import ast
import io
import json
import re
import runpy
import tokenize
import types
from collections.abc import Iterator
from typing import Any, Final

import django
import httpx
import pytest
from django.conf import settings
from django.test import Client
from django.urls import clear_url_caches
from fastapi.testclient import TestClient

from slen._http import _pool
from slen._http._endpoints import Endpoint
from slen.testing import FakeTransport, RecordedRequest
from support.harness import FakeClock
from support.paths import EXAMPLES
from support.schema import problems
from support.spec import loaded, spec

# The examples of the console's Help & Docs, run as they are written: each python.py on a double fed with the
# answers of its example.json, what it sent and what it printed held against its expect.json. The rules an
# example follows are in AGENTS.md ("Help examples").

KEY: Final = "sl_live_help_example"
BASE: Final = "https://api.slen.ai/api"
LANGUAGE: Final = "python"
FILE: Final = "python.py"
TEN_MINUTES: Final = 600.0

REGION_START: Final = re.compile(r"^\s*# docs:start ([a-z][a-z0-9-]*)\s*$")
REGION_END: Final = re.compile(r"^\s*# docs:end\s*$")

# What no region may show: names that are going or never were, and the lines of the harness.
NOT_SHOWN: Final = (
    (re.compile(r"wait_until_finished|waitUntilFinished"), "the wait is wait()"),
    (re.compile(r"\bis_allowed\b|\bisAllowed\b"), "is_allowed() goes away with the denied status"),
    (re.compile(r"['\"]denied['\"]"), "the denied status of a hold goes away"),
    (re.compile(r"sg_test_|dry_run"), "the test mode is not documented"),
    (re.compile(r"SlenClient"), "there is no SlenClient"),
    (re.compile(r"L[I]MLY_|SP[E]NDGUARD_"), "the names of the environment before the rename"),
    (re.compile(r"X-L[i]mly-|X-Sp[e]ndGuard-", re.IGNORECASE), "the headers before the rename"),
    (re.compile(r"first-request-1"), "an idempotency key is derived from the unit of work"),
    (re.compile(r"localhost"), "an example names the production host"),
    (re.compile(r"\bHarness:"), "a # Harness: line stays outside every region"),
    (re.compile(r"\brecorded\b"), "recorded is what an example hands to the harness"),
)

HOLDS: Final = "the holds left the SDK: a flow holds and settles the money of its model calls"
GATEWAY: Final = "the gateway is called from inside a flow only: run the operation with operations.execute"

# What the SDK no longer has, in any spelling.
RETIRED: Final = (
    (re.compile(r"\bauthorizations\b|reservations\(|AuthorizeAiOperation"), HOLDS),
    (re.compile(r"costEstimates|cost_estimates"), "the estimates left the SDK"),
    (re.compile(r"\bchat\.|\bchat\(\)"), GATEWAY),
    (re.compile(r"(?<!asyncio)\.run\(|\.stream\("), GATEWAY),
    (re.compile(r"responses\.create|wrapOpenAI|wrap_openai"), GATEWAY),
    (re.compile(r"\boperations\.wait\b|\boperations\.execution\b"), "a run is read through executions"),
    (re.compile(r"defaultOperation|default_operation"), "the SDK has no default operation"),
    (re.compile(r"set_logger\(|setLogger\("), "a logger of its own is a copy of the client: with_logger()"),
)

# What no file of an example names, in a region or out of one.
NAMED_NOWHERE: Final = (
    (re.compile(r"base[_ ]?url", re.IGNORECASE), "the address of the API is the SDK's constant"),
    (re.compile(r"\bsg_(?:live|test)_"), "a key is shown as sl_live_…"),
)


def ids() -> list[str]:
    found: list[str] = []

    for path in sorted(EXAMPLES.iterdir()):
        example = json.loads((path / "example.json").read_text(encoding="utf-8"))

        if LANGUAGE in example["languages"]:
            found.append(path.name)

    return found


def example_of(name: str) -> dict[str, Any]:
    found: dict[str, Any] = json.loads((EXAMPLES / name / "example.json").read_text(encoding="utf-8"))

    return found


def expect_of(name: str) -> dict[str, Any]:
    found: dict[str, Any] = json.loads((EXAMPLES / name / "expect.json").read_text(encoding="utf-8"))

    return found


def regions_of(text: str) -> tuple[list[tuple[str, list[int]]], list[str]]:
    """The regions of a file — each name with the numbers of its lines — and what is wrong with the markers."""
    regions: list[tuple[str, list[int]]] = []
    found: list[str] = []
    open_name: str | None = None

    for number, line in enumerate(text.splitlines(), start=1):
        start = REGION_START.match(line)
        end = REGION_END.match(line)

        if start is not None and open_name is not None:
            found.append(f"{number}: {start.group(1)} opens inside {open_name}")

        if start is not None:
            opened = start.group(1)
            open_name = opened
            regions.append((opened, []))
            continue

        if end is not None and open_name is None:
            found.append(f"{number}: docs:end closes nothing")

        if end is not None:
            open_name = None
            continue

        if "docs:start" in line or "docs:end" in line:
            found.append(f"{number}: a marker that is not one")

        if open_name is not None:
            regions[-1][1].append(number)

    found += [] if open_name is None else [f"the region {open_name} is not closed"]
    found += [
        f"the region {name} is empty"
        for name, lines in regions
        if not any(text.splitlines()[n - 1].strip() for n in lines)
    ]

    return regions, found


def region_text(text: str, lines: list[int]) -> str:
    every = text.splitlines()

    return "\n".join(every[number - 1] for number in lines)


def bound_outside(text: str, inside: set[int]) -> set[str]:
    """The names a statement outside every region binds: a region may not read them."""
    names: set[str] = set()

    for node in ast.parse(text).body:
        lines = set(range(node.lineno, (node.end_lineno or node.lineno) + 1))

        if lines & inside:
            continue

        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
                names.add(inner.id)

            if isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                names.add(inner.name)

    return names


def read_in(text: str) -> set[str]:
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)

    return {token.string for token in tokens if token.type == tokenize.NAME}


@pytest.mark.parametrize("name", ids())
def test_an_example_carries_the_regions_its_example_json_lists(name: str) -> None:
    text = (EXAMPLES / name / FILE).read_text(encoding="utf-8")
    regions, found = regions_of(text)

    assert found == []
    assert [region for region, _ in regions] == example_of(name)["regions"]


@pytest.mark.parametrize("name", ids())
def test_a_region_shows_only_what_a_reader_may_see_and_leans_on_nothing_hidden(name: str) -> None:
    text = (EXAMPLES / name / FILE).read_text(encoding="utf-8")
    regions, _ = regions_of(text)
    inside = {number for _, lines in regions for number in lines}
    hidden = bound_outside(text, inside)
    found: list[str] = []

    for region, lines in regions:
        shown = region_text(text, lines)
        found += [f"{region}: {why}" for pattern, why in (*NOT_SHOWN, *RETIRED) if pattern.search(shown)]
        found += [f"{region}: reads {used}, which no region brings in" for used in sorted(read_in(shown) & hidden)]

    assert found == []


@pytest.mark.parametrize("name", ids())
def test_no_file_of_an_example_names_the_address_or_an_old_key(name: str) -> None:
    found = [
        f"{path.name}: {why}"
        for path in sorted((EXAMPLES / name).iterdir())
        for pattern, why in NAMED_NOWHERE
        if pattern.search(path.read_text(encoding="utf-8"))
    ]

    assert found == []


def test_every_example_for_python_has_its_file_and_no_other_has_one() -> None:
    with_file = sorted(path.parent.name for path in EXAMPLES.glob(f"*/{FILE}"))

    assert with_file == ids()
    assert all(not example_of(name).get("laravel") for name in ids())


# ---------------------------------------------------------------------------
# The run.


def route_of(path: str) -> Endpoint:
    for endpoint in Endpoint:
        pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(endpoint.route))

        if re.fullmatch(pattern, path):
            return endpoint

    raise LookupError(path)


def call_problems(recorded: tuple[RecordedRequest, ...], expected: list[dict[str, Any]]) -> list[str]:
    found = [] if len(recorded) == len(expected) else [f"{len(recorded)} requests sent, {len(expected)} expected"]

    for number, (sent, call) in enumerate(zip(recorded, expected, strict=False), start=1):
        url = httpx.URL(sent.url)
        headers = {name.lower(): value for name, value in call.get("headers", {}).items()}
        wanted = {"authorization": f"Bearer {KEY}", **headers}
        seen = (sent.method, str(url.copy_with(query=None)), dict(url.params.multi_items()), sent.body)
        meant = (call["method"], f"{BASE}{call['path']}", call.get("query", {}), call.get("body"))
        found += [] if seen == meant else [f"call {number}: sent {seen}, expected {meant}"]
        found += [
            f"call {number}: {name} is {sent.headers.get(name)!r}"
            for name, value in wanted.items()
            if sent.headers.get(name) != value
        ]
        found += (
            []
            if "idempotency-key" in wanted or "idempotency-key" not in sent.headers
            else [f"call {number}: a key that was not expected"]
        )

    return found


def drive_fastapi(module: dict[str, Any], requests: list[dict[str, Any]]) -> list[str]:
    found: list[str] = []

    # Starlette's test client is typed against a fork of httpx the suite does not install: it is read as Any.
    with TestClient(module["app"]) as tested:
        client: Any = tested

        for request in requests:
            answer = client.request(
                request["method"], request["path"], headers=request.get("headers"), json=request.get("body")
            )
            found += answer_problems(request, answer.status_code, answer.json())

    return found


def drive_django(module: dict[str, Any], requests: list[dict[str, Any]]) -> list[str]:
    if not settings.configured:
        settings.configure(DEBUG=False, SECRET_KEY="harness", ALLOWED_HOSTS=["testserver"], MIDDLEWARE=[], USE_TZ=True)
        django.setup()

    urls = types.ModuleType("example_urls")
    urls.urlpatterns = module["urlpatterns"]  # type: ignore[attr-defined]
    settings.ROOT_URLCONF = urls
    clear_url_caches()
    found: list[str] = []

    for request in requests:
        body = json.dumps(request["body"]) if "body" in request else ""
        answer = Client().generic(
            request["method"], request["path"], body, "application/json", headers=request.get("headers")
        )
        found += answer_problems(request, answer.status_code, json.loads(answer.content))

    return found


def answer_problems(request: dict[str, Any], status: int, body: object) -> list[str]:
    where = f"{request['method']} {request['path']}"
    found = [] if status == request["status"] else [f"{where}: answered {status}, expected {request['status']}"]

    return found + ([] if "answer" not in request or body == request["answer"] else [f"{where}: answered {body}"])


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> Iterator[FakeTransport]:
    fake = FakeTransport()

    def sync_pool(config: object) -> httpx.Client:
        return httpx.Client(transport=fake)

    def async_pool(config: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=fake)

    monkeypatch.setattr(_pool, "sync_pool", sync_pool)
    monkeypatch.setattr(_pool, "async_pool", async_pool)
    monkeypatch.setenv("SLEN_API_KEY", KEY)

    yield fake

    assert clock.elapsed <= TEN_MINUTES, "the example's own clock ran past ten minutes"


@pytest.mark.parametrize("name", ids())
def test_an_example_sends_what_expect_json_says_and_prints_it(
    name: str, served: FakeTransport, capsys: pytest.CaptureFixture[str]
) -> None:
    example, expect = example_of(name), expect_of(name)

    for answer in example["responses"]:
        served.push(answer["status"], answer["body"])

    module = runpy.run_path(str(EXAMPLES / name / FILE), run_name=f"example_{name.replace('-', '_')}")
    framework = example.get("framework")
    driven: list[str] = []

    if framework is not None and framework["name"] == "fastapi":
        driven = drive_fastapi(module, framework["requests"])

    if framework is not None and framework["name"] == "django":
        driven = drive_django(module, framework["requests"])

    recorded: tuple[RecordedRequest, ...] = tuple(module.get("recorded", served.requests))

    assert driven == []
    assert call_problems(recorded, expect["calls"]) == []
    assert capsys.readouterr().out.splitlines() == expect["prints"]


# ---------------------------------------------------------------------------
# Against the API's spec.


def operation_of(method: str, path: str) -> dict[str, Any]:
    found: dict[str, Any] = spec()["paths"][route_of(path).route][method.lower()]

    return found


def every_example() -> list[str]:
    return sorted(path.name for path in EXAMPLES.iterdir())


@pytest.mark.parametrize("name", every_example())
def test_with_the_spec_every_answer_an_example_is_served_has_the_shape_of_its_operation(name: str) -> None:
    calls, answers = expect_of(name)["calls"], example_of(name)["responses"]
    found: list[str] = []

    for call, answer in zip(calls, answers, strict=False):
        responses = operation_of(call["method"], call["path"])["responses"]
        described: dict[str, Any] | None = responses.get(str(answer["status"]))

        if described is None and answer["status"] != 429:
            found.append(f"{call['method']} {call['path']} does not answer {answer['status']}")
            continue

        content: dict[str, Any] = (described or {}).get("content", {}).get("application/json", {})
        found += problems(answer["body"], content.get("schema", {}), f"{call['path']} {answer['status']}")

    assert found == []


@pytest.mark.parametrize("name", every_example())
def test_with_the_spec_every_body_an_example_sends_has_the_shape_of_its_operation(name: str) -> None:
    found: list[str] = []

    for call in expect_of(name)["calls"]:
        body = operation_of(call["method"], call["path"]).get("requestBody")

        if "body" in call and body is not None:
            found += problems(call["body"], body["content"]["application/json"]["schema"], call["path"])

        if "body" in call and body is None:
            found.append(f"{call['path']} takes no body")

    assert found == []


def test_the_spec_is_read_when_it_is_named() -> None:
    if loaded() is None:
        pytest.skip("no spec named")

    assert isinstance(spec()["paths"], dict)


def test_the_harness_finds_a_marker_out_of_place() -> None:
    _, found = regions_of("# docs:start a\nx = 1\n# docs:start b\ny = 2\n# docs:end\n# docs:end\n")

    assert found != []
    assert regions_of("# docs:start a\n\n# docs:end\n")[1] == ["the region a is empty"]


def test_the_harness_finds_a_region_that_leans_on_the_harness() -> None:
    text = "hidden = 1\n# docs:start a\nprint(hidden)\n# docs:end\n"
    regions, _ = regions_of(text)

    assert read_in(region_text(text, regions[0][1])) & bound_outside(text, set(regions[0][1])) == {"hidden"}


def test_the_spec_problems_are_found() -> None:
    shape = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}

    assert problems({"a": 1}, shape, "x") == ["x.a is not of type string"]
    assert problems({}, shape, "x") == ["x.a is missing"]
    assert problems({"a": "1", "b": 2}, shape, "x") == ["x.b is not in the schema"]

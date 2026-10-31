import dataclasses
import json
import re
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import httpx
import pytest

import slen
from slen import Slen
from slen._config import DEFAULT_BASE_URL
from slen._http._endpoints import Endpoint
from slen.testing import FakeTransport, RecordedRequest
from support.harness import (
    BASE,
    KINDS,
    Kind,
    account,
    collect,
    customer,
    data,
    drive,
    entry,
    price,
    run_result,
    run_view,
    trace,
)
from support.paths import CONTRACT, SRC
from support.schema import problems
from support.spec import resolved, schema, spec

# The contract of the calls: every public call of the client is a line of contract/calls.json that names Python,
# and the other way round; each is driven to the method and the path its line names — with no spec, and against
# the spec where there is one.

SDK: Final = "python"
LINES: Final[dict[str, dict[str, Any]]] = {
    name: line
    for name, line in json.loads((CONTRACT / "calls.json").read_text(encoding="utf-8"))["calls"].items()
    if SDK in line["sdks"]
}

# The public calls that make no request of the API, each with why.
NOT_CALLS: Final = {
    "webhooks.verify": "checks a signature on the machine, with the endpoint's secret",
    "webhooks.construct_event": "reads an event the machine was sent",
    "close": "closes the connections of the client",
}

ID: Final = "74438200973594624"
USER: Final = "user 42"
INPUT: Final = {"question": "hello"}
EXECUTE: Final = {
    "customer": USER,
    "credit_type": "enrichment",
    "context": {"tenant": "acme"},
    "idempotency_key": "ticket-42:answer",
}
MOVE: Final = {"credit_type": "enrichment", "note": "invoice 7781", "idempotency_key": "invoice-7781"}
HEALTH: Final = {
    "app": "slen",
    "release": None,
    "server": "octane",
    "mysql": "ok",
    "redis": "ok",
    "queue": None,
    "broadcast": None,
    "opcache_preloaded_files": None,
    "opcache_cached_scripts": None,
}


@dataclass(frozen=True)
class Row:
    run: Callable[[Any], Any]
    answers: tuple[tuple[int, dict[str, Any] | None], ...]


def page(rows: list[Any], cursor: str | None, limit: int) -> dict[str, Any]:
    return {"data": rows, "meta": {"limit": limit, "next_cursor": cursor}}


# Each body is the fullest the call can make: every option that goes into the body or the query is passed.
ROWS: Final[dict[str, Row]] = {
    "operations.execute": Row(
        lambda c: c.operations.execute("support.answer", INPUT, **EXECUTE), ((200, data(run_result())),)
    ),
    "operations.executeAsync": Row(
        lambda c: c.operations.execute_async("support.answer", INPUT, **EXECUTE),
        ((202, data(run_result(status="queued", output=None))),),
    ),
    "executions.get": Row(lambda c: c.executions.get(ID), ((200, data(run_view())),)),
    "executions.wait": Row(lambda c: c.executions.wait(ID, timeout_seconds=5), ((200, data(run_view())),)),
    "executions.trace": Row(lambda c: c.executions.trace(ID), ((200, data(trace())),)),
    "customers.list": Row(
        lambda c: c.customers.list(
            cursor="eyJpZCI6MX0", limit=30, search="user", status="active", credit_type="enrichment", low_balance="10"
        ),
        ((200, page([customer()], None, 30)),),
    ),
    "customers.listAll": Row(
        lambda c: collect(
            c.customers.list_all(
                cursor="eyJpZCI6MX0",
                limit=1,
                search="user",
                status="active",
                credit_type="enrichment",
                low_balance="10",
            )
        ),
        ((200, page([customer()], ID, 1)), (200, page([], None, 1))),
    ),
    "customers.get": Row(lambda c: c.customers.get(USER), ((200, data(customer())),)),
    "customers.create": Row(lambda c: c.customers.create(USER), ((201, data(customer(accounts=[]))),)),
    "customers.updateAccount": Row(
        lambda c: c.customers.update_account(USER, "enrichment", allow_negative=True, low_balance_threshold="10.0000"),
        ((200, data(account())),),
    ),
    "customers.block": Row(
        lambda c: c.customers.block(USER, reason="Chargeback"), ((200, data(customer(status="blocked"))),)
    ),
    "customers.unblock": Row(lambda c: c.customers.unblock(USER), ((200, data(customer())),)),
    "customers.delete": Row(lambda c: c.customers.delete(USER), ((204, None),)),
    "customers.topUp": Row(lambda c: c.customers.top_up(USER, "100.0000", **MOVE), ((200, data(account())),)),
    "customers.charge": Row(lambda c: c.customers.charge(USER, "5.0000", **MOVE), ((200, data(account())),)),
    "customers.adjust": Row(lambda c: c.customers.adjust(USER, "-5.0000", **MOVE), ((200, data(account())),)),
    "customers.entries": Row(
        lambda c: c.customers.entries(
            USER, cursor="eyJpZCI6MX0", limit=30, credit_type="enrichment", entry_type="charge"
        ),
        ((200, page([entry()], None, 30)),),
    ),
    "customers.entriesAll": Row(
        lambda c: collect(
            c.customers.entries_all(USER, cursor="eyJpZCI6MX0", limit=1, credit_type="enrichment", entry_type="charge")
        ),
        ((200, page([entry()], ID, 1)), (200, page([], None, 1))),
    ),
    "customers.prices": Row(
        lambda c: c.customers.prices(operation_code="support.answer", credit_type="enrichment"),
        ((200, data([price()])),),
    ),
    "health": Row(lambda c: c.health(), ((200, HEALTH),)),
}


def python_name(key: str) -> str:
    """The key of contract/calls.json as Python writes it: each segment in snake_case, nothing else."""
    return ".".join(re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", segment).lower() for segment in key.split("."))


def public_calls() -> set[str]:
    client = Slen(api_key="key-for-tests")
    calls = {name for name in dir(Slen) if not name.startswith("_") and callable(getattr(Slen, name))}
    calls -= {"with_logger"}

    for module in ("operations", "executions", "customers", "webhooks"):
        calls.discard(module)
        found = getattr(client, module)
        calls |= {
            f"{module}.{name}" for name in dir(found) if not name.startswith("_") and callable(getattr(found, name))
        }

    return calls


def sent(kind: Kind, name: str) -> tuple[RecordedRequest, ...]:
    fake = FakeTransport()

    for status, body in ROWS[name].answers:
        fake.push(status, body)

    drive(kind, fake, ROWS[name].run)

    return fake.requests


def template_of(request: RecordedRequest) -> str:
    path = request.url.removeprefix(BASE).split("?")[0]

    for endpoint in Endpoint:
        pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(endpoint.route))

        if endpoint.method == request.method and re.fullmatch(pattern, path):
            return str(endpoint)

    return f"{request.method} {path}"


def test_the_rule_of_names_is_one_function_both_ways() -> None:
    assert python_name("customers.topUp") == "customers.top_up"
    assert python_name("operations.executeAsync") == "operations.execute_async"
    assert python_name("customers.entriesAll") == "customers.entries_all"
    assert python_name("health") == "health"


def test_every_public_call_is_a_line_of_the_table_or_says_why_not() -> None:
    assert public_calls() == {python_name(key) for key in LINES} | set(NOT_CALLS)


def test_the_rows_are_the_lines_of_the_table() -> None:
    assert set(ROWS) == set(LINES)
    assert len(LINES) == 20


def test_every_line_names_an_operation_and_the_sdks_that_offer_it() -> None:
    for name, line in LINES.items():
        assert re.fullmatch(r"(GET|POST|PUT|DELETE) /\S+", line["operation"]), name
        assert len(set(line["sdks"])) == len(line["sdks"]), name


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("name", sorted(LINES))
def test_every_call_goes_to_the_method_and_the_path_of_its_line(kind: Kind, name: str) -> None:
    requests = sent(kind, name)

    assert requests != ()
    assert {template_of(request) for request in requests} == {LINES[name]["operation"]}


def test_the_operations_of_the_sdk_are_those_of_the_table_both_ways() -> None:
    assert {str(endpoint) for endpoint in Endpoint} == {line["operation"] for line in LINES.values()}


def test_no_path_of_the_api_is_spelt_outside_the_endpoints() -> None:
    found = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if path.name != "_endpoints.py"
        and re.search(r"[\"'](?:GET |POST |PUT |DELETE )?/(?:v1/|health)", path.read_text())
    ]

    assert found == []


# ---------------------------------------------------------------------------
# Against the API's spec.


def operation_of(key: str) -> dict[str, Any]:
    method, path = LINES[key]["operation"].split(" ", 1)
    found: dict[str, Any] = spec()["paths"][path][method.lower()]

    return found


def parameters_of(key: str) -> list[dict[str, Any]]:
    method, path = LINES[key]["operation"].split(" ", 1)
    item = spec()["paths"][path]
    declared = [*item.get("parameters", []), *item[method.lower()].get("parameters", [])]

    return [resolved_parameter(parameter) for parameter in declared]


def resolved_parameter(parameter: dict[str, Any]) -> dict[str, Any]:
    if "$ref" not in parameter:
        return parameter

    found: dict[str, Any] = spec()["components"]["parameters"][str(parameter["$ref"]).rsplit("/", 1)[-1]]

    return found


@pytest.mark.parametrize("name", sorted(LINES))
def test_with_the_spec_every_operation_is_a_path_of_it(name: str) -> None:
    assert isinstance(operation_of(name), dict)


@pytest.mark.parametrize("name", sorted(LINES))
def test_with_the_spec_every_call_sends_the_query_and_the_body_its_operation_describes(name: str) -> None:
    query = {parameter["name"] for parameter in parameters_of(name) if parameter["in"] == "query"}
    body = operation_of(name).get("requestBody")
    found: list[str] = []

    for request in sent("sync", name):
        found += [f"query {key}" for key in dict(_params(request.url)) if key not in query]

        if request.body is not None and body is None:
            found.append("a body the operation does not take")

        if request.body is not None and body is not None:
            found += problems(request.body, body["content"]["application/json"]["schema"], "body")

    assert found == []


def _params(url: str) -> list[tuple[str, str]]:
    return list(httpx.URL(url).params.multi_items())


@pytest.mark.parametrize("name", sorted(LINES))
def test_with_the_spec_the_idempotency_key_is_sent_exactly_where_it_is_declared(name: str) -> None:
    declared = any(
        parameter["in"] == "header" and parameter["name"].lower() == "idempotency-key"
        for parameter in parameters_of(name)
    )

    assert {("idempotency-key" in request.headers) for request in sent("sync", name)} == {declared}


@pytest.mark.parametrize("name", sorted(LINES))
def test_with_the_spec_every_answer_of_a_row_has_the_shape_its_operation_answers(name: str) -> None:
    responses = operation_of(name)["responses"]
    found: list[str] = []

    for status, body in ROWS[name].answers:
        described = responses[str(status)]
        content = described.get("content", {}).get("application/json")
        found += [] if body is None else problems(body, content["schema"], f"{name} {status}")

    assert found == []


def test_with_the_spec_the_host_the_sdk_talks_to_is_its_first_server() -> None:
    assert spec()["servers"][0]["url"] == f"{DEFAULT_BASE_URL}/api"


# ---------------------------------------------------------------------------
# The shapes: every field of a type of an answer is a property of its schema, and the other way round.

SHAPES: Final[dict[type, str]] = {
    slen.Health: "Health",
    slen.ExecutionResult: "ExecutionResult",
    slen.ExecutionStatusView: "ExecutionStatusView",
    slen.ExecutionCost: "ExecutionCost",
    slen.ExecutionCache: "ExecutionCache",
    slen.WaitingOn: "WaitingOn",
    slen.ExecutionTrace: "FlowExecutionTrace",
    slen.FlowExecutionNode: "FlowExecutionNode",
    slen.FlowExecutionEvent: "FlowExecutionEvent",
    slen.AttemptSummary: "AttemptSummary",
    slen.Customer: "Customer",
    slen.CustomerAccount: "CustomerAccount",
    slen.CreditEntry: "CustomerCreditEntry",
    slen.CreditPrice: "CreditPrice",
}

# The types of the answers that transcribe no schema of their own, each with why.
NOT_COMPARED: Final[dict[type, str]] = {
    slen.Page: "the page of a list, `data` and `meta.next_cursor` read flat; its rows are compared on their own",
    slen.CreditPriceList: "the body of GET /v1/credit-prices, written in place by the spec; its rows are compared",
    slen.ExecutionError: "`error_code` and `error_message` of the run as one object, which the spec leaves open",
}

# Where a type says something else than the spec on purpose: the line the comparison prints, and why.
KNOWN_DIVERGENCES: Final[dict[str, str]] = {}

# The id of a response is its header, not a field of its body.
NOT_OF_THE_BODY: Final = frozenset({"request_id"})


def optional(annotation: object) -> bool:
    return type(None) in typing.get_args(annotation) and isinstance(annotation, types.UnionType)


def nullable(given: dict[str, Any]) -> bool:
    found = resolved(given) if "$ref" in given or "allOf" in given else given
    alternatives = found.get("oneOf", found.get("anyOf", []))
    kinds = found.get("type", [])

    return (
        "null" in kinds or any(option.get("type") == "null" for option in alternatives) or found.get("nullable") is True
    )


def divergences_of(kind: type, name: str) -> list[str]:
    shape = resolved({"$ref": f"#/components/schemas/{name}"})
    properties: dict[str, Any] = shape.get("properties", {})
    required = set(shape.get("required", []))
    hints = typing.get_type_hints(kind)
    fields = {field.name for field in dataclasses.fields(kind)} - NOT_OF_THE_BODY
    found = [f"{kind.__name__}.{field}: not in the spec" for field in sorted(fields - set(properties))]
    found += [f"{kind.__name__}.{field}: in the spec, not in the SDK" for field in sorted(set(properties) - fields)]

    for field in sorted(fields & set(properties)):
        may_lack = field not in required or nullable(properties[field])

        if may_lack and not optional(hints[field]):
            found.append(f"{kind.__name__}.{field}: may be absent or null in the spec, never None in the SDK")

        if not may_lack and optional(hints[field]):
            found.append(f"{kind.__name__}.{field}: always there in the spec, may be None in the SDK")

    return found


def test_with_the_spec_the_types_declare_the_shapes_the_spec_declares() -> None:
    found = [line for kind, name in SHAPES.items() for line in divergences_of(kind, name)]

    assert {line: KNOWN_DIVERGENCES.get(line) for line in found} == KNOWN_DIVERGENCES
    assert set(found) == set(KNOWN_DIVERGENCES)


def test_every_type_of_an_answer_is_compared_or_says_why_not() -> None:
    answers = {
        value
        for name, value in vars(slen).items()
        if name in slen.__all__ and dataclasses.is_dataclass(value) and isinstance(value, type)
    }
    events = {
        value for value in answers if issubclass(value, slen.WebhookEvent) or value.__name__.endswith("EventData")
    }
    others = events | {slen.SlenSpan}

    assert answers - others == set(SHAPES) | set(NOT_COMPARED)


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        (slen.ExecutionStatus, "ExecutionStatus"),
        (slen.CustomerStatus, "CustomerStatus"),
    ],
)
def test_with_the_spec_an_enumeration_has_the_values_of_its_schema(kind: type, name: str) -> None:
    assert {str(member) for member in kind} == set(schema(name)["enum"])  # type: ignore[attr-defined]


def test_with_the_spec_the_types_of_entries_are_its_enumeration() -> None:
    entry_type = schema("CustomerCreditEntry")["properties"]["entry_type"]

    assert {str(member) for member in slen.CreditEntryType} == set(entry_type["enum"])

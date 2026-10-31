# pyright: reportPrivateUsage=false
import copy
import math
import pickle
import re
from typing import Any

import httpx
import pytest

from slen import AsyncSlen, Slen
from slen.testing import FakeTransport
from support.harness import KEY, Kind, RecordingLogger, data, drive, run_view
from support.paths import SRC

CLIENTS = (Slen, AsyncSlen)


def build(kind: Kind, **options: Any) -> Slen | AsyncSlen:
    return Slen(**options) if kind == "sync" else AsyncSlen(**options)


def test_the_key_comes_from_slen_api_key_when_none_is_passed(kind: Kind, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLEN_API_KEY", "sl_live_from_the_environment")
    fake = FakeTransport().push(200, data(run_view()))

    drive(kind, fake, lambda slen: slen.executions.get("74438200973594700"), api_key=None)

    assert fake.last().headers["authorization"] == "Bearer sl_live_from_the_environment"


@pytest.mark.parametrize("given", [None, "", "   "])
def test_a_client_without_a_key_is_a_value_error(kind: Kind, given: str | None) -> None:
    with pytest.raises(ValueError, match="SLEN_API_KEY"):
        build(kind, api_key=given)


def test_a_key_that_is_not_a_string_is_a_type_error(kind: Kind) -> None:
    with pytest.raises(TypeError):
        build(kind, api_key=42)


@pytest.mark.parametrize(
    ("option", "value", "error"),
    [
        ("timeout", 0, ValueError),
        ("timeout", -1.0, ValueError),
        ("timeout", math.nan, ValueError),
        ("timeout", True, TypeError),
        ("timeout", "65", TypeError),
        ("connect_timeout", 0, ValueError),
        ("retries", -1, ValueError),
        ("retries", 1.5, TypeError),
        ("retries", False, TypeError),
        ("webhook_tolerance_seconds", 0, ValueError),
        ("headers", {"X-Team": 7}, TypeError),
        ("logger", object(), TypeError),
        ("span_recorder", object(), TypeError),
        ("base_url", "", ValueError),
    ],
)
def test_an_option_out_of_range_is_a_programming_error(kind: Kind, option: str, value: object, error: type) -> None:
    with pytest.raises(error):
        build(kind, api_key=KEY, **{option: value})


def test_an_infinite_timeout_switches_the_attempt_clock_off(kind: Kind) -> None:
    build(kind, api_key=KEY, timeout=math.inf, connect_timeout=math.inf)


def test_each_client_takes_its_own_kind_of_http_client() -> None:
    with pytest.raises(TypeError, match="AsyncClient"):
        Slen(api_key=KEY, http_client=httpx.AsyncClient())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"httpx\.Client"):
        AsyncSlen(api_key=KEY, http_client=httpx.Client())  # type: ignore[arg-type]


def test_building_a_client_touches_no_network(kind: Kind) -> None:
    fake = FakeTransport()
    http = httpx.Client(transport=fake) if kind == "sync" else httpx.AsyncClient(transport=fake)
    build(kind, api_key=KEY, http_client=http)

    assert fake.requests == ()


def test_neither_the_repr_nor_the_slots_of_a_client_show_the_key(kind: Kind) -> None:
    client = build(kind, api_key="sl_live_never_printed", webhook_secret="whsec_never_printed")

    assert "never_printed" not in repr(client)
    assert "never_printed" not in repr(client._parts)  # what a debugger shows
    assert not hasattr(client, "__dict__")


@pytest.mark.parametrize("travel", [pickle.dumps, copy.copy, copy.deepcopy])
def test_a_client_does_not_travel_to_another_process(kind: Kind, travel: Any) -> None:
    with pytest.raises(TypeError, match="each process"):
        travel(build(kind, api_key=KEY))


def test_with_logger_answers_a_copy_that_owns_no_connections(kind: Kind) -> None:
    client = build(kind, api_key=KEY)
    logger = RecordingLogger()
    copy_of = client.with_logger(logger)

    assert copy_of is not client
    assert copy_of._parts.http is client._parts.http  # the shared pool
    assert copy_of._parts.owns is False
    assert copy_of._parts.config.logger is logger

    with pytest.raises(TypeError):
        client.with_logger(object())  # type: ignore[arg-type]


def test_close_closes_only_the_client_the_sdk_built() -> None:
    own = Slen(api_key=KEY)
    given = httpx.Client()
    lent = Slen(api_key=KEY, http_client=given)

    with own:
        pass
    lent.close()
    own.with_logger(RecordingLogger()).close()

    assert own._parts.http.is_closed
    assert not given.is_closed


@pytest.mark.asyncio
async def test_close_of_the_async_client_closes_only_what_it_built() -> None:
    given = httpx.AsyncClient()

    async with AsyncSlen(api_key=KEY) as own:
        pass
    await AsyncSlen(api_key=KEY, http_client=given).close()

    assert own._parts.http.is_closed
    assert not given.is_closed
    await given.aclose()


def test_the_environment_is_read_in_one_file_by_one_name() -> None:
    readers = sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if re.search(r"\bos\.environ\b|\bgetenv\b|\benviron\b", path.read_text(encoding="utf-8"))
    )
    names = {
        name for path in SRC.rglob("*.py") for name in re.findall(r"\bSLEN_[A-Z_]+\b", path.read_text(encoding="utf-8"))
    }

    assert readers == ["_config.py"]
    assert names == {"SLEN_API_KEY"}

import json
import math
from datetime import UTC, datetime
from types import MappingProxyType

import httpx
import pytest

from slen import InvalidRequestError
from slen._http._endpoints import Endpoint
from slen._http._request import encode_body
from slen.testing import FakeTransport
from support.harness import Kind, RecordingLogger, data, drive, raised, run_result

INPUT = {"messages": [{"role": "user", "content": "Grüß Gott — 你好"}], "n": [1, 2], "ok": True, "none": None}


class Bytes(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """Keeps the raw bytes of each body it is sent."""

    def __init__(self) -> None:
        self.bodies: list[bytes] = []
        self.types: list[str | None] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(request.content)
        self.types.append(request.headers.get("content-type"))

        return httpx.Response(200, json=data(run_result()))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self.handle_request(request)


def test_the_body_is_compact_json_in_utf_8_whatever_httpx_does_with_json() -> None:
    expected = (
        '{"operation":"support.answer","input":{"messages":[{"role":"user","content":"Grüß Gott — 你好"}],'
        '"n":[1,2],"ok":true,"none":null}}'
    )

    assert encode_body(Endpoint.EXECUTE, {"operation": "support.answer", "input": INPUT}) == expected.encode()


def test_the_bytes_on_the_wire_are_the_sdks_own(kind: Kind) -> None:
    transport = Bytes()

    drive(kind, transport, lambda slen: slen.operations.execute("support.answer", INPUT, idempotency_key="k-1"))

    assert transport.bodies == [encode_body(Endpoint.EXECUTE, {"operation": "support.answer", "input": INPUT})]
    assert transport.types == ["application/json"]


def test_a_mapping_that_is_not_a_dict_is_sent_as_an_object(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_result()))

    drive(kind, fake, lambda slen: slen.operations.execute("op", MappingProxyType({"a": MappingProxyType({"b": 1})})))

    assert fake.last().body["input"] == {"a": {"b": 1}}


@pytest.mark.parametrize("value", [math.nan, math.inf, datetime(2026, 10, 17, tzinfo=UTC), object(), {1, 2}])
def test_an_input_that_is_not_json_is_refused_before_the_wire(kind: Kind, value: object) -> None:
    fake = FakeTransport()

    error = raised(kind, fake, lambda slen: slen.operations.execute("op", {"value": value}))

    assert isinstance(error, InvalidRequestError)
    assert "not JSON" in str(error)
    assert fake.requests == ()


def test_text_that_is_not_unicode_is_refused_before_the_wire_and_written_nowhere(kind: Kind) -> None:
    fake = FakeTransport()
    logger = RecordingLogger()

    error = raised(kind, fake, lambda slen: slen.operations.execute("op", {"x": "\ud800"}), logger=logger)

    assert isinstance(error, InvalidRequestError)
    assert error.code == "invalid_request"
    assert fake.requests == ()
    assert logger.entries == []


def test_a_call_without_a_body_sends_no_content_type(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_result()))

    drive(kind, fake, lambda slen: slen.executions.get("74438200973594700"))

    assert "content-type" not in fake.last().headers
    assert fake.last().body is None


def test_an_empty_body_is_an_empty_object(kind: Kind) -> None:
    fake = FakeTransport().push(201, data({}))

    raised(kind, fake, lambda slen: slen.customers.create("user 42"))

    assert json.loads(b"{}") == fake.last().body

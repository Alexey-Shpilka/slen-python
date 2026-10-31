import asyncio

import httpx
import pytest

from slen import AsyncSlen, ExecutionStatus, Slen
from slen.testing import FakeTransport, MemorySpanRecorder
from support.harness import KEY, bare_span, data, run_result


def test_the_double_answers_in_order_and_keeps_every_request() -> None:
    fake = FakeTransport().push(200, data(run_result())).push(503, {"error": {"code": "service_unavailable"}})
    client = Slen(api_key=KEY, http_client=httpx.Client(transport=fake), retries=0)

    run = client.operations.execute("support.answer", {"q": 1}, idempotency_key="order-42:answer")

    assert run.status is ExecutionStatus.COMPLETED
    assert fake.last().method == "POST"
    assert fake.last().url == "https://api.slen.ai/api/v1/operations/execute"
    assert fake.last().body == {"operation": "support.answer", "input": {"q": 1}}
    assert fake.last().headers["idempotency-key"] == "order-42:answer"
    assert len(fake.requests) == 1


def test_a_request_with_nothing_queued_is_a_lookup_error_that_names_its_route() -> None:
    fake = FakeTransport()
    client = Slen(api_key=KEY, http_client=httpx.Client(transport=fake))

    with pytest.raises(LookupError, match=r"GET /v1/customers/\{externalUserId\}"):
        client.customers.get("ada@example.com")

    assert fake.last().url.endswith("/v1/customers/ada%40example.com")


def test_the_double_serves_an_async_client_too() -> None:
    fake = FakeTransport().push(200, data(run_result()), headers={"X-Request-Id": "req-1"})

    async def main() -> str | None:
        client = AsyncSlen(api_key=KEY, http_client=httpx.AsyncClient(transport=fake))
        run = await client.executions.get("74438200973594700")

        return run.request_id

    assert asyncio.run(main()) == "req-1"


def test_a_queued_failure_of_the_wire_is_raised_in_place_of_an_answer() -> None:
    error = httpx.ConnectError("refused")
    fake = FakeTransport().push_exception(error)

    with pytest.raises(httpx.ConnectError):
        httpx.Client(transport=fake).get("https://api.slen.ai/api/health")


def test_last_of_nothing_is_a_lookup_error() -> None:
    with pytest.raises(LookupError):
        FakeTransport().last()

    with pytest.raises(LookupError):
        MemorySpanRecorder().last()


def test_a_status_out_of_range_is_refused() -> None:
    with pytest.raises(ValueError, match="status"):
        FakeTransport().push(42)


def test_the_span_recorder_keeps_spans_in_order() -> None:
    recorder = MemorySpanRecorder()
    first, second = bare_span("operations.execute"), bare_span("executions.wait")

    recorder.record(first)
    recorder.record(second)

    assert recorder.spans == (first, second)
    assert recorder.last() is second

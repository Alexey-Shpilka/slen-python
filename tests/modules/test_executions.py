import asyncio
import dataclasses
import math
from typing import Any

import httpx
import pytest

from slen import (
    AsyncSlen,
    ConnectionError,
    CustomerNotFoundError,
    ExecutionStatus,
    InvalidRequestError,
    RateLimitError,
    SlenError,
)
from slen._http import _clock
from slen.testing import FakeTransport, MemorySpanRecorder
from support.harness import BASE, KEY, FakeClock, Kind, data, drive, raised, run_view, trace

RUN = "74438200973594700"
RUNNING = data(run_view(status="running", output=None))
LIMITED = {"error": {"code": "rate_limit_exceeded", "message": "API rate limit exceeded"}}


def test_get_reads_the_status_view_once(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_view()))

    run = drive(kind, fake, lambda slen: slen.executions.get(RUN))

    assert fake.last().url == f"{BASE}/v1/executions/{RUN}/status"
    assert run.is_completed()
    assert run.output == {"content": "Hello"}


def test_trace_reads_every_node_event_and_attempt(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(trace()), headers={"X-Request-Id": "req-t"})

    found = drive(kind, fake, lambda slen: slen.executions.trace(RUN))

    assert fake.last().url == f"{BASE}/v1/executions/{RUN}"
    assert found.status is ExecutionStatus.COMPLETED
    assert found.nodes[0].attempts[0].model_code == "gpt-4o-mini"
    assert found.nodes[0].metadata == {"tokens": 30}
    assert found.events[0].payload == {}
    assert found.duration_ms == 2000
    assert found.request_id == "req-t"


def test_a_trace_without_the_fields_the_spec_leaves_out_reads_them_as_none(kind: Kind) -> None:
    lean = {key: value for key, value in trace().items() if key not in ("flow_name", "operation", "finished_at")}
    fake = FakeTransport().push(200, data(lean))

    found = drive(kind, fake, lambda slen: slen.executions.trace(RUN))

    assert (found.flow_name, found.operation, found.finished_at) == (None, None, None)


def test_wait_reads_at_the_pace_it_doubles_until_the_run_is_over(kind: Kind, clock: FakeClock) -> None:
    fake = FakeTransport().push(200, RUNNING).push(200, RUNNING).push(200, RUNNING).push(200, data(run_view()))

    run = drive(kind, fake, lambda slen: slen.executions.wait(RUN))

    assert run.is_completed()
    assert len(fake.requests) == 4
    assert clock.slept == [1.0, 2.0, 4.0]


def test_wait_keeps_the_pace_the_server_asks_for(kind: Kind, clock: FakeClock) -> None:
    asked = data(run_view(status="queued", output=None, retry_after_seconds=3))
    fake = FakeTransport().push(200, asked).push(200, data(run_view()))

    drive(kind, fake, lambda slen: slen.executions.wait(RUN))

    assert clock.slept == [3.0]


def test_wait_answers_the_last_state_read_when_the_time_is_up(kind: Kind, clock: FakeClock) -> None:
    fake = FakeTransport()
    for _ in range(4):
        fake.push(200, RUNNING)

    run = drive(kind, fake, lambda slen: slen.executions.wait(RUN, timeout_seconds=6))

    assert run.status is ExecutionStatus.RUNNING
    assert clock.elapsed == 6
    assert clock.slept == [1.0, 2.0, 3.0]


def test_a_read_of_a_wait_is_sent_once_under_what_is_left_of_it(kind: Kind) -> None:
    class Reads(httpx.BaseTransport, httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.timeouts: list[object] = []

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            self.timeouts.append(request.extensions["timeout"]["read"])
            body = RUNNING if len(self.timeouts) < 3 else data(run_view())

            return httpx.Response(200, json=body)

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return self.handle_request(request)

    transport = Reads()

    drive(kind, transport, lambda slen: slen.executions.wait(RUN, timeout_seconds=8), timeout=30.0)

    assert transport.timeouts == [8.0, 7.0, 5.0]


def test_a_failed_read_is_told_and_the_wait_goes_on(kind: Kind) -> None:
    fake = FakeTransport().push(429, LIMITED).push(200, data(run_view()))
    told: list[tuple[str, int]] = []

    def listener(error: SlenError, failures: int) -> None:
        told.append((type(error).__name__, failures))

    run = drive(kind, fake, lambda slen: slen.executions.wait(RUN, on_poll_error=listener))

    assert run.is_completed()
    assert told == [("RateLimitError", 1)]
    assert len(fake.requests) == 2


def test_an_async_wait_awaits_a_coroutine_listener() -> None:
    fake = FakeTransport().push(503, {"error": {"code": "service_unavailable"}}).push(200, data(run_view()))
    told: list[int] = []

    async def listener(error: SlenError, failures: int) -> None:
        await asyncio.sleep(0)
        told.append(failures)

    async def main() -> None:
        client = AsyncSlen(api_key=KEY, http_client=httpx.AsyncClient(transport=fake))
        await client.executions.wait(RUN, on_poll_error=listener)

    asyncio.run(main())

    assert told == [1]


def test_what_the_listener_raises_ends_the_wait(kind: Kind) -> None:
    fake = FakeTransport().push(429, LIMITED)

    def listener(error: SlenError, failures: int) -> None:
        raise RuntimeError("stop")

    error = raised(kind, fake, lambda slen: slen.executions.wait(RUN, on_poll_error=listener))

    assert isinstance(error, RuntimeError)


def test_a_refusal_ends_the_wait_at_once(kind: Kind) -> None:
    fake = FakeTransport().push(404, {"error": {"code": "customer_not_found"}})

    assert isinstance(raised(kind, fake, lambda slen: slen.executions.wait(RUN)), CustomerNotFoundError)
    assert len(fake.requests) == 1


def test_a_wait_without_a_ceiling_gives_up_after_ten_failed_reads(kind: Kind) -> None:
    fake = FakeTransport()
    for _ in range(10):
        fake.push_exception(httpx.ConnectError("refused"))

    error = raised(kind, fake, lambda slen: slen.executions.wait(RUN, timeout_seconds=math.inf))

    assert isinstance(error, ConnectionError)
    assert len(fake.requests) == 10


def test_a_wait_that_never_read_a_state_raises_its_last_failure(kind: Kind) -> None:
    fake = FakeTransport()
    for _ in range(3):
        fake.push(429, LIMITED)

    error = raised(kind, fake, lambda slen: slen.executions.wait(RUN, timeout_seconds=2))

    assert isinstance(error, RateLimitError)


@pytest.mark.parametrize("given", ["", True, "300"])
def test_a_wait_is_checked_before_the_wire(kind: Kind, given: Any) -> None:
    fake = FakeTransport()
    options = {"timeout_seconds": given} if given != "" else {}
    execution_id = "" if given == "" else RUN

    error = raised(kind, fake, lambda slen: slen.executions.wait(execution_id, **options))

    assert isinstance(error, InvalidRequestError)
    assert fake.requests == ()


def test_a_wait_takes_no_request_id(kind: Kind) -> None:
    with pytest.raises(TypeError):
        drive(kind, FakeTransport(), lambda slen: slen.executions.wait(RUN, request_id="order-42:wait"))


def test_a_wait_writes_one_span_with_what_it_read(kind: Kind) -> None:
    fake = FakeTransport().push(200, RUNNING).push(200, data(run_view(cost={"estimated": "1.5", "actual": "1.4"})))
    spans = MemorySpanRecorder()

    drive(kind, fake, lambda slen: slen.executions.wait(RUN), span_recorder=spans)

    assert len(spans.spans) == 1
    span = spans.last()
    assert (span.operation, span.outcome, span.status, span.operation_code) == (
        "executions.wait",
        "ok",
        ExecutionStatus.COMPLETED,
        "support.answer",
    )
    assert (span.estimated, span.actual, span.cache_hit, span.duration_ms) == ("1.5", "1.4", False, 1000)


def test_a_wait_that_failed_writes_its_span_with_the_run(kind: Kind) -> None:
    fake = FakeTransport().push(404, {"error": {"code": "customer_not_found"}})
    spans = MemorySpanRecorder()

    raised(kind, fake, lambda slen: slen.executions.wait(RUN), span_recorder=spans)

    assert (spans.last().outcome, spans.last().execution_id, spans.last().error_code) == (
        "error",
        RUN,
        "customer_not_found",
    )


def test_a_cancelled_wait_stays_cancelled_and_reads_no_more(clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    async def forever(seconds: float) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(_clock, "SYSTEM_CLOCK", dataclasses.replace(clock.clock(), sleep_async=forever))
    fake = FakeTransport().push(200, RUNNING).push(200, RUNNING)

    async def main() -> None:
        client = AsyncSlen(api_key=KEY, http_client=httpx.AsyncClient(transport=fake))
        task = asyncio.create_task(client.executions.wait(RUN))

        while not fake.requests:
            await asyncio.sleep(0)

        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())

    assert len(fake.requests) == 1

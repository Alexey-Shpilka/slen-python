import httpx
import pytest

from slen import ConnectionError, ProviderError, RateLimitError, ServiceUnavailableError, TimeoutError
from slen._http._retry import backoff_ms, retry_after_ms
from slen.testing import FakeTransport
from support.harness import FakeClock, Kind, data, drive, raised, run_result, run_view

STATUS = "74438200973594700"
UNAVAILABLE = {"error": {"code": "service_unavailable", "message": "Down for a moment"}}


def get(slen: object) -> object:
    return slen.executions.get(STATUS)  # type: ignore[attr-defined]


def test_a_503_is_sent_again_after_a_pause_that_doubles(kind: Kind, clock: FakeClock) -> None:
    fake = FakeTransport().push(503, UNAVAILABLE).push(503, UNAVAILABLE).push(200, data(run_view()))

    drive(kind, fake, get)

    assert len(fake.requests) == 3
    assert clock.slept == [0.2, 0.4]


def test_a_429_waits_out_its_retry_after(kind: Kind, clock: FakeClock) -> None:
    fake = FakeTransport().push(429, {"error": {"code": "rate_limit_exceeded"}}, headers={"Retry-After": "2"})
    fake.push(200, data(run_view()))

    drive(kind, fake, get)

    assert clock.slept == [2.0]


def test_a_retry_after_given_as_a_date_is_read(kind: Kind, clock: FakeClock) -> None:
    fake = FakeTransport().push(503, UNAVAILABLE, headers={"Retry-After": "Sat, 17 Oct 2026 12:00:03 GMT"})
    fake.push(200, data(run_view()))

    drive(kind, fake, get)

    assert clock.slept == [3.0]


def test_a_retry_after_longer_than_thirty_seconds_comes_back_at_once(kind: Kind, clock: FakeClock) -> None:
    fake = FakeTransport().push(429, {"error": {"code": "rate_limit_exceeded"}}, headers={"Retry-After": "31"})

    error = raised(kind, fake, get)

    assert isinstance(error, RateLimitError)
    assert error.retry_after_seconds == 31
    assert len(fake.requests) == 1
    assert clock.slept == []


@pytest.mark.parametrize("status", [500, 502, 504])
def test_a_500_502_or_504_is_never_sent_again(kind: Kind, status: int) -> None:
    fake = FakeTransport().push(status, {"error": {"code": "provider_error", "message": "Upstream"}})

    assert isinstance(raised(kind, fake, get), ProviderError)
    assert len(fake.requests) == 1


def test_no_answer_is_sent_again_under_the_same_idempotency_key(kind: Kind) -> None:
    fake = FakeTransport().push_exception(httpx.ConnectError("refused")).push(200, data(run_result()))

    drive(kind, fake, lambda slen: slen.operations.execute("support.answer", {"messages": []}))

    keys = {request.headers["idempotency-key"] for request in fake.requests}
    assert len(fake.requests) == 2
    assert len(keys) == 1


def test_no_answer_after_every_attempt_is_a_connection_error_without_a_code(kind: Kind) -> None:
    fake = FakeTransport()
    for _ in range(3):
        fake.push_exception(httpx.ConnectError("refused"))

    error = raised(kind, fake, get)

    assert isinstance(error, ConnectionError)
    assert error.code is None
    assert error.status is None
    assert len(fake.requests) == 3


def test_a_read_timeout_of_the_wire_is_the_sdks_timeout_error(kind: Kind) -> None:
    fake = FakeTransport().push_exception(httpx.ReadTimeout("slow"))

    error = raised(kind, fake, get, retries=0)

    assert isinstance(error, TimeoutError)
    assert error.code is None


def test_retries_of_a_call_replace_the_clients(kind: Kind) -> None:
    fake = FakeTransport().push(503, UNAVAILABLE).push(503, UNAVAILABLE)

    error = raised(kind, fake, lambda slen: slen.executions.get(STATUS, retries=1), retries=5)

    assert isinstance(error, ServiceUnavailableError)
    assert len(fake.requests) == 2


def test_retries_zero_sends_a_call_once(kind: Kind) -> None:
    fake = FakeTransport().push(503, UNAVAILABLE)

    raised(kind, fake, get, retries=0)

    assert len(fake.requests) == 1


def test_the_pause_doubles_from_200_ms_to_at_most_5_s() -> None:
    assert [backoff_ms(retried, lambda: 0.5) for retried in range(7)] == [200, 400, 800, 1600, 3200, 5000, 5000]
    assert backoff_ms(0, lambda: 0.0) == 150
    assert backoff_ms(0, lambda: 1.0) == 250


def test_a_retry_after_is_seconds_or_a_date() -> None:
    now = 1_792_238_400.0

    assert retry_after_ms("3", now) == 3000
    assert retry_after_ms(" 3 ", now) == 3000
    assert retry_after_ms("Sat, 17 Oct 2026 12:00:05 GMT", now) == 5000
    assert retry_after_ms("Sat, 17 Oct 2026 11:00:00 GMT", now) == 0
    assert retry_after_ms("soon", now) is None
    assert retry_after_ms("", now) is None
    assert retry_after_ms(None, now) is None
    assert retry_after_ms("\u0663", now) is None

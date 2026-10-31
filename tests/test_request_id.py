import httpx
import pytest

from slen import ConnectionError, InvalidRequestError, RateLimitError, ServiceUnavailableError
from slen.testing import FakeTransport
from support.harness import Kind, account, customer, data, drive, raised, run_view

STATUS = "74438200973594700"
UNAVAILABLE = {"error": {"code": "service_unavailable", "message": "Down"}}


def test_a_callers_id_goes_out_on_every_attempt_of_the_call(kind: Kind) -> None:
    fake = FakeTransport().push(503, UNAVAILABLE).push(503, UNAVAILABLE).push(200, data(run_view()))

    drive(kind, fake, lambda slen: slen.executions.get(STATUS, request_id="order-42:status"))

    assert [request.headers["x-request-id"] for request in fake.requests] == ["order-42:status"] * 3


def test_a_callers_id_replaces_the_one_of_the_clients_headers(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_view())).push(200, data(run_view()))
    headers = {"X-Request-Id": "client-wide-id", "X-Team": "billing"}

    drive(kind, fake, lambda slen: slen.executions.get(STATUS, request_id="call-own-id"), headers=headers)
    drive(kind, fake, lambda slen: slen.executions.get(STATUS), headers=headers)

    assert [request.headers["x-request-id"] for request in fake.requests] == ["call-own-id", "client-wide-id"]
    assert fake.last().headers["x-team"] == "billing"


@pytest.mark.parametrize("given", ["short", "has space in it", "x" * 129, "ünïcode-id", "", 42])
def test_a_malformed_id_is_refused_before_the_wire(kind: Kind, given: object) -> None:
    fake = FakeTransport()

    error = raised(kind, fake, lambda slen: slen.customers.get("user 42", request_id=given))

    assert isinstance(error, InvalidRequestError)
    assert "8 to 128" in str(error)
    assert fake.requests == ()


def test_an_answer_carries_the_id_of_its_response(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(customer()), headers={"X-Request-Id": "resp-1"})

    found = drive(kind, fake, lambda slen: slen.customers.get("user 42"))

    assert found.request_id == "resp-1"
    assert found.accounts[0].request_id is None


def test_the_id_of_an_answer_takes_no_part_in_equality(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(account()), headers={"X-Request-Id": "a"})
    fake.push(200, data(account()), headers={"X-Request-Id": "b"})

    first = drive(kind, fake, lambda slen: slen.customers.top_up("user 42", "5", idempotency_key="k-1"))
    second = drive(kind, fake, lambda slen: slen.customers.top_up("user 42", "5", idempotency_key="k-1"))

    assert first == second
    assert first.request_id != second.request_id


def test_an_error_with_no_answer_carries_the_callers_id(kind: Kind) -> None:
    fake = FakeTransport().push_exception(httpx.ConnectError("refused"))

    error = raised(kind, fake, lambda slen: slen.customers.get("user 42", retries=0, request_id="order-42:get"))

    assert isinstance(error, ConnectionError)
    assert error.request_id == "order-42:get"


def test_an_answer_with_another_id_has_the_last_word(kind: Kind) -> None:
    fake = FakeTransport().push(503, UNAVAILABLE, headers={"X-Request-Id": "server-id"})

    error = raised(kind, fake, lambda slen: slen.customers.get("user 42", retries=0, request_id="order-42:get"))

    assert isinstance(error, ServiceUnavailableError)
    assert error.request_id == "server-id"


def test_an_error_reads_the_header_first_then_the_body(kind: Kind) -> None:
    body = {"error": {"code": "rate_limit_exceeded", "request_id": "from-the-body"}}
    fake = FakeTransport().push(429, body, headers={"X-Request-Id": "from-the-header"}).push(429, body)

    first = raised(kind, fake, lambda slen: slen.customers.get("user 42", retries=0))
    second = raised(kind, fake, lambda slen: slen.customers.get("user 42", retries=0))

    assert isinstance(first, RateLimitError)
    assert isinstance(second, RateLimitError)
    assert (first.request_id, second.request_id) == ("from-the-header", "from-the-body")


def test_wait_answers_the_id_of_its_last_read(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_view(status="running")), headers={"X-Request-Id": "read-1"})
    fake.push(200, data(run_view()), headers={"X-Request-Id": "read-2"})

    finished = drive(kind, fake, lambda slen: slen.executions.wait(STATUS))

    assert finished.request_id == "read-2"
    assert "x-request-id" not in fake.last().headers

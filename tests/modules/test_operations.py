import uuid
from collections.abc import Callable
from typing import Any

import pytest

from slen import (
    ExecutionResult,
    ExecutionStatus,
    InvalidRequestError,
    InvalidResponseError,
    SpendRefusedError,
)
from slen.testing import FakeTransport, MemorySpanRecorder
from support.harness import BASE, Kind, data, drive, raised, run_result

INPUT = {"messages": [{"role": "user", "content": "Where is my order?"}]}


def execute(**options: Any) -> Callable[[Any], Any]:
    def action(slen: Any) -> Any:
        return slen.operations.execute("support.answer", INPUT, **options)

    return action


def test_execute_sends_the_operation_the_input_and_the_context(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_result()))

    drive(
        kind,
        fake,
        execute(customer="user_8421", credit_type="enrichment", context={"plan": "pro"}, idempotency_key="t-42:reply"),
    )
    sent = fake.last()

    assert (sent.method, sent.url) == ("POST", f"{BASE}/v1/operations/execute")
    assert sent.body == {
        "operation": "support.answer",
        "input": INPUT,
        "context": {"plan": "pro", "user_id": "user_8421", "credit_type": "enrichment"},
    }
    assert sent.headers["idempotency-key"] == "t-42:reply"
    assert sent.headers["authorization"] == "Bearer key-for-tests"
    assert sent.headers["accept"] == "application/json"
    assert sent.headers["user-agent"].startswith("slen-sdk-python/0.4.0 python/")


def test_execute_without_options_sends_no_context_and_a_generated_key(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_result()))

    drive(kind, fake, execute())

    assert fake.last().body == {"operation": "support.answer", "input": INPUT}
    assert uuid.UUID(fake.last().headers["idempotency-key"]).version == 4


def test_an_empty_context_is_sent_as_one(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_result()))

    drive(kind, fake, execute(context={}))

    assert fake.last().body["context"] == {}


def test_execute_async_asks_for_a_worker(kind: Kind) -> None:
    fake = FakeTransport().push(202, data(run_result(status="queued", output=None, retry_after_seconds=2)))

    run = drive(kind, fake, lambda slen: slen.operations.execute_async("support.answer", INPUT))

    assert fake.last().body["execution_mode"] == "async"
    assert run.status is ExecutionStatus.QUEUED
    assert run.retry_after_seconds == 2
    assert run.is_pending()


def test_the_answer_is_read_into_its_type(kind: Kind) -> None:
    body = run_result(
        status="rejected",
        output=None,
        error={"code": "budget_exceeded", "message": "Budget 7 (monthly) exceeded"},
        error_code="budget_exceeded",
        error_message="Budget 7 (monthly) exceeded",
        replayed=True,
        waiting_on={"node_key": "gate", "type": "approval", "resume_at": "2026-10-17T12:00:00Z"},
        cache={"hit": False, "cached_at": "2026-10-17T11:00:00+02:00"},
    )
    fake = FakeTransport().push(200, data(body), headers={"X-Request-Id": "req-1"})

    run: ExecutionResult = drive(kind, fake, execute())

    assert run.is_rejected()
    assert not run.is_completed()
    assert run.is_finished()
    assert run.error is not None
    assert (run.error.code, run.error_code, run.replayed) == ("budget_exceeded", "budget_exceeded", True)
    assert run.waiting_on is not None
    assert run.waiting_on.resume_at is not None
    assert run.waiting_on.resume_at.utcoffset() is not None
    assert run.cache.cached_at is not None
    assert run.cache.cached_at.isoformat() == "2026-10-17T11:00:00+02:00"
    assert run.cost.estimated == "0.00412500"
    assert run.request_id == "req-1"
    assert str(run.status) == "rejected"


@pytest.mark.parametrize(
    ("options", "words"),
    [
        ({"customer": ""}, "`customer`"),
        ({"credit_type": "  "}, "`credit_type`"),
        ({"customer": "user_1", "context": {"user_id": "user_2"}}, "two different values"),
        ({"customer": "42", "context": {"user_id": None}}, "two different values"),
        ({"idempotency_key": ""}, "idempotency key"),
        ({"timeout": 0}, "timeout"),
        ({"timeout": True}, "timeout"),
        ({"retries": -1}, "retries"),
        ({"retries": 1.0}, "retries"),
    ],
)
def test_a_call_refused_before_the_wire_sends_nothing_and_writes_no_span(
    kind: Kind, options: dict[str, Any], words: str
) -> None:
    fake = FakeTransport()
    spans = MemorySpanRecorder()

    error = raised(kind, fake, execute(**options), span_recorder=spans)

    assert isinstance(error, InvalidRequestError)
    assert words in str(error)
    assert fake.requests == ()
    assert spans.spans == ()


def test_the_same_customer_in_the_context_is_one_customer(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_result()))

    drive(kind, fake, execute(customer="42", context={"user_id": 42}))

    assert fake.last().body["context"] == {"user_id": "42"}


def test_a_refusal_of_money_is_its_typed_error(kind: Kind) -> None:
    body = {"error": {"code": "insufficient_credits", "message": "Cannot cover", "request_id": "r-9"}}
    fake = FakeTransport().push(402, body)

    error = raised(kind, fake, execute())

    assert isinstance(error, SpendRefusedError)
    assert (error.code, error.status, error.request_id) == ("insufficient_credits", 402, "r-9")


@pytest.mark.parametrize(
    ("body", "words"),
    [
        (data(run_result(status="invented")), "`data.status`"),
        (data(run_result(execution_id=7)), "`data.execution_id`"),
        (data({k: v for k, v in run_result().items() if k != "trace_url"}), "`data.trace_url` is missing"),
        (data(run_result(cost=None)), "`data.cost`"),
        (data(run_result(output=[1])), "`data.output`"),
        ({"result": run_result()}, "no `data`"),
        (data(run_result(cache={"hit": False, "cached_at": "yesterday"})), "`data.cache.cached_at`"),
    ],
)
def test_an_answer_that_cannot_be_read_is_an_invalid_response(kind: Kind, body: dict[str, Any], words: str) -> None:
    fake = FakeTransport().push(200, body)

    error = raised(kind, fake, execute())

    assert isinstance(error, InvalidResponseError)
    assert error.code == "invalid_response"
    assert error.status == 200
    assert words in str(error)
    assert "Where is my order" not in str(error)


def test_an_empty_list_of_the_backend_is_an_empty_output(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_result(output=[])))

    run = drive(kind, fake, execute())

    assert run.output == {}


def test_a_204_to_a_call_that_reads_an_answer_is_an_invalid_response(kind: Kind) -> None:
    fake = FakeTransport().push(204)

    error = raised(kind, fake, execute())

    assert isinstance(error, InvalidResponseError)
    assert error.status == 204

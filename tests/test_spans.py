import dataclasses
import json
import logging
import re
from typing import Any, Final

import pytest

from slen import ExecutionStatus, LoggerSpanRecorder, SlenSpan
from slen._observability._span import SPAN_OPERATIONS, attributes_of
from slen.testing import FakeTransport, MemorySpanRecorder
from support.harness import Kind, RecordingLogger, RecordsHandler, account, data, drive, raised, run_result
from support.paths import CONTRACT

CONTRACT_SPANS: Final[dict[str, Any]] = json.loads((CONTRACT / "span-attributes.json").read_text(encoding="utf-8"))

# A name that looks as if it could hold what was said to a model.
SAID: Final = re.compile(r"prompt|message|input|output|content|text|completion|body|payload", re.IGNORECASE)


def a_span(**changes: Any) -> SlenSpan:
    fields: dict[str, Any] = {
        "operation": "operations.execute",
        "outcome": "ok",
        "status": ExecutionStatus.COMPLETED,
        "duration_ms": 12,
        "execution_id": "74438200973594700",
        "operation_code": "support.answer",
        "estimated": "0.004",
        "actual": None,
        "error_code": None,
        "cache_hit": False,
    }

    return SlenSpan(**{**fields, **changes})


def test_the_fields_of_a_span_are_the_attributes_of_the_contract_in_its_order() -> None:
    assert [field.name for field in dataclasses.fields(SlenSpan)] == [
        line["attribute"] for line in CONTRACT_SPANS["fields"]
    ]


def test_no_field_of_a_span_could_carry_a_prompt() -> None:
    assert [field.name for field in dataclasses.fields(SlenSpan) if SAID.search(field.name)] == []


def test_the_names_of_spans_are_the_contracts() -> None:
    assert set(SPAN_OPERATIONS) == set(CONTRACT_SPANS["operations"])
    assert all("python" in line["sdks"] for line in CONTRACT_SPANS["operations"].values())


def test_an_attribute_that_is_none_is_left_out_and_false_is_kept() -> None:
    assert attributes_of(a_span()) == {
        "operation": "operations.execute",
        "outcome": "ok",
        "status": "completed",
        "duration_ms": 12,
        "execution_id": "74438200973594700",
        "operation_code": "support.answer",
        "estimated": "0.004",
        "cache_hit": False,
    }


@pytest.mark.parametrize(
    ("status", "outcome"),
    [("completed", "ok"), ("rejected", "refused"), ("failed", "error"), ("uncertain", "error"), ("queued", "ok")],
)
def test_the_outcome_of_a_run_is_read_off_its_status(kind: Kind, status: str, outcome: str) -> None:
    fake = FakeTransport().push(200, data(run_result(status=status, error_code=None)))
    spans = MemorySpanRecorder()

    drive(kind, fake, lambda slen: slen.operations.execute("support.answer", {}), span_recorder=spans)

    assert spans.last().outcome == outcome
    assert spans.last().cache_hit is (None if status == "queued" else False)


@pytest.mark.parametrize(
    ("status", "code", "outcome"),
    [(402, "budget_exceeded", "refused"), (403, "customer_blocked", "refused"), (401, "invalid_api_key", "error")],
)
def test_a_thrown_refusal_of_money_or_policy_is_refused(kind: Kind, status: int, code: str, outcome: str) -> None:
    fake = FakeTransport().push(status, {"error": {"code": code}})
    spans = MemorySpanRecorder()

    raised(kind, fake, lambda slen: slen.operations.execute("support.answer", {}), span_recorder=spans)

    assert (spans.last().outcome, spans.last().error_code, spans.last().operation_code) == (
        outcome,
        code,
        "support.answer",
    )


def test_the_span_is_named_by_the_call_not_the_answer(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(run_result(replayed=True)))
    spans = MemorySpanRecorder()

    drive(kind, fake, lambda slen: slen.operations.execute_async("support.answer", {}), span_recorder=spans)

    assert spans.last().operation == "operations.execute_async"
    assert spans.last().status is ExecutionStatus.COMPLETED


def test_customers_and_reads_write_no_span(kind: Kind) -> None:
    fake = FakeTransport().push(200, data(account())).push(200, data(run_result()))
    spans = MemorySpanRecorder()

    drive(kind, fake, lambda slen: slen.customers.top_up("user 42", "5"), span_recorder=spans)
    drive(kind, fake, lambda slen: slen.executions.get("74438200973594700"), span_recorder=spans)

    assert spans.spans == ()


def test_a_recorder_that_raises_does_not_fail_the_call(kind: Kind) -> None:
    class Broken:
        def record(self, span: SlenSpan) -> None:
            raise RuntimeError(span.operation)

    fake = FakeTransport().push(200, data(run_result()))

    run = drive(kind, fake, lambda slen: slen.operations.execute("support.answer", {}), span_recorder=Broken())

    assert run.is_completed()


def test_the_logger_recorder_writes_one_line_with_the_attributes_as_fields() -> None:
    logger = RecordingLogger()

    LoggerSpanRecorder(logger).record(a_span())
    LoggerSpanRecorder(logger, level=logging.DEBUG).record(a_span(outcome="error"))

    assert [(entry.event, entry.level) for entry in logger.entries] == [("slen.span", "info"), ("slen.span", "debug")]
    assert logger.entries[0].fields == attributes_of(a_span())


def test_the_logger_recorder_reaches_a_record_of_the_standard_library() -> None:
    handler = RecordsHandler()
    logger = logging.getLogger("spans-under-test")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    LoggerSpanRecorder(logger).record(a_span())
    logger.removeHandler(handler)

    assert vars(handler.records[0])["operation_code"] == "support.answer"


def test_the_logger_recorder_takes_a_level_of_the_four() -> None:
    with pytest.raises(ValueError, match="level"):
        LoggerSpanRecorder(RecordingLogger(), level=logging.CRITICAL)

    with pytest.raises(TypeError):
        LoggerSpanRecorder(object())  # type: ignore[arg-type]

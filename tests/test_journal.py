import logging
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from slen import LOG_EVENTS, Webhooks
from slen._logger import LEVELS, LOGGER_NAME
from slen.testing import FakeTransport
from support.harness import Kind, RecordingLogger, RecordsHandler, account, data, drive, raised, run_result

# Values a journal must never carry, each planted where a call puts it.
API_KEY = "sl_live_planted_key_value"
PATH_VALUE = "ada@planted.example"
QUERY_VALUE = "planted-search-text"
IDEMPOTENCY_KEY = "planted-idempotency-key"
BODY_VALUE = "planted words of a prompt"
SERVER_MESSAGE = "planted message of the server"
WEBHOOK_SECRET = "whsec_planted_secret"
PLANTED = (API_KEY, PATH_VALUE, QUERY_VALUE, IDEMPOTENCY_KEY, BODY_VALUE, SERVER_MESSAGE, WEBHOOK_SECRET)

# The attributes of a record of the standard library: no field of the journal may be one of them.
RECORD_ATTRIBUTES = frozenset(vars(logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None))) | {
    "message",
    "asctime",
    "taskName",
}


@pytest.fixture
def records() -> Iterator[RecordsHandler]:
    handler = RecordsHandler()
    logger = logging.getLogger("journal-under-test")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    yield handler

    logger.removeHandler(handler)


def every_call(kind: Kind, logger: Any) -> None:
    fake = FakeTransport()
    fake.push_exception(httpx.ConnectError("refused"))
    fake.push(200, data(run_result()))
    fake.push(402, {"error": {"code": "insufficient_credits", "message": SERVER_MESSAGE}})
    fake.push(200, {"data": [], "meta": {"limit": 50, "next_cursor": None}})
    fake.push(500, {"error": {"code": "provider_error", "message": SERVER_MESSAGE}})
    fake.push(401, {"error": {"code": "invalid_api_key", "message": SERVER_MESSAGE}})
    options = {"api_key": API_KEY, "logger": logger, "webhook_secret": WEBHOOK_SECRET}
    run = {"messages": [{"role": "user", "content": BODY_VALUE}]}

    drive(
        kind,
        fake,
        lambda slen: slen.operations.execute("support.answer", run, idempotency_key=IDEMPOTENCY_KEY),
        **options,
    )
    raised(kind, fake, lambda slen: slen.customers.charge(PATH_VALUE, "5", idempotency_key=IDEMPOTENCY_KEY), **options)
    drive(kind, fake, lambda slen: slen.customers.list(search=QUERY_VALUE), **options)
    raised(kind, fake, lambda slen: slen.customers.get(PATH_VALUE), **options)
    raised(kind, fake, lambda slen: slen.customers.get(PATH_VALUE), **options)
    Webhooks(secret=WEBHOOK_SECRET, logger=logger).verify(BODY_VALUE, "t=1,v1=" + "0" * 64)


def test_the_journal_carries_no_key_secret_body_message_or_value(kind: Kind, records: RecordsHandler) -> None:
    every_call(kind, logging.getLogger("journal-under-test"))
    written = [str(value) for record in records.records for value in vars(record).values()]

    assert len(records.records) > 10
    assert [planted for planted in PLANTED if any(planted in text for text in written)] == []


def test_the_fields_of_the_journal_are_none_of_the_attributes_of_a_record(kind: Kind) -> None:
    logger = RecordingLogger()
    every_call(kind, logger)
    fields = {name for entry in logger.entries for name in entry.fields}

    assert fields & RECORD_ATTRIBUTES == set()
    assert {"method", "route", "attempt", "status", "duration_ms", "request_id", "reason", "delay_ms"} <= fields


def test_the_fields_reach_a_record_of_the_standard_library(records: RecordsHandler) -> None:
    fake = FakeTransport().push(200, data(account()))
    logger = logging.getLogger("journal-under-test")

    drive("sync", fake, lambda slen: slen.customers.top_up("user 42", "5", idempotency_key="k-1"), logger=logger)
    response = next(record for record in records.records if record.getMessage() == "slen.response")

    assert response.levelno == logging.DEBUG
    assert vars(response)["route"] == "/v1/customers/{externalUserId}/topup"
    assert vars(response)["method"] == "POST"
    assert vars(response)["status"] == 200


def test_each_event_is_written_at_its_level(kind: Kind) -> None:
    logger = RecordingLogger()
    every_call(kind, logger)
    levels = {(entry.event, entry.level) for entry in logger.entries}

    assert levels <= {(event, LEVELS[event]) for event in LOG_EVENTS}
    assert ("slen.retry", "warning") in levels
    assert ("slen.refused", "info") in levels
    assert ("slen.unauthorized", "error") in levels
    assert ("slen.failed", "error") in levels
    assert ("slen.webhook.rejected", "warning") in levels


def test_a_failure_names_the_contracts_type_and_the_attempts(kind: Kind) -> None:
    logger = RecordingLogger()
    fake = FakeTransport().push(500, {"error": {"code": "provider_error", "message": "x"}})

    raised(kind, fake, lambda slen: slen.customers.get("user 42"), logger=logger)
    failed = next(entry for entry in logger.entries if entry.event == "slen.failed")

    assert failed.fields["error_type"] == "Provider"
    assert failed.fields["attempts"] == 1
    assert failed.fields["error_code"] == "provider_error"


def test_a_logger_that_raises_does_not_fail_the_call(kind: Kind) -> None:
    class Broken:
        def debug(self, msg: str, /, **_: object) -> None:
            raise RuntimeError(msg)

        info = warning = error = debug

    fake = FakeTransport().push(200, data(run_result()))

    run = drive(kind, fake, lambda slen: slen.operations.execute("support.answer", {}), logger=Broken())

    assert run.execution_id == "74438200973594700"


def test_the_default_journal_is_the_slen_logger_which_drops_records_unless_configured() -> None:
    logger = logging.getLogger(LOGGER_NAME)

    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)

"""floor.py: the installed package, not the source, taken through what leans on the runtime and on httpx.

Run in an environment where the wheel is installed (not editable), on the floor of the package — Python 3.11 and
httpx 0.27. A retry, the journal, a run and its wait with their spans, a page and every page of a loop, a 204, the
id of a response, the async client, and every webhook vector. Exit 0, or the first failure as a traceback.
"""

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

import slen
from slen import AsyncSlen, ExecutionStatus, InvalidRequestError, Slen, Webhooks
from slen.testing import FakeTransport, MemorySpanRecorder

ROOT = Path(__file__).resolve().parents[1]
RUN: dict[str, Any] = {
    "execution_id": "74438200973594700",
    "status": "completed",
    "operation": "support.answer",
    "output": {"content": "Hello"},
    "error": None,
    "error_code": None,
    "error_message": None,
    "cost": {"estimated": "0.004", "actual": None},
    "cache": {"hit": False, "cached_at": None},
    "replayed": False,
    "waiting_on": None,
    "trace_url": "/v1/executions/74438200973594700",
}
ACCOUNT: dict[str, Any] = {
    "customer_account_id": "1",
    "customer_id": "1",
    "project_id": "1",
    "external_user_id": "user 42",
    "credit_type": "default",
    "balance": "1.0000",
    "reserved": "0.0000",
    "available": "1.0000",
    "allow_negative": False,
    "low_balance_threshold": "0",
    "created_at": "2026-10-17T09:00:00+00:00",
    "updated_at": "2026-10-17T09:00:00+00:00",
}
ENTRY: dict[str, Any] = {
    "entry_id": "1",
    "customer_account_id": "1",
    "external_user_id": "user 42",
    "credit_type": "default",
    "entry_type": "topup",
    "credits": "1.0000",
    "balance_after": "1.0000",
    "available_after": "1.0000",
    "reservation_id": None,
    "note": None,
    "created_at": "2026-10-17T09:00:00+00:00",
}


class Journal(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.events: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.events.append(record.getMessage())


def installed() -> None:
    where = Path(slen.__file__).resolve()

    assert ROOT / "src" not in where.parents, f"slen is imported from the source, {where}"
    assert (where.parent / "py.typed").is_file(), "the wheel carries no py.typed"
    print(f"slen {slen.__version__} from {where.parent}, httpx {httpx.__version__}, Python {sys.version.split()[0]}")


def sync_client() -> None:
    fake = FakeTransport()
    fake.push(503, {"error": {"code": "service_unavailable"}}).push(200, {"data": RUN}, headers={"X-Request-Id": "r-1"})
    fake.push(200, {"data": {**RUN, "status": "running", "retry_after_seconds": 0}}).push(200, {"data": RUN})
    fake.push(200, {"data": [ENTRY], "meta": {"limit": 1, "next_cursor": "c1"}})
    fake.push(200, {"data": [ENTRY], "meta": {"limit": 1, "next_cursor": None}})
    fake.push(204)
    spans = MemorySpanRecorder()
    journal = Journal()
    logger = logging.getLogger("floor")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(journal)

    with Slen(
        api_key="key-for-the-floor", http_client=httpx.Client(transport=fake), logger=logger, span_recorder=spans
    ) as client:
        run = client.operations.execute("support.answer", {"messages": []}, idempotency_key="floor-1:run")
        waited = client.executions.wait(run.execution_id, timeout_seconds=10)
        rows = list(client.customers.entries_all("user 42", limit=1))
        client.customers.delete("user 42")

    assert run.request_id == "r-1" and run.status is ExecutionStatus.COMPLETED
    assert waited.is_completed()
    assert len(rows) == 2
    assert fake.last().method == "DELETE"
    assert [span.operation for span in spans.spans] == ["operations.execute", "executions.wait"]
    assert "slen.retry" in journal.events and "slen.response" in journal.events
    keys = {request.headers["idempotency-key"] for request in fake.requests[:2]}
    assert keys == {"floor-1:run"}
    print("the sync client: a retry, the journal, a run and its wait, a loop, a 204")


def async_client() -> None:
    fake = FakeTransport().push(200, {"data": ACCOUNT}, headers={"X-Request-Id": "r-2"})

    async def main() -> str | None:
        async with AsyncSlen(api_key="key-for-the-floor", http_client=httpx.AsyncClient(transport=fake)) as client:
            account = await client.customers.top_up("user 42", "1.0000", idempotency_key="floor-2:topup")

            return account.request_id

    assert asyncio.run(main()) == "r-2"
    print("the async client: a movement and the id of its response")


def refusal() -> None:
    try:
        Slen(api_key="key-for-the-floor").customers.top_up("user 42", "0")
    except InvalidRequestError:
        print("a refusal before the wire")
        return

    raise AssertionError("credits of zero were not refused")


def webhook_vectors() -> None:
    vectors = json.loads((ROOT / "contract" / "webhook-vectors.json").read_text(encoding="utf-8"))
    webhooks = Webhooks(secret=vectors["secret"], tolerance_seconds=vectors["tolerance_seconds"])

    for case in vectors["cases"]:
        now = datetime.fromtimestamp(case["now"], tz=UTC)

        assert webhooks.verify(case["payload"], case["header"], now=now) is case["valid"], case["name"]

    print(f"{len(vectors['cases'])} webhook vectors")


if __name__ == "__main__":
    installed()
    sync_client()
    async_client()
    refusal()
    webhook_vectors()

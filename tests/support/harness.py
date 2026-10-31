import asyncio
import inspect
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import httpx

from slen import AsyncSlen, Slen, SlenSpan
from slen._http._clock import Clock

KEY: Final = "key-for-tests"
BASE: Final = "https://api.slen.ai/api"

Kind = Literal["sync", "async"]
KINDS: Final[tuple[Kind, ...]] = ("sync", "async")


@dataclass
class FakeClock:
    """A clock that moves only when the SDK sleeps; the jitter is always the middle of its range."""

    moment: float = 1_792_238_400.0
    elapsed: float = 0.0
    slept: list[float] = field(default_factory=list[float])

    def monotonic(self) -> float:
        return self.elapsed

    def now(self) -> float:
        return self.moment + self.elapsed

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.elapsed += seconds

    async def sleep_async(self, seconds: float) -> None:
        self.sleep(seconds)

    def clock(self) -> Clock:
        return Clock(
            monotonic=self.monotonic,
            now=self.now,
            random=lambda: 0.5,
            sleep=self.sleep,
            sleep_async=self.sleep_async,
        )


@dataclass(frozen=True)
class Entry:
    level: str
    event: str
    fields: Mapping[str, object]


class RecordingLogger:
    """A SlenLogger that keeps what it is told."""

    def __init__(self) -> None:
        self.entries: list[Entry] = []

    def _keep(self, level: str, msg: str, extra: Mapping[str, object] | None) -> None:
        self.entries.append(Entry(level, msg, dict(extra or {})))

    def debug(self, msg: str, /, *, extra: Mapping[str, object] | None = None) -> None:
        self._keep("debug", msg, extra)

    def info(self, msg: str, /, *, extra: Mapping[str, object] | None = None) -> None:
        self._keep("info", msg, extra)

    def warning(self, msg: str, /, *, extra: Mapping[str, object] | None = None) -> None:
        self._keep("warning", msg, extra)

    def error(self, msg: str, /, *, extra: Mapping[str, object] | None = None) -> None:
        self._keep("error", msg, extra)

    def events(self) -> list[str]:
        return [entry.event for entry in self.entries]


class RecordsHandler(logging.Handler):
    """A handler of the standard library that keeps every record."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def sync_client(fake: httpx.BaseTransport, **options: Any) -> Slen:
    merged: dict[str, Any] = {"api_key": KEY, **options}

    return Slen(**merged, http_client=httpx.Client(transport=fake))


def async_client(fake: httpx.AsyncBaseTransport, **options: Any) -> AsyncSlen:
    merged: dict[str, Any] = {"api_key": KEY, **options}

    return AsyncSlen(**merged, http_client=httpx.AsyncClient(transport=fake))


def drive(kind: Kind, fake: Any, action: Callable[[Any], Any], **options: Any) -> Any:
    """Runs one action on a client of either kind over the fake; an awaitable it answers is awaited."""
    if kind == "sync":
        return action(sync_client(fake, **options))

    async def main() -> Any:
        answer = action(async_client(fake, **options))

        return await answer if inspect.isawaitable(answer) else answer

    return asyncio.run(main())


def raised(kind: Kind, fake: Any, action: Callable[[Any], Any], **options: Any) -> BaseException:
    """The exception one action raises, on a client of either kind."""
    try:
        drive(kind, fake, action, **options)
    except BaseException as error:
        return error

    raise AssertionError("nothing was raised")


def collect(rows: Iterator[Any] | AsyncIterator[Any]) -> list[Any] | Awaitable[list[Any]]:
    """Every row of a loop of either kind: a list, or an awaitable of one."""
    if isinstance(rows, Iterator):
        return list(rows)

    async def gather() -> list[Any]:
        return [row async for row in rows]

    return gather()


def run_view(**changes: Any) -> dict[str, Any]:
    view: dict[str, Any] = {
        "execution_id": "74438200973594700",
        "status": "completed",
        "operation": "support.answer",
        "output": {"content": "Hello"},
        "error_code": None,
        "error_message": None,
        "cost": {"estimated": "0.00412500", "actual": None},
        "cache": {"hit": False, "cached_at": None},
        "waiting_on": None,
        "trace_url": "/v1/executions/74438200973594700",
    }

    return {**view, **changes}


def run_result(**changes: Any) -> dict[str, Any]:
    return run_view(**{"error": None, "replayed": False, **changes})


def account(**changes: Any) -> dict[str, Any]:
    held: dict[str, Any] = {
        "customer_account_id": "74438200973595100",
        "customer_id": "74438200973595100",
        "project_id": "74438200973590001",
        "external_user_id": "user 42",
        "credit_type": "default",
        "balance": "100.0000",
        "reserved": "0.0000",
        "available": "100.0000",
        "allow_negative": False,
        "low_balance_threshold": "10.0000",
        "created_at": "2026-10-17T09:05:00+00:00",
        "updated_at": "2026-10-17T09:05:00+00:00",
    }

    return {**held, **changes}


def customer(**changes: Any) -> dict[str, Any]:
    held: dict[str, Any] = {
        "customer_id": "74438200973595100",
        "external_user_id": "user 42",
        "status": "active",
        "blocked_at": None,
        "block_reason": None,
        "accounts": [account()],
        "created_at": "2026-10-17T09:00:00+00:00",
        "updated_at": "2026-10-17T09:05:00+00:00",
    }

    return {**held, **changes}


def entry(**changes: Any) -> dict[str, Any]:
    held: dict[str, Any] = {
        "entry_id": "74438200973595202",
        "customer_account_id": "74438200973595100",
        "external_user_id": "user 42",
        "credit_type": "default",
        "entry_type": "charge",
        "credits": "-5.0000",
        "balance_after": "95.0000",
        "available_after": "95.0000",
        "reservation_id": None,
        "note": "PDF export",
        "created_at": "2026-10-17T09:10:00+00:00",
    }

    return {**held, **changes}


def price(**changes: Any) -> dict[str, Any]:
    held: dict[str, Any] = {
        "credit_price_id": "74438200973596001",
        "project_id": "74438200973590001",
        "operation_code": "support.answer",
        "credit_type": "default",
        "credits": "2.0000",
        "created_at": "2026-10-17T09:00:00+00:00",
        "updated_at": "2026-10-17T09:00:00+00:00",
    }

    return {**held, **changes}


def trace(**changes: Any) -> dict[str, Any]:
    held: dict[str, Any] = {
        "execution_id": "74438200973594700",
        "flow_id": "74438200973590001",
        "flow_version_id": "74438200973590002",
        "flow_name": "Support",
        "operation": "support.answer",
        "operation_id": "74438200973590003",
        "status": "completed",
        "error_code": None,
        "error_message": None,
        "cost": {"estimated": "0.00412500", "actual": "0.00401000"},
        "cache": {"hit": False, "cached_at": None},
        "started_at": "2026-10-17T12:00:00+00:00",
        "finished_at": "2026-10-17T12:00:02+00:00",
        "duration_ms": 2000,
        "nodes": [
            {
                "node_key": "answer",
                "node_type": "ai_model",
                "status": "completed",
                "output_port": "out",
                "cost": "0.00401000",
                "duration_ms": 1900,
                "started_at": "2026-10-17T12:00:00+00:00",
                "finished_at": "2026-10-17T12:00:02+00:00",
                "metadata": {"tokens": 30},
                "attempts": [
                    {
                        "attempt_id": "74438200973597001",
                        "attempt_number": 1,
                        "connection_id": "74438200973598001",
                        "pool_id": None,
                        "status": "succeeded",
                        "error_code": None,
                        "latency_ms": 1800,
                        "cost": "0.00401000",
                        "provider_request_id": "req_provider",
                        "model_code": "gpt-4o-mini",
                    }
                ],
                "label": "Answer",
                "model": "gpt-4o-mini",
                "code": None,
            }
        ],
        "events": [
            {
                "seq": 1,
                "type": "accepted",
                "node_key": None,
                "occurred_at": "2026-10-17T12:00:00+00:00",
                "payload": {},
            }
        ],
    }

    return {**held, **changes}


def data(value: object) -> dict[str, object]:
    return {"data": value}


def bare_span(operation: str) -> SlenSpan:
    return SlenSpan(
        operation=operation,
        outcome="ok",
        status=None,
        duration_ms=0,
        execution_id=None,
        operation_code=None,
        estimated=None,
        actual=None,
        error_code=None,
        cache_hit=None,
    )

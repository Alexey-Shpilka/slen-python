import math
from dataclasses import dataclass

from slen._errors import PolicyDeniedError, SlenError, SpendRefusedError
from slen._http._clock import Clock
from slen._modules.executions._types import ExecutionStatus, ExecutionStatusView
from slen._modules.operations._types import ExecutionResult
from slen._observability._recorders import SpanRecorder, record_safely
from slen._observability._span import SlenSpan


@dataclass(frozen=True, slots=True, kw_only=True)
class SpanSubject:
    operation: str
    operation_code: str | None = None
    execution_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Verdict:
    outcome: str
    status: ExecutionStatus | None = None
    execution_id: str | None = None
    operation_code: str | None = None
    estimated: str | None = None
    actual: str | None = None
    error_code: str | None = None
    cache_hit: bool | None = None


# The span of one call, written once: from the run it answered with, or from the error it ended on.
class SpanScope:
    __slots__ = ("_clock", "_recorder", "_started", "_subject")

    def __init__(self, recorder: SpanRecorder, subject: SpanSubject, clock: Clock) -> None:
        self._recorder = recorder
        self._subject = subject
        self._clock = clock
        self._started = clock.monotonic()

    def execution(self, run: ExecutionResult | ExecutionStatusView) -> None:
        status = run.status
        refused = status is ExecutionStatus.REJECTED
        broken = status in (ExecutionStatus.FAILED, ExecutionStatus.UNCERTAIN)
        error = run.error if isinstance(run, ExecutionResult) else None

        self._emit(
            Verdict(
                outcome="refused" if refused else "error" if broken else "ok",
                status=status,
                execution_id=run.execution_id,
                operation_code=run.operation,
                estimated=run.cost.estimated,
                actual=run.cost.actual,
                error_code=run.error_code or (error.code if error is not None else None),
                # A run without an answer yet says `cache.hit: false`, which is not a miss.
                cache_hit=None if status.is_pending() else run.cache.hit,
            )
        )

    def failed(self, error: BaseException, operation_code: str | None = None) -> None:
        refused = isinstance(error, SpendRefusedError | PolicyDeniedError)

        self._emit(
            Verdict(
                outcome="refused" if refused else "error",
                operation_code=operation_code,
                error_code=error.code if isinstance(error, SlenError) else None,
            )
        )

    def _emit(self, verdict: Verdict) -> None:
        span = SlenSpan(
            operation=self._subject.operation,
            outcome=verdict.outcome,
            status=verdict.status,
            duration_ms=max(0, math.floor((self._clock.monotonic() - self._started) * 1000 + 0.5)),
            execution_id=verdict.execution_id or self._subject.execution_id,
            operation_code=verdict.operation_code or self._subject.operation_code,
            estimated=verdict.estimated,
            actual=verdict.actual,
            error_code=verdict.error_code,
            cache_hit=verdict.cache_hit,
        )

        record_safely(self._recorder, span)

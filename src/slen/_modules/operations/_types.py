from dataclasses import dataclass, field
from typing import Any

from slen._modules.executions._types import (
    ExecutionCache,
    ExecutionCost,
    ExecutionError,
    ExecutionStatus,
    WaitingOn,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionResult:
    """The answer of execute(): the run as it stands, its error and whether the key replayed an earlier run."""

    execution_id: str
    status: ExecutionStatus
    operation: str
    output: dict[str, Any] | None
    error: ExecutionError | None
    error_code: str | None
    error_message: str | None
    cost: ExecutionCost
    cache: ExecutionCache
    replayed: bool
    waiting_on: WaitingOn | None
    trace_url: str
    retry_after_seconds: int | None = None
    request_id: str | None = field(default=None, compare=False)

    def is_completed(self) -> bool:
        """Over: the flow ran to its end."""
        return self.status is ExecutionStatus.COMPLETED

    def is_rejected(self) -> bool:
        """The flow said no, as an answer: error_code says why."""
        return self.status is ExecutionStatus.REJECTED

    def is_pending(self) -> bool:
        """Still going to move on its own: queued, waiting or running."""
        return self.status.is_pending()

    def is_finished(self) -> bool:
        """Over: it will not move any more, whatever it came to."""
        return self.status.is_finished()

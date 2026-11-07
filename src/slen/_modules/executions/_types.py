from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ExecutionStatus(StrEnum):
    """Where a run stands; the value is the wire's (print(run.status) prints completed)."""

    QUEUED = "queued"
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    UNCERTAIN = "uncertain"

    def is_pending(self) -> bool:
        """Still going to move on its own: queued, waiting or running."""
        return self in (ExecutionStatus.QUEUED, ExecutionStatus.WAITING, ExecutionStatus.RUNNING)

    def is_finished(self) -> bool:
        """Over: it will not move any more, whatever it came to."""
        return not self.is_pending()


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionCost:
    """What the run's model calls were estimated at, and charged once the charges are in (decimal strings)."""

    estimated: str | None
    actual: str | None
    # A provider billed something Slen could not price: actual is what Slen knew (false until actual is set).
    incomplete: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionCache:
    """Whether the output is a stored answer of an earlier model call; true only for a completed run."""

    hit: bool
    cached_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionError:
    """Why the run did not complete, as one object: the code to branch on and the sentence to show."""

    code: str
    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class WaitingOn:
    """What a waiting or queued run waits on: a queue node, an approval, a rate-limit queue, a background job."""

    node_key: str
    type: str
    resume_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionStatusView:
    """The polling view of a run (GET /v1/executions/{id}/status); why it did not complete is error_code."""

    execution_id: str
    status: ExecutionStatus
    operation: str
    output: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    cost: ExecutionCost
    cache: ExecutionCache
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


@dataclass(frozen=True, slots=True, kw_only=True)
class AttemptCostBreakdown:
    """What the cost of a provider attempt is made of (decimal strings); total is their sum."""

    input: str
    cached_input: str
    cache_write: str
    output: str
    tools: dict[str, str]
    total: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AttemptSummary:
    """One provider attempt a node opened."""

    attempt_id: str
    attempt_number: int
    connection_id: str
    pool_id: str | None
    status: str
    error_code: str | None
    latency_ms: int | None
    cost: str | None
    provider_request_id: str | None
    model_code: str | None
    # The whole input with the cache read and writes, the whole output with reasoning, and the parts of each.
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    cache_write_long_tokens: int | None = None
    reasoning_tokens: int | None = None
    tool_calls: dict[str, int] | None = None
    cost_breakdown: AttemptCostBreakdown | None = None
    cost_incomplete: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FlowExecutionNode:
    """One node the run walked through; types and statuses are left open, the backend adds them."""

    node_key: str
    node_type: str
    status: str
    output_port: str | None
    cost: str | None
    duration_ms: int | None
    started_at: datetime
    finished_at: datetime | None
    metadata: dict[str, Any] | None
    attempts: tuple[AttemptSummary, ...]
    label: str | None
    model: str | None
    code: str | None
    # What a model node left: its answer on `success` / `tool_calls` (`content`, `finish_reason`, `usage`, ...), its
    # `error` on a failure port. None for every other node, when `output_stored` is not "stored", and for older runs.
    output: dict[str, Any] | None = None
    # The kept `output` was cut to the limit (64 KB of JSON unless the service is set up otherwise).
    output_truncated: bool | None = None
    # Whether a model node's output is kept: "stored", "disabled_by_project", "withheld" (grounded with Google Search:
    # the rest is kept, its `content` is not) or "history_paused"; None for every other node and for older runs.
    output_stored: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FlowExecutionEvent:
    """One line of the run's timeline: amounts, ids and verdicts, never prompts or provider messages."""

    seq: int
    type: str
    node_key: str | None
    occurred_at: datetime
    payload: dict[str, Any] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionTrace:
    """The stored run with every node and event (GET /v1/executions/{id})."""

    execution_id: str
    flow_id: str
    flow_version_id: str
    flow_name: str | None
    operation: str | None
    operation_id: str | None
    status: ExecutionStatus
    error_code: str | None
    error_message: str | None
    cost: ExecutionCost
    cache: ExecutionCache
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    nodes: tuple[FlowExecutionNode, ...]
    events: tuple[FlowExecutionEvent, ...]
    # The month's executions with history had run out: the run wrote no trace (None from a backend before 1.0.23).
    history_paused: bool | None = None
    request_id: str | None = field(default=None, compare=False)

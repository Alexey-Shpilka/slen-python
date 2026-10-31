from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, TypeAlias

from slen._modules.executions._types import ExecutionStatus

WebhookPayload: TypeAlias = str | bytes


class WebhookEventType(StrEnum):
    """Every event an endpoint can subscribe to, as the backend names them."""

    RESERVATION_CREATED = "reservation.created"
    RESERVATION_CAPTURED = "reservation.captured"
    RESERVATION_RELEASED = "reservation.released"
    RESERVATION_EXPIRED = "reservation.expired"
    RESERVATION_OVERRUN = "reservation.overrun"
    BUDGET_THRESHOLD_REACHED = "budget.threshold_reached"
    BUDGET_EXCEEDED = "budget.exceeded"
    OPERATION_AUTHORIZED = "operation.authorized"
    OPERATION_DENIED = "operation.denied"
    OPERATION_STARTED = "operation.started"
    OPERATION_COMPLETED = "operation.completed"
    OPERATION_FAILED = "operation.failed"
    OPERATION_UNCERTAIN = "operation.uncertain"
    FLOW_PUBLISHED = "flow.published"
    FLOW_ROLLED_BACK = "flow.rolled_back"
    CONNECTION_COOLDOWN_STARTED = "connection.cooldown_started"
    CONNECTION_HEALTH_CHANGED = "connection.health_changed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_DECIDED = "approval.decided"
    EXECUTION_FINISHED = "execution.finished"
    ALERT_OPENED = "alert.opened"
    ALERT_RESOLVED = "alert.resolved"
    OVERRUN_DECIDED = "overrun.decided"
    CUSTOMER_BALANCE_LOW = "customer.balance_low"
    LEDGER_DEGRADED = "ledger.degraded"
    LEDGER_RESTORED = "ledger.restored"


@dataclass(frozen=True, slots=True, kw_only=True)
class WebhookEvent:
    """One delivery; id is the event's, the same on every delivery of it: deduplicate by it."""

    id: str
    type: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionFinishedEventData:
    """A flow run reached its final status; error_code is None for a completed run."""

    execution_id: str
    flow_id: str
    operation: str
    status: ExecutionStatus
    error_code: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionFinishedEvent(WebhookEvent):
    """execution.finished: sent once per run."""

    data: ExecutionFinishedEventData


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerBalanceLowEventData:
    """A movement took a customer's account below its low_balance_threshold (decimal strings)."""

    customer_account_id: str
    project_id: str
    external_user_id: str
    credit_type: str
    balance: str
    reserved: str
    available: str
    threshold: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerBalanceLowEvent(WebhookEvent):
    """customer.balance_low."""

    data: CustomerBalanceLowEventData


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalRequestedEventData:
    """A run parked at an approval node until somebody decides or the request expires."""

    approval_id: str
    execution_id: str
    flow_id: str
    node_key: str
    operation_code: str
    note: str | None
    expires_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalRequestedEvent(WebhookEvent):
    """approval.requested."""

    data: ApprovalRequestedEventData


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalDecidedEventData:
    """An approval got its verdict; expired when nobody decided in time."""

    approval_id: str
    execution_id: str
    flow_id: str
    node_key: str
    operation_code: str
    status: Literal["approved", "rejected", "expired"]
    reason: str | None
    decided_by: str | None
    decided_by_user_id: str | None
    decided_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalDecidedEvent(WebhookEvent):
    """approval.decided."""

    data: ApprovalDecidedEventData


@dataclass(frozen=True, slots=True, kw_only=True)
class UnknownWebhookEvent(WebhookEvent):
    """Any other event, with data as it came; an event added after this release arrives as one too."""

    data: dict[str, Any]

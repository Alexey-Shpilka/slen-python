import json
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Final, Literal, TypeAlias, cast

from slen._http._fields import Fields, WireError
from slen._modules.executions._types import ExecutionStatus
from slen._modules.webhooks._types import (
    ApprovalDecidedEvent,
    ApprovalDecidedEventData,
    ApprovalRequestedEvent,
    ApprovalRequestedEventData,
    CustomerBalanceLowEvent,
    CustomerBalanceLowEventData,
    ExecutionFinishedEvent,
    ExecutionFinishedEventData,
    UnknownWebhookEvent,
    WebhookEvent,
)

Decision: TypeAlias = Literal["approved", "rejected", "expired"]
DECISIONS: Final[Mapping[str, Decision]] = MappingProxyType(
    {"approved": "approved", "rejected": "rejected", "expired": "expired"}
)


def execution_finished(envelope: Fields, data: Fields) -> WebhookEvent:
    return ExecutionFinishedEvent(
        id=envelope.text("id"),
        type=envelope.text("type"),
        created_at=envelope.moment("created_at"),
        data=ExecutionFinishedEventData(
            execution_id=data.text("execution_id"),
            flow_id=data.text("flow_id"),
            operation=data.text("operation"),
            status=data.choice("status", ExecutionStatus),
            error_code=data.nullable_text("error_code"),
        ),
    )


def balance_low(envelope: Fields, data: Fields) -> WebhookEvent:
    return CustomerBalanceLowEvent(
        id=envelope.text("id"),
        type=envelope.text("type"),
        created_at=envelope.moment("created_at"),
        data=CustomerBalanceLowEventData(
            customer_account_id=data.text("customer_account_id"),
            project_id=data.text("project_id"),
            external_user_id=data.text("external_user_id"),
            credit_type=data.text("credit_type"),
            balance=data.text("balance"),
            reserved=data.text("reserved"),
            available=data.text("available"),
            threshold=data.text("threshold"),
        ),
    )


def approval_requested(envelope: Fields, data: Fields) -> WebhookEvent:
    return ApprovalRequestedEvent(
        id=envelope.text("id"),
        type=envelope.text("type"),
        created_at=envelope.moment("created_at"),
        data=ApprovalRequestedEventData(
            approval_id=data.text("approval_id"),
            execution_id=data.text("execution_id"),
            flow_id=data.text("flow_id"),
            node_key=data.text("node_key"),
            operation_code=data.text("operation_code"),
            note=data.nullable_text("note"),
            expires_at=data.moment("expires_at"),
        ),
    )


def approval_decided(envelope: Fields, data: Fields) -> WebhookEvent:
    status = DECISIONS.get(data.text("status"))

    if status is None:
        raise WireError("`data.status` is not a decision")

    return ApprovalDecidedEvent(
        id=envelope.text("id"),
        type=envelope.text("type"),
        created_at=envelope.moment("created_at"),
        data=ApprovalDecidedEventData(
            approval_id=data.text("approval_id"),
            execution_id=data.text("execution_id"),
            flow_id=data.text("flow_id"),
            node_key=data.text("node_key"),
            operation_code=data.text("operation_code"),
            status=status,
            reason=data.nullable_text("reason"),
            decided_by=data.nullable_text("decided_by"),
            decided_by_user_id=data.nullable_text("decided_by_user_id"),
            decided_at=data.nullable_moment("decided_at"),
        ),
    )


TYPED: Final[Mapping[str, Callable[[Fields, Fields], WebhookEvent]]] = MappingProxyType(
    {
        "execution.finished": execution_finished,
        "customer.balance_low": balance_low,
        "approval.requested": approval_requested,
        "approval.decided": approval_decided,
    }
)


# The event of a body, or None when the body is not one: JSON with id, type, created_at and data.
def event_of(text: str) -> WebhookEvent | None:
    try:
        parsed: object = json.loads(text)
        envelope = Fields(parsed, "event")
        raw = cast("dict[str, object]", parsed).get("data")
        # The backend encodes an empty `data` as `[]`: that is an empty object, a list with items is not.
        data = Fields({} if raw == [] else raw, "data")
        kind = envelope.text("type")

        if not kind or not envelope.text("id"):
            return None

        typed = TYPED.get(kind)

        return unknown(envelope, data) if typed is None else typed(envelope, data)
    except (ValueError, WireError):
        return None


def unknown(envelope: Fields, data: Fields) -> WebhookEvent:
    return UnknownWebhookEvent(
        id=envelope.text("id"),
        type=envelope.text("type"),
        created_at=envelope.moment("created_at"),
        data=cast("dict[str, Any]", data.raw()),
    )

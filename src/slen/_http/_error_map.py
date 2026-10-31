import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final, cast

from slen._errors import (
    AuthenticationError,
    BudgetExceededError,
    ConcurrencyLimitError,
    CustomerBlockedError,
    CustomerNotFoundError,
    FlowRuntimeError,
    IdempotencyConflictError,
    InsufficientCreditsError,
    InvalidRequestError,
    OperationLimitExceededError,
    OperationUncertainError,
    OverrunApprovalRequiredError,
    OverrunStoppedError,
    PolicyDeniedError,
    ProviderError,
    RateLimitError,
    ServiceUnavailableError,
    SlenError,
    SpendRefusedError,
    TimeoutError,
)
from slen._http._answer import HttpAnswer
from slen._http._retry import retry_after_ms

# contract/error-codes.json, `codes`: a code listed here always becomes its type, whatever the status.
BY_CODE: Final[Mapping[str, type[SlenError]]] = MappingProxyType(
    {
        "invalid_api_key": AuthenticationError,
        "insufficient_scope": AuthenticationError,
        "not_authenticated": AuthenticationError,
        "not_a_member": AuthenticationError,
        "account_suspended": AuthenticationError,
        "budget_exceeded": BudgetExceededError,
        "insufficient_credits": InsufficientCreditsError,
        "overrun_stopped": OverrunStoppedError,
        "overrun_approval_required": OverrunApprovalRequiredError,
        "customer_not_found": CustomerNotFoundError,
        "operation_limit_exceeded": OperationLimitExceededError,
        "concurrency_limit_exceeded": ConcurrencyLimitError,
        "rate_limit_exceeded": RateLimitError,
        "policy_denied": PolicyDeniedError,
        "model_not_allowed": PolicyDeniedError,
        "customer_blocked": CustomerBlockedError,
        "idempotency_conflict": IdempotencyConflictError,
        "idempotency_in_progress": IdempotencyConflictError,
        "execution_timeout": TimeoutError,
        "background_hold_expired": TimeoutError,
        # The provider could not be reached at all, whatever the name says.
        "provider_timeout": ProviderError,
        "provider_unavailable": ProviderError,
        "provider_rate_limit": ProviderError,
        "provider_error": ProviderError,
        "provider_not_configured": ProviderError,
        "pool_exhausted": ProviderError,
        "cost_calculation_failed": InvalidRequestError,
        # Not a ProviderError: the one answer that must not be caught as a safe one.
        "operation_uncertain": OperationUncertainError,
        "ledger_unavailable": ServiceUnavailableError,
        "service_unavailable": ServiceUnavailableError,
        "flow_runtime_error": FlowRuntimeError,
        "step_limit_exceeded": FlowRuntimeError,
        "unrouted_port": FlowRuntimeError,
        "unknown_node": FlowRuntimeError,
        "node_type_not_supported": FlowRuntimeError,
        "execution_conflict": FlowRuntimeError,
        "http_request_failed": FlowRuntimeError,
    }
)

# contract/error-codes.json, `fallback`: a code this version does not know falls back by status.
BY_STATUS: Final[Mapping[int, type[SlenError]]] = MappingProxyType(
    {401: AuthenticationError, 402: SpendRefusedError, 403: AuthenticationError, 429: RateLimitError}
)


def fallback_for(status: int) -> type[SlenError]:
    return BY_STATUS.get(status) or (ProviderError if status >= 500 else InvalidRequestError)


def error_from_answer(answer: HttpAnswer, now: float) -> SlenError:
    parsed = object_of(answer.body)
    envelope = object_of(parsed.get("error"))
    code = text_of(envelope.get("code"))
    errors = parsed.get("errors")
    details = object_of(envelope.get("details")) or ({"errors": errors} if isinstance(errors, dict | list) else {})
    message = (
        text_of(envelope.get("message"))
        or text_of(parsed.get("message"))
        or f"Slen request failed with status {answer.status}"
    )
    kind = BY_CODE.get(code, fallback_for(answer.status)) if code is not None else fallback_for(answer.status)
    asked = retry_after_ms(answer.retry_after, now)

    return kind(
        message,
        code=code,
        status=answer.status,
        details=details,
        request_id=answer.request_id or text_of(envelope.get("request_id")),
        retry_after_seconds=None if asked is None else math.ceil(asked / 1000),
    )


def object_of(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def text_of(value: object) -> str | None:
    return value if isinstance(value, str) else None

import builtins
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Final, Literal, TypeAlias

INVALID_REQUEST: Final = "invalid_request"
INVALID_RESPONSE: Final = "invalid_response"
WEBHOOK_SIGNATURE_INVALID: Final = "webhook_signature_invalid"
WEBHOOK_PAYLOAD_INVALID: Final = "webhook_payload_invalid"

WebhookSignatureReason: TypeAlias = Literal[
    "missing_header", "malformed_header", "outside_tolerance", "no_matching_signature"
]

_STATE: Final = ("code", "status", "details", "request_id", "retry_after_seconds")


class SlenError(Exception):
    """The root of every error the SDK raises."""

    code: str | None
    status: int | None
    details: Mapping[str, Any]
    request_id: str | None
    retry_after_seconds: int | None

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        details: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = MappingProxyType(dict(details or {}))
        self.request_id = request_id
        self.retry_after_seconds = retry_after_seconds

    def __reduce__(self) -> tuple[Callable[..., "SlenError"], tuple[object, ...]]:
        state = {name: getattr(self, name) for name in _STATE}
        state["details"] = dict(self.details)
        state.update({name: value for name, value in vars(self).items() if name not in _STATE})

        return _rebuilt, (type(self), str(self), state)


def _rebuilt(kind: type[SlenError], message: str, state: dict[str, Any]) -> SlenError:
    error = kind.__new__(kind, message)
    Exception.__init__(error, message)
    vars(error).update({**state, "details": MappingProxyType(dict(state["details"]))})

    return error


class AuthenticationError(SlenError):
    """401 or 403: the key, its scope or the tenant."""


class InvalidRequestError(SlenError):
    """The request was refused for its shape: 422, an unknown code of a 4xx, or a check before the wire."""


class SpendRefusedError(SlenError):
    """Money said no (402); each ceiling has a subtype."""


class BudgetExceededError(SpendRefusedError):
    """The project's or the organization's budget."""


class InsufficientCreditsError(SpendRefusedError):
    """The end customer is out of credits."""


class OverrunStoppedError(SpendRefusedError):
    """An overrun of a budget that stops the run."""


class OverrunApprovalRequiredError(SpendRefusedError):
    """An overrun of a budget that waits for somebody to approve it."""


class OperationLimitExceededError(SpendRefusedError):
    """One operation would cost more than a per-operation budget allows."""


class ConcurrencyLimitError(SpendRefusedError):
    """A concurrency budget has every slot taken; passes when one is freed."""


class CustomerNotFoundError(SlenError):
    """The project has never seen this end customer."""


class RateLimitError(SlenError):
    """429: the key sent more requests than its rate limit allows."""


class PolicyDeniedError(SlenError):
    """A policy of the project refused the run."""


class CustomerBlockedError(PolicyDeniedError):
    """The end customer of the run is blocked, so its new runs are refused; nothing ran."""


class IdempotencyConflictError(SlenError):
    """The idempotency key was used with another body, or its first request is still running."""


class ProviderError(SlenError):
    """A model provider failed or could not be called; any 5xx without a known code lands here too — read code."""


class TimeoutError(SlenError, builtins.TimeoutError):
    """No answer in time (no code), or a run that ran out of time on the server."""


class OperationUncertainError(SlenError):
    """A provider was called and nobody knows what became of the call: the money may be spent."""


class ServiceUnavailableError(SlenError):
    """503 from Slen itself: nothing was done, the request may be sent again."""


class FlowRuntimeError(SlenError):
    """The flow broke while it was walked; the model calls before the break were paid for."""


class ConnectionError(SlenError, builtins.ConnectionError):
    """Slen could not be reached, or the connection broke before the answer was read; no code, no status."""


class InvalidResponseError(SlenError):
    """A 2xx whose body cannot be read as the answer; the call may have gone through."""


class WebhookSignatureError(SlenError):
    """A webhook whose Slen-Signature was not accepted: do not act on its body; reason says why."""

    reason: WebhookSignatureReason

    def __init__(
        self,
        message: str,
        *,
        reason: WebhookSignatureReason,
        code: str | None = WEBHOOK_SIGNATURE_INVALID,
        status: int | None = None,
        details: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            status=status,
            details=details,
            request_id=request_id,
            retry_after_seconds=retry_after_seconds,
        )
        self.reason = reason


def contract_type_of(error: SlenError) -> str:
    return type(error).__name__.removesuffix("Error")


def refused(message: str) -> InvalidRequestError:
    return InvalidRequestError(message, code=INVALID_REQUEST)

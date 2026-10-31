import importlib
import sys
from typing import Final

import pytest

import slen
import slen.otel
import slen.testing

# The public surface, exactly: a name added or taken away is a decision, written here.
SURFACE: Final = frozenset(
    {
        # The clients and their modules.
        "Slen",
        "AsyncSlen",
        "Operations",
        "AsyncOperations",
        "Executions",
        "AsyncExecutions",
        "Customers",
        "AsyncCustomers",
        "Webhooks",
        # The answers.
        "Health",
        "Page",
        "CreditPriceList",
        "Customer",
        "CustomerAccount",
        "CreditEntry",
        "CreditPrice",
        "ExecutionResult",
        "ExecutionStatusView",
        "ExecutionCost",
        "ExecutionCache",
        "ExecutionError",
        "WaitingOn",
        "ExecutionTrace",
        "FlowExecutionNode",
        "FlowExecutionEvent",
        "AttemptSummary",
        # The enumerations.
        "ExecutionStatus",
        "CustomerStatus",
        "CreditEntryType",
        "WebhookEventType",
        # The events of a webhook.
        "WebhookEvent",
        "ExecutionFinishedEvent",
        "ExecutionFinishedEventData",
        "CustomerBalanceLowEvent",
        "CustomerBalanceLowEventData",
        "ApprovalRequestedEvent",
        "ApprovalRequestedEventData",
        "ApprovalDecidedEvent",
        "ApprovalDecidedEventData",
        "UnknownWebhookEvent",
        # The errors.
        "SlenError",
        "AuthenticationError",
        "InvalidRequestError",
        "SpendRefusedError",
        "BudgetExceededError",
        "InsufficientCreditsError",
        "OverrunStoppedError",
        "OverrunApprovalRequiredError",
        "OperationLimitExceededError",
        "ConcurrencyLimitError",
        "CustomerNotFoundError",
        "RateLimitError",
        "PolicyDeniedError",
        "CustomerBlockedError",
        "IdempotencyConflictError",
        "ProviderError",
        "TimeoutError",
        "OperationUncertainError",
        "ServiceUnavailableError",
        "FlowRuntimeError",
        "ConnectionError",
        "InvalidResponseError",
        "WebhookSignatureError",
        # The journal and the spans.
        "SlenLogger",
        "LOG_EVENTS",
        "SlenSpan",
        "SpanRecorder",
        "LoggerSpanRecorder",
        # The helpers and the aliases of types.
        "generate_idempotency_key",
        "idempotency_key_for_job",
        "ContextValue",
        "PollErrorListener",
        "AsyncPollErrorListener",
        "WebhookPayload",
        "WebhookSignatureReason",
        "__version__",
    }
)


def test_the_package_exports_the_surface_and_nothing_else() -> None:
    assert set(slen.__all__) == SURFACE
    assert len(slen.__all__) == len(SURFACE)
    assert [name for name in SURFACE if not hasattr(slen, name)] == []


def test_nothing_internal_is_exported() -> None:
    assert [name for name in slen.__all__ if name.startswith("_") and name != "__version__"] == []


def test_the_submodules_export_the_doubles_and_the_bridge() -> None:
    assert set(slen.testing.__all__) == {"FakeTransport", "RecordedRequest", "MemorySpanRecorder"}
    assert set(slen.otel.__all__) == {"OtelSpanRecorder"}


def test_the_bridge_without_the_extra_says_how_to_get_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    monkeypatch.delitem(sys.modules, "slen.otel", raising=False)

    with pytest.raises(ImportError, match=r'pip install "slen\[otel\]"'):
        importlib.import_module("slen.otel")


def test_the_events_of_the_journal_are_the_contracts() -> None:
    assert slen.LOG_EVENTS == (
        "slen.request",
        "slen.response",
        "slen.retry",
        "slen.refused",
        "slen.unauthorized",
        "slen.failed",
        "slen.wait.poll",
        "slen.wait.poll_failed",
        "slen.webhook.rejected",
    )

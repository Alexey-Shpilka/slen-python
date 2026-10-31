from collections.abc import Mapping
from typing import Any

from slen._http._request import Sending, refuse_before_the_wire
from slen._modules._context import SyncContext
from slen._modules.operations._calls import ContextValue, RunOrder, run_call, span_subject
from slen._modules.operations._types import ExecutionResult
from slen._observability._scope import SpanScope


class Operations:
    """Runs the flow bound to an operation; the caller names what it wants done, never a model."""

    def __init__(self, context: SyncContext) -> None:
        self._context = context

    def execute(
        self,
        operation: str,
        input: Mapping[str, Any],
        *,
        customer: str | None = None,
        credit_type: str | None = None,
        context: Mapping[str, ContextValue] | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> ExecutionResult:
        """Runs the flow inside the request and answers with the run; a repeated key answers the first run."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return self._run(
            RunOrder(
                operation=operation,
                input=input,
                queued=False,
                customer=customer,
                credit_type=credit_type,
                context=context,
                idempotency_key=idempotency_key,
                sending=sending,
            )
        )

    def execute_async(
        self,
        operation: str,
        input: Mapping[str, Any],
        *,
        customer: str | None = None,
        credit_type: str | None = None,
        context: Mapping[str, ContextValue] | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> ExecutionResult:
        """Hands the run to a worker and answers queued at once; executions.wait() or a webhook tells the rest."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return self._run(
            RunOrder(
                operation=operation,
                input=input,
                queued=True,
                customer=customer,
                credit_type=credit_type,
                context=context,
                idempotency_key=idempotency_key,
                sending=sending,
            )
        )

    def _run(self, order: RunOrder) -> ExecutionResult:
        call = run_call(order)
        refuse_before_the_wire(call.request)
        scope = SpanScope(self._context.spans, span_subject(order), self._context.transport.clock)

        try:
            run = self._context.transport.call(call)
        except BaseException as error:
            scope.failed(error)
            raise

        scope.execution(run)

        return run

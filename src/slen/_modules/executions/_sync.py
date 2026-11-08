from slen._errors import SlenError
from slen._http._request import Sending
from slen._modules._context import SyncContext
from slen._modules.executions._calls import status_call, trace_call
from slen._modules.executions._journal import log_warnings
from slen._modules.executions._types import ExecutionStatusView, ExecutionTrace
from slen._modules.executions._wait import PollErrorListener, Waiting, WaitOrder, check_wait
from slen._observability._scope import SpanScope, SpanSubject


class Executions:
    """Reads a run: its status, a wait until it is over, its trace."""

    def __init__(self, context: SyncContext) -> None:
        self._context = context

    def get(
        self,
        execution_id: str,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> ExecutionStatusView:
        """The polling view of one run, read once; writes no span."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)
        run = self._context.transport.call(status_call(execution_id, sending))
        log_warnings(self._context.transport.config.logger, run.execution_id, run.warnings)

        return run

    def wait(
        self,
        execution_id: str,
        *,
        timeout_seconds: float = 300,
        on_poll_error: PollErrorListener | None = None,
    ) -> ExecutionStatusView:
        """Reads the run until it is over, at the pace the server asks; at the timeout, answers the last state read."""
        order = WaitOrder(execution_id=execution_id, timeout_seconds=timeout_seconds)
        check_wait(order)
        transport = self._context.transport
        scope = SpanScope(
            self._context.spans, SpanSubject(operation="executions.wait", execution_id=execution_id), transport.clock
        )
        waiting = Waiting(order, transport.config, transport.clock)

        try:
            run = self._poll(waiting, on_poll_error)
        except BaseException as error:
            scope.failed(error, None if waiting.seen is None else waiting.seen.operation)
            raise

        scope.execution(run)
        # One record for the state the wait answers with, none for the reads before it.
        log_warnings(transport.config.logger, run.execution_id, run.warnings)

        return run

    def trace(
        self,
        execution_id: str,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> ExecutionTrace:
        """The trace of one run: every node, event and provider attempt."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)
        found = self._context.transport.call(trace_call(execution_id, sending))
        log_warnings(self._context.transport.config.logger, found.execution_id, found.warnings)

        return found

    def _poll(self, waiting: Waiting, listener: PollErrorListener | None) -> ExecutionStatusView:
        transport = self._context.transport

        while True:
            run: ExecutionStatusView | None = None
            failure: SlenError | None = None

            try:
                run = transport.call(waiting.read())
            except SlenError as error:
                failure = error

            if failure is not None:
                waiting.failed(failure)
                # Outside the read's `try`: what the listener raises is the caller's own and ends the wait.
                if listener is not None:
                    listener(failure, waiting.failures)

                waiting.give_up_if_endless(failure)

            pause = waiting.pause(run)

            if pause is None:
                return waiting.outcome(run)

            transport.clock.sleep(pause)

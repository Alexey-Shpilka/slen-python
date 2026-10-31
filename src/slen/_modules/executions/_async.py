import inspect

from slen._errors import SlenError
from slen._http._request import Sending
from slen._modules._context import AsyncContext
from slen._modules.executions._calls import status_call, trace_call
from slen._modules.executions._types import ExecutionStatusView, ExecutionTrace
from slen._modules.executions._wait import AsyncPollErrorListener, Waiting, WaitOrder, check_wait
from slen._observability._scope import SpanScope, SpanSubject


class AsyncExecutions:
    """Reads a run, for asyncio: its status, a wait until it is over, its trace."""

    def __init__(self, context: AsyncContext) -> None:
        self._context = context

    async def get(
        self,
        execution_id: str,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> ExecutionStatusView:
        """The polling view of one run, read once; writes no span."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(status_call(execution_id, sending))

    async def wait(
        self,
        execution_id: str,
        *,
        timeout_seconds: float = 300,
        on_poll_error: AsyncPollErrorListener | None = None,
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
            run = await self._poll(waiting, on_poll_error)
        except BaseException as error:
            scope.failed(error, None if waiting.seen is None else waiting.seen.operation)
            raise

        scope.execution(run)

        return run

    async def trace(
        self,
        execution_id: str,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> ExecutionTrace:
        """The trace of one run: every node, event and provider attempt."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._context.transport.call(trace_call(execution_id, sending))

    async def _poll(self, waiting: Waiting, listener: AsyncPollErrorListener | None) -> ExecutionStatusView:
        transport = self._context.transport

        while True:
            run: ExecutionStatusView | None = None
            failure: SlenError | None = None

            try:
                run = await transport.call(waiting.read())
            except SlenError as error:
                failure = error

            if failure is not None:
                waiting.failed(failure)
                told = None if listener is None else listener(failure, waiting.failures)

                # A listener may be a plain function or a coroutine; what it raises ends the wait.
                if inspect.isawaitable(told):
                    await told

                waiting.give_up_if_endless(failure)

            pause = waiting.pause(run)

            if pause is None:
                return waiting.outcome(run)

            await transport.clock.sleep_async(pause)

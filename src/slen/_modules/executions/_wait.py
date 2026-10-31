import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, TypeAlias

from slen._config import ClientConfig
from slen._errors import ConnectionError, SlenError, TimeoutError, contract_type_of, refused
from slen._http._answer import Call
from slen._http._clock import Clock
from slen._http._request import NOT_SAID, Sending, refuse_before_the_wire
from slen._logger import write_log
from slen._modules.executions._calls import status_call
from slen._modules.executions._types import ExecutionStatusView

PollErrorListener: TypeAlias = Callable[[SlenError, int], None]
AsyncPollErrorListener: TypeAlias = Callable[[SlenError, int], Awaitable[None] | None]

DEFAULT_WAIT_SECONDS: Final = 300.0
MAX_FAILURES_WITHOUT_TIMEOUT: Final = 10
SHORTEST_READ_SECONDS: Final = 5.0
# A wait never reads faster than four times a second; a sliver of time left is no time.
SHORTEST_PAUSE_MS: Final = 250
NEGLIGIBLE_MS: Final = 5
LONGEST_PAUSE_SECONDS: Final = 30


@dataclass(frozen=True, slots=True, kw_only=True)
class WaitOrder:
    execution_id: str
    timeout_seconds: float


def check_wait(order: WaitOrder) -> None:
    refuse_before_the_wire(status_call(order.execution_id, NOT_SAID).request)
    given: object = order.timeout_seconds

    if not isinstance(given, int | float) or isinstance(given, bool):
        raise refused(f"Slen: timeout_seconds of a wait is a number of seconds, got {given!r}.")


def wait_seconds(given: float) -> float:
    return max(1.0, DEFAULT_WAIT_SECONDS if math.isnan(given) else float(given))


def next_delay_ms(retry_after_seconds: int | None, step: int, random: Callable[[], float]) -> int:
    fallback = min(LONGEST_PAUSE_SECONDS, 2 ** min(5, max(0, step - 1)))
    seconds = fallback if retry_after_seconds is None else retry_after_seconds
    jitter = seconds * (random() * 0.5 - 0.25)

    return max(SHORTEST_PAUSE_MS, math.floor((seconds + jitter) * 1000 + 0.5))


# No answer, 429 and any 5xx are waited through; anything else ends the wait at once.
def is_passing(error: SlenError) -> bool:
    if isinstance(error, TimeoutError | ConnectionError):
        return True

    return error.status is not None and (error.status == 429 or error.status >= 500)


# The state of one wait, kept on the stack of its call: the deadline, what was read, how many reads failed in a row.
class Waiting:
    __slots__ = ("_answers", "_clock", "_config", "_deadline", "_order", "failure", "failures", "seen")

    def __init__(self, order: WaitOrder, config: ClientConfig, clock: Clock) -> None:
        self._order = order
        self._config = config
        self._clock = clock
        self._deadline = clock.monotonic() + wait_seconds(order.timeout_seconds)
        self._answers = 0
        self.failures = 0
        self.failure: SlenError | None = None
        self.seen: ExecutionStatusView | None = None

    # A read is sent once, under what is left of the wait: at least five seconds, at most the client's timeout.
    def read(self) -> Call[ExecutionStatusView]:
        left = max(SHORTEST_READ_SECONDS, self._deadline - self._clock.monotonic())

        return status_call(self._order.execution_id, Sending(timeout=min(self._config.timeout, left), retries=0))

    def failed(self, error: SlenError) -> None:
        if not is_passing(error):
            raise error

        self.failure = error
        self.failures += 1
        fields = {"failures_in_a_row": self.failures, "error_type": contract_type_of(error)}
        write_log(self._config.logger, "slen.wait.poll_failed", {"execution_id": self._order.execution_id, **fields})

    def give_up_if_endless(self, error: SlenError) -> None:
        if math.isinf(self._deadline) and self.failures >= MAX_FAILURES_WITHOUT_TIMEOUT:
            raise error

    # How long to pause before the next read, in seconds; None once the run is over or the time is up.
    def pause(self, run: ExecutionStatusView | None) -> float | None:
        if run is not None:
            self.seen = run
            self.failures = 0
            self._answers += 1

        step = self.failures if run is None else self._answers
        wanted = next_delay_ms(None if run is None else run.retry_after_seconds, step, self._clock.random)
        pause = None if run is not None and run.is_finished() else self._pause_before(wanted)

        if run is not None:
            fields = {"status": str(run.status), "next_poll_ms": pause}
            write_log(self._config.logger, "slen.wait.poll", {"execution_id": self._order.execution_id, **fields})

        return None if pause is None else pause / 1000

    def _pause_before(self, wanted_ms: int) -> int | None:
        remaining_ms = (self._deadline - self._clock.monotonic()) * 1000

        # Negated on purpose: a value that is not a number reads as "up", never as "read at once".
        if not remaining_ms >= NEGLIGIBLE_MS:
            return None

        return math.floor(min(max(wanted_ms, SHORTEST_PAUSE_MS), remaining_ms))

    # At the end: the run that is over, or the last state read when the time is up; with none, the last failure.
    def outcome(self, run: ExecutionStatusView | None) -> ExecutionStatusView:
        last = run if run is not None else self.seen

        if last is None:
            raise self.failure or refused("Slen: the wait read nothing.")

        return last

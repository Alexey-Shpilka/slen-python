import email.utils
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from typing import Final, Literal, TypeAlias

from slen._errors import ConnectionError, TimeoutError
from slen._http._answer import HttpAnswer
from slen._http._clock import Clock

RETRY_AFTER_CEILING_MS: Final = 30_000
BACKOFF_BASE_MS: Final = 200
BACKOFF_CEILING_MS: Final = 5_000
DIGITS: Final = re.compile(r"[0-9]+")

RetryReason: TypeAlias = Literal["no_answer", "rate_limited", "unavailable"]


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryPause:
    delay_ms: int
    reason: RetryReason
    status: int | None


# Where a call stands after one of its attempts: the attempt (from 1) and how many the call may repeat.
@dataclass(frozen=True, slots=True, kw_only=True)
class Standing:
    attempt: int
    retries: int


def pause_after_no_answer(standing: Standing, clock: Clock) -> RetryPause | None:
    if standing.attempt > standing.retries:
        return None

    return RetryPause(delay_ms=backoff_ms(standing.attempt - 1, clock.random), reason="no_answer", status=None)


# No answer, 429 and any 503 are repeated; 500, 502 and 504 never are: a provider may have been paid.
def pause_after_answer(answer: HttpAnswer, standing: Standing, clock: Clock) -> RetryPause | None:
    if standing.attempt > standing.retries or answer.status not in (429, 503):
        return None

    asked = retry_after_ms(answer.retry_after, clock.now())
    reason: RetryReason = "rate_limited" if answer.status == 429 else "unavailable"

    if asked is not None and asked > RETRY_AFTER_CEILING_MS:
        return None

    delay = backoff_ms(standing.attempt - 1, clock.random) if asked is None else asked

    return RetryPause(delay_ms=delay, reason=reason, status=answer.status)


def retry_after_ms(value: str | None, now: float) -> int | None:
    text = (value or "").strip()

    if not text:
        return None

    if DIGITS.fullmatch(text):
        return int(text) * 1000

    try:
        moment = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None

    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)

    return max(0, math.floor((aware.timestamp() - now) * 1000 + 0.5))


def backoff_ms(retried: int, random: Callable[[], float]) -> int:
    base = BACKOFF_BASE_MS * (1 << min(max(retried, 0), 16))

    return min(math.floor(base * (0.75 + random() * 0.5) + 0.5), BACKOFF_CEILING_MS)


# What the SDK raises when the answer did not arrive; a server's own timeout comes with a code.
def is_no_answer(error: BaseException) -> bool:
    return isinstance(error, TimeoutError | ConnectionError) and error.code is None

import math
from dataclasses import dataclass
from typing import Generic, TypeVar, cast

from slen._errors import INVALID_RESPONSE, InvalidResponseError
from slen._http._answer import Answered, Call, HttpAnswer
from slen._http._clock import Clock
from slen._http._error_map import error_from_answer
from slen._http._fields import WireError
from slen._http._journal import HttpJournal
from slen._http._request import ApiRequest

T = TypeVar("T")


# One call on its way: what it is, where its journal goes, and when it started.
@dataclass(frozen=True, slots=True, kw_only=True)
class Exchange(Generic[T]):
    call: Call[T]
    journal: HttpJournal
    clock: Clock
    started: float


def settle(exchange: Exchange[T], answer: HttpAnswer) -> T:
    request = exchange.call.request

    if not 200 <= answer.status < 300:
        return settle_refusal(exchange, answer)

    try:
        value = exchange.call.read(Answered(data=data_of(request, answer), request_id=answer.request_id))
    except WireError as problem:
        error = unreadable(request, answer, f"an answer whose {problem}")
        exchange.journal.rejected(request, error, answer.attempts)
        raise error from None
    except InvalidResponseError as error:
        exchange.journal.rejected(request, error, answer.attempts)
        raise

    exchange.journal.response(request, answer, elapsed_ms(exchange))

    return value


def settle_refusal(exchange: Exchange[T], answer: HttpAnswer) -> T:
    request = exchange.call.request
    error = error_from_answer(answer, exchange.clock.now())
    done = request.done_after_no_answer

    # A repeat after no answer that finds the thing gone: the attempt that got no answer did the work.
    if answer.after_no_answer and done is not None and error.code == done:
        exchange.journal.response(request, answer, elapsed_ms(exchange))
        return exchange.call.read(Answered(data=None, request_id=answer.request_id))

    exchange.journal.rejected(request, error, answer.attempts)
    raise error


def elapsed_ms(exchange: Exchange[T]) -> int:
    return max(0, math.floor((exchange.clock.monotonic() - exchange.started) * 1000 + 0.5))


def data_of(request: ApiRequest, answer: HttpAnswer) -> object:
    if answer.status == 204 and request.wants_body:
        raise unreadable(request, answer, "no body")

    if answer.status == 204:
        return None

    body = answer.body

    if not isinstance(body, dict):
        raise unreadable(request, answer, "no body" if answer.body_length == 0 else "a body that is not a JSON object")

    held = cast("dict[str, object]", body)

    if request.envelope == "body":
        return held

    return inside(request, answer, held)


def inside(request: ApiRequest, answer: HttpAnswer, body: dict[str, object]) -> object:
    data = body.get("data")
    meta = body.get("meta")

    if not isinstance(data, dict | list):
        raise unreadable(request, answer, "JSON that has no `data` in it")

    if request.envelope == "list" and not isinstance(data, list):
        raise unreadable(request, answer, "a `data` that is not a list")

    if request.envelope == "page" and not (isinstance(data, list) and is_cursor_meta(meta)):
        raise unreadable(request, answer, "a page that has no `data` list or no `meta.next_cursor`")

    if request.envelope in ("page", "list"):
        return body

    return cast("object", data)


def is_cursor_meta(meta: object) -> bool:
    cursor = cast("dict[str, object]", meta).get("next_cursor", 0) if isinstance(meta, dict) else 0

    return cursor is None or isinstance(cursor, str)


# The body is not quoted: it may carry the output of a flow.
def unreadable(request: ApiRequest, answer: HttpAnswer, what: str) -> InvalidResponseError:
    return InvalidResponseError(
        f"Slen answered {answer.status} to {request.endpoint} with {what}. "
        "The call may have gone through; its answer cannot be read.",
        code=INVALID_RESPONSE,
        status=answer.status,
        request_id=answer.request_id,
    )

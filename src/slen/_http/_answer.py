import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

import httpx

from slen._http._request import ApiRequest

T = TypeVar("T")


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpAnswer:
    status: int
    body: object
    body_length: int
    request_id: str | None
    retry_after: str | None
    attempts: int = 1
    after_no_answer: bool = False


# What a reader of the wire gets: the inside of the envelope, and the id of the response it came in.
@dataclass(frozen=True, slots=True, kw_only=True)
class Answered:
    data: object
    request_id: str | None


@dataclass(frozen=True, slots=True)
class Call(Generic[T]):
    request: ApiRequest
    read: Callable[[Answered], T]


def answer_of(response: httpx.Response, content: bytes) -> HttpAnswer:
    body: object = None

    try:
        body = json.loads(content) if content else None
    except ValueError:
        body = None

    return HttpAnswer(
        status=response.status_code,
        body=body,
        body_length=len(content),
        request_id=response.headers.get("x-request-id"),
        retry_after=response.headers.get("retry-after"),
    )

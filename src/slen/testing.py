"""Test doubles of the SDK, for your own tests: an HTTP transport that answers from a queue, and a span recorder."""

import json
import re
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Self

import httpx

from slen._http._endpoints import Endpoint
from slen._observability._span import SlenSpan

# A response of these statuses carries no body, not even an empty one.
NO_BODY: Final = frozenset({204, 205, 304})


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordedRequest:
    """One request the SDK sent: its method, URL, headers (names in lower case) and its body as JSON, or None."""

    method: str
    url: str
    headers: Mapping[str, str]
    body: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class _Queued:
    status: int = 200
    headers: tuple[tuple[str, str], ...] = ()
    content: bytes = b""
    error: Exception | None = None


class FakeTransport(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """Answers from a queue and keeps every request: for tests, never a server."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: deque[_Queued] = deque()
        self._requests: list[RecordedRequest] = []

    def push(
        self, status: int, body: Mapping[str, Any] | None = None, *, headers: Mapping[str, str] | None = None
    ) -> Self:
        """Queues an answer: its status, its JSON body (none without one) and its headers."""
        if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
            raise ValueError("FakeTransport: an answer has an HTTP status, 100 to 599.")

        content = b"" if body is None or status in NO_BODY else json.dumps(body).encode()
        sent = tuple({"Content-Type": "application/json", **(headers or {})}.items())

        return self._queued(_Queued(status=status, headers=sent, content=content))

    def push_exception(self, error: Exception) -> Self:
        """Queues a failure of the wire, raised in place of an answer: httpx.ConnectError, httpx.ReadTimeout."""
        return self._queued(_Queued(error=error))

    @property
    def requests(self) -> tuple[RecordedRequest, ...]:
        """Every request sent, in order."""
        with self._lock:
            return tuple(self._requests)

    def last(self) -> RecordedRequest:
        """The last request sent; LookupError when none was."""
        with self._lock:
            if not self._requests:
                raise LookupError("FakeTransport: no request was sent.")

            return self._requests[-1]

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Answers one request of an httpx.Client."""
        return self._answer(request)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Answers one request of an httpx.AsyncClient."""
        return self._answer(request)

    def _queued(self, queued: _Queued) -> Self:
        with self._lock:
            self._queue.append(queued)

        return self

    def _answer(self, request: httpx.Request) -> httpx.Response:
        recorded = RecordedRequest(
            method=request.method,
            url=str(request.url),
            headers=MappingProxyType({name.lower(): value for name, value in request.headers.items()}),
            body=json.loads(request.content) if request.content else None,
        )

        with self._lock:
            self._requests.append(recorded)
            queued = self._queue.popleft() if self._queue else None

        if queued is None:
            raise LookupError(f"FakeTransport: nothing is queued for {route_of(request)}; push() an answer first.")

        if queued.error is not None:
            raise queued.error

        return httpx.Response(queued.status, headers=list(queued.headers), content=queued.content)


# The route a request was sent to, as a template: the values of a path are not repeated in a message.
def route_of(request: httpx.Request) -> str:
    path = request.url.path.removeprefix("/api")

    for endpoint in Endpoint:
        pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(endpoint.route))

        if endpoint.method == request.method and re.fullmatch(pattern, path):
            return str(endpoint)

    return request.method


class MemorySpanRecorder:
    """Keeps every span it is given, in memory: for tests, never a server."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spans: list[SlenSpan] = []

    @property
    def spans(self) -> tuple[SlenSpan, ...]:
        """Every span recorded, in order."""
        with self._lock:
            return tuple(self._spans)

    def record(self, span: SlenSpan) -> None:
        """Keeps the span."""
        with self._lock:
            self._spans.append(span)

    def last(self) -> SlenSpan:
        """The last span recorded; LookupError when there is none."""
        with self._lock:
            if not self._spans:
                raise LookupError("MemorySpanRecorder: no span was recorded.")

            return self._spans[-1]


__all__ = ("FakeTransport", "MemorySpanRecorder", "RecordedRequest")

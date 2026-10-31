import dataclasses
from typing import TypeVar

import httpx

from slen._config import ClientConfig
from slen._errors import ConnectionError, SlenError, TimeoutError
from slen._http._answer import Call, HttpAnswer, answer_of
from slen._http._clock import Clock
from slen._http._envelope import Exchange, settle
from slen._http._journal import HttpJournal
from slen._http._request import ApiRequest, refuse_before_the_wire
from slen._http._retry import RetryPause, Standing, pause_after_answer, pause_after_no_answer
from slen._http._wire import Prepared, prepare, timed_out, unreachable

T = TypeVar("T")


# The chain of one client, for a thread: checks before the wire, attempts and their pauses, the envelope, the journal.
class SyncTransport:
    __slots__ = ("_client", "_clock", "_journal", "config")

    config: ClientConfig

    def __init__(self, config: ClientConfig, client: httpx.Client, clock: Clock) -> None:
        self.config = config
        self._client = client
        self._clock = clock
        self._journal = HttpJournal(config.logger)

    @property
    def clock(self) -> Clock:
        return self._clock

    def call(self, call: Call[T]) -> T:
        refuse_before_the_wire(call.request)
        exchange = Exchange(call=call, journal=self._journal, clock=self._clock, started=self._clock.monotonic())

        return settle(exchange, self._send(prepare(self.config, call.request)))

    def _send(self, prepared: Prepared) -> HttpAnswer:
        request = prepared.request
        retries = self.config.retries if request.sending.retries is None else request.sending.retries
        after_no_answer = False
        attempt = 0

        while True:
            attempt += 1
            standing = Standing(attempt=attempt, retries=retries)
            self._journal.request(request, attempt)

            try:
                answer = self._attempt(prepared)
            except (TimeoutError, ConnectionError) as error:
                pause = pause_after_no_answer(standing, self._clock)

                if pause is None:
                    self._journal.rejected(request, error, attempt)
                    raise

                self._pause(request, attempt, pause)
                after_no_answer = True
                continue

            pause = pause_after_answer(answer, standing, self._clock)

            if pause is None:
                return dataclasses.replace(answer, attempts=attempt, after_no_answer=after_no_answer)

            self._pause(request, attempt, pause)

    def _pause(self, request: ApiRequest, attempt: int, pause: RetryPause) -> None:
        self._journal.retry(request, attempt, pause)
        self._clock.sleep(pause.delay_ms / 1000)

    def _attempt(self, prepared: Prepared) -> HttpAnswer:
        request = self._client.build_request(
            prepared.request.endpoint.method,
            prepared.url,
            headers=prepared.headers,
            content=prepared.request.body,
            timeout=prepared.timeout,
        )
        deadline = self._clock.monotonic() + prepared.seconds

        try:
            response = self._client.send(request, stream=True)
        except httpx.TimeoutException as error:
            raise timed_out(prepared) from error
        except (httpx.RequestError, OSError) as error:
            raise unreachable(prepared, error) from error

        try:
            content = self._read(response, deadline, prepared)
        finally:
            response.close()

        return answer_of(response, content)

    # httpx holds each read to the timeout, not the body as a whole: the attempt's deadline is checked between chunks.
    def _read(self, response: httpx.Response, deadline: float, prepared: Prepared) -> bytes:
        chunks: list[bytes] = []

        try:
            for chunk in response.iter_bytes():
                chunks.append(chunk)

                if self._clock.monotonic() > deadline:
                    raise timed_out(prepared)
        except SlenError:
            raise
        except httpx.TimeoutException as error:
            raise timed_out(prepared) from error
        except (httpx.RequestError, OSError) as error:
            raise unreachable(prepared, error) from error

        return b"".join(chunks)

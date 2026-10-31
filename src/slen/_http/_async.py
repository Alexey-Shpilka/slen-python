import asyncio
import builtins
import dataclasses
import math
from typing import TypeVar

import httpx

from slen._config import ClientConfig
from slen._errors import ConnectionError, TimeoutError
from slen._http._answer import Call, HttpAnswer, answer_of
from slen._http._clock import Clock
from slen._http._envelope import Exchange, settle
from slen._http._journal import HttpJournal
from slen._http._request import ApiRequest, refuse_before_the_wire
from slen._http._retry import RetryPause, Standing, pause_after_answer, pause_after_no_answer
from slen._http._wire import Prepared, prepare, timed_out, unreachable

T = TypeVar("T")


# The chain of one client, for asyncio: the same decisions as the thread's, each attempt under one deadline.
class AsyncTransport:
    __slots__ = ("_client", "_clock", "_journal", "config")

    config: ClientConfig

    def __init__(self, config: ClientConfig, client: httpx.AsyncClient, clock: Clock) -> None:
        self.config = config
        self._client = client
        self._clock = clock
        self._journal = HttpJournal(config.logger)

    @property
    def clock(self) -> Clock:
        return self._clock

    async def call(self, call: Call[T]) -> T:
        refuse_before_the_wire(call.request)
        exchange = Exchange(call=call, journal=self._journal, clock=self._clock, started=self._clock.monotonic())

        return settle(exchange, await self._send(prepare(self.config, call.request)))

    async def _send(self, prepared: Prepared) -> HttpAnswer:
        request = prepared.request
        retries = self.config.retries if request.sending.retries is None else request.sending.retries
        after_no_answer = False
        attempt = 0

        while True:
            attempt += 1
            standing = Standing(attempt=attempt, retries=retries)
            self._journal.request(request, attempt)

            try:
                answer = await self._attempt(prepared)
            except (TimeoutError, ConnectionError) as error:
                pause = pause_after_no_answer(standing, self._clock)

                if pause is None:
                    self._journal.rejected(request, error, attempt)
                    raise

                await self._pause(request, attempt, pause)
                after_no_answer = True
                continue

            pause = pause_after_answer(answer, standing, self._clock)

            if pause is None:
                return dataclasses.replace(answer, attempts=attempt, after_no_answer=after_no_answer)

            await self._pause(request, attempt, pause)

    async def _pause(self, request: ApiRequest, attempt: int, pause: RetryPause) -> None:
        self._journal.retry(request, attempt, pause)
        await self._clock.sleep_async(pause.delay_ms / 1000)

    # The whole attempt, headers and body, runs under one deadline; a cancelled task stays cancelled.
    async def _attempt(self, prepared: Prepared) -> HttpAnswer:
        request = self._client.build_request(
            prepared.request.endpoint.method,
            prepared.url,
            headers=prepared.headers,
            content=prepared.request.body,
            timeout=prepared.timeout,
        )

        try:
            async with asyncio.timeout(None if math.isinf(prepared.seconds) else prepared.seconds):
                response = await self._client.send(request, stream=True)

                try:
                    content = await response.aread()
                finally:
                    await response.aclose()
        except (builtins.TimeoutError, httpx.TimeoutException) as error:
            raise timed_out(prepared) from error
        except (httpx.RequestError, OSError) as error:
            raise unreachable(prepared, error) from error

        return answer_of(response, content)

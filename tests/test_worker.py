import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import httpx

from slen import AsyncSlen, Slen
from support.harness import KEY, RecordingLogger, data, run_result

# A server shares one client; the context of a request goes on a copy. A thousand calls, each through a copy of
# its own, find every record of the journal in the logger of their own request.

CALLS = 1000
THREADS = 32


class Echo(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """Answers every run at once, with the idempotency key of its request as the id of the response."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        headers = {"X-Request-Id": request.headers["idempotency-key"], "Content-Type": "application/json"}

        return httpx.Response(200, headers=headers, content=json.dumps(data(run_result())).encode())

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self.handle_request(request)


def own_records(loggers: list[RecordingLogger]) -> list[int]:
    wrong: list[int] = []

    for number, logger in enumerate(loggers):
        ids = [entry.fields.get("request_id") for entry in logger.entries if entry.event == "slen.response"]

        if logger.events() != ["slen.request", "slen.response"] or ids != [f"job-{number}"]:
            wrong.append(number)

    return wrong


def test_a_thousand_calls_in_threads_each_write_to_their_own_logger() -> None:
    shared = Slen(api_key=KEY, http_client=httpx.Client(transport=Echo()))
    loggers = [RecordingLogger() for _ in range(CALLS)]

    def call(number: int) -> str:
        run = shared.with_logger(loggers[number]).operations.execute("op", {}, idempotency_key=f"job-{number}")

        return run.request_id or ""

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        answered = list(pool.map(call, range(CALLS)))

    assert answered == [f"job-{number}" for number in range(CALLS)]
    assert own_records(loggers) == []


def test_a_thousand_tasks_each_write_to_their_own_logger() -> None:
    loggers = [RecordingLogger() for _ in range(CALLS)]

    async def main() -> list[str]:
        shared = AsyncSlen(api_key=KEY, http_client=httpx.AsyncClient(transport=Echo()))

        async def call(number: int) -> str:
            copy = shared.with_logger(loggers[number])
            run = await copy.operations.execute("op", {}, idempotency_key=f"job-{number}")

            return run.request_id or ""

        return list(await asyncio.gather(*(call(number) for number in range(CALLS))))

    assert asyncio.run(main()) == [f"job-{number}" for number in range(CALLS)]
    assert own_records(loggers) == []

import asyncio
import builtins
import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from slen import AsyncSlen, ConnectionError, Slen, TimeoutError
from slen._http import _clock
from slen._http._clock import Clock
from support.harness import KEY, Kind, data, run_view

# The clocks of an attempt, on a real socket of this machine: what httpx does is not what a double does.

ANSWER = json.dumps(data(run_view())).encode()
Behaviour = Callable[[socket.socket, threading.Event], None]


class Server:
    def __init__(self, behaviour: Behaviour) -> None:
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._stop = threading.Event()
        self._behaviour = behaviour
        self._threads: list[threading.Thread] = []
        accepting = threading.Thread(target=self._accept, daemon=True)
        accepting.start()
        self._threads.append(accepting)

    @property
    def address(self) -> str:
        return f"http://127.0.0.1:{self._listener.getsockname()[1]}"

    def _accept(self) -> None:
        self._listener.settimeout(0.1)

        while not self._stop.is_set():
            try:
                connection, _ = self._listener.accept()
            except builtins.TimeoutError:
                continue
            except OSError:
                return

            serving = threading.Thread(target=self._serve, args=(connection,), daemon=True)
            serving.start()
            self._threads.append(serving)

    def _serve(self, connection: socket.socket) -> None:
        with connection:
            received = b""

            while b"\r\n\r\n" not in received:
                chunk = connection.recv(4096)

                if not chunk:
                    return

                received += chunk

            self._behaviour(connection, self._stop)

    def close(self) -> None:
        self._stop.set()
        self._listener.close()

        for thread in self._threads:
            thread.join(timeout=5)


def head(length: int) -> bytes:
    return f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {length}\r\n\r\n".encode()


def silent(connection: socket.socket, stop: threading.Event) -> None:
    stop.wait(10)


def stalled_body(connection: socket.socket, stop: threading.Event) -> None:
    connection.sendall(head(len(ANSWER)) + ANSWER[:10])
    stop.wait(10)


def trickling_body(connection: socket.socket, stop: threading.Event) -> None:
    connection.sendall(head(len(ANSWER)))

    for byte in ANSWER:
        if stop.wait(0.3):
            return

        connection.sendall(bytes([byte]))


def late(seconds: float) -> Behaviour:
    def answer(connection: socket.socket, stop: threading.Event) -> None:
        if not stop.wait(seconds):
            connection.sendall(head(len(ANSWER)) + ANSWER)

    return answer


@pytest.fixture(autouse=True)
def real_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_clock, "SYSTEM_CLOCK", Clock())


@pytest.fixture
def serve() -> Iterator[Callable[[Behaviour], Server]]:
    servers: list[Server] = []

    def start(behaviour: Behaviour) -> Server:
        server = Server(behaviour)
        servers.append(server)

        return server

    yield start

    for server in servers:
        server.close()


def read(kind: Kind, address: str, **options: Any) -> tuple[BaseException | None, float]:
    started = time.monotonic()

    try:
        if kind == "sync":
            read_sync(address, **options)

        if kind == "async":
            asyncio.run(read_async(address, **options))
    except BaseException as error:
        return error, time.monotonic() - started

    return None, time.monotonic() - started


# `yours` stands for an httpx client of the application, built without a timeout: httpx's own is five seconds.
def read_sync(address: str, *, yours: bool = False, **options: Any) -> None:
    with (
        httpx.Client() as http,
        Slen(api_key=KEY, base_url=address, retries=0, **options, **given(http, yours)) as client,
    ):
        client.executions.get("74438200973594700")


async def read_async(address: str, *, yours: bool = False, **options: Any) -> None:
    async with (
        httpx.AsyncClient() as http,
        AsyncSlen(api_key=KEY, base_url=address, retries=0, **options, **given(http, yours)) as client,
    ):
        await client.executions.get("74438200973594700")


def given(http: object, yours: bool) -> dict[str, Any]:
    return {"http_client": http} if yours else {}


def closed_port() -> str:
    with socket.create_server(("127.0.0.1", 0)) as listener:
        port = listener.getsockname()[1]

    return f"http://127.0.0.1:{port}"


def test_a_closed_port_is_a_connection_error(kind: Kind) -> None:
    error, _ = read(kind, closed_port())

    assert isinstance(error, ConnectionError)
    assert error.code is None


def test_headers_that_never_come_are_a_timeout_error(kind: Kind, serve: Callable[[Behaviour], Server]) -> None:
    error, elapsed = read(kind, serve(silent).address, timeout=1.0)

    assert isinstance(error, TimeoutError)
    assert error.code is None
    assert elapsed < 3


def test_a_body_that_stalls_after_its_headers_is_a_timeout_error(
    kind: Kind, serve: Callable[[Behaviour], Server]
) -> None:
    error, elapsed = read(kind, serve(stalled_body).address, timeout=1.0)

    assert isinstance(error, TimeoutError)
    assert elapsed < 3


def test_a_body_that_trickles_past_the_deadline_is_a_timeout_error(
    kind: Kind, serve: Callable[[Behaviour], Server]
) -> None:
    error, elapsed = read(kind, serve(trickling_body).address, timeout=1.0)

    assert isinstance(error, TimeoutError)
    assert elapsed < 3


def test_a_client_of_yours_without_a_timeout_lives_the_sdks(kind: Kind, serve: Callable[[Behaviour], Server]) -> None:
    error, elapsed = read(kind, serve(late(5.6)).address, timeout=10.0, yours=True)

    assert error is None
    assert elapsed > 5.5

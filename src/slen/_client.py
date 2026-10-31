import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Generic, NoReturn, Self, TypeVar

import httpx

from slen._config import DEFAULT_BASE_URL, ClientConfig, ClientOptions, logger_of, resolve_config
from slen._health import Health, health_call
from slen._http import _clock, _pool
from slen._http._async import AsyncTransport
from slen._http._clock import Clock
from slen._http._request import Sending
from slen._http._sync import SyncTransport
from slen._logger import SlenLogger
from slen._modules._context import AsyncContext, SyncContext
from slen._modules.customers._async import AsyncCustomers
from slen._modules.customers._sync import Customers
from slen._modules.executions._async import AsyncExecutions
from slen._modules.executions._sync import Executions
from slen._modules.operations._async import AsyncOperations
from slen._modules.operations._sync import Operations
from slen._modules.webhooks._webhooks import Webhooks
from slen._observability._recorders import NullSpanRecorder, SpanRecorder

C = TypeVar("C", httpx.Client, httpx.AsyncClient)


# What one client is made of; a copy made by with_logger() shares all of it but the logger, and owns no pool.
@dataclass(frozen=True, slots=True, kw_only=True)
class Parts(Generic[C]):
    config: ClientConfig
    http: C
    owns: bool
    spans: SpanRecorder
    clock: Clock


def recorder_of(given: SpanRecorder | None) -> SpanRecorder:
    if given is not None and not callable(getattr(given, "record", None)):
        raise TypeError("Slen: span_recorder has a record(span) method.")

    return NullSpanRecorder() if given is None else given


def webhooks_of(config: ClientConfig) -> Webhooks:
    return Webhooks(
        secret=config.webhook_secret,
        tolerance_seconds=config.webhook_tolerance_seconds,
        logger=config.logger,
    )


def refuse_to_travel() -> NoReturn:
    raise TypeError(
        "Slen: a client holds connections and cannot be pickled or copied; build a client in each process, "
        "and use with_logger() for a copy within one."
    )


class Slen:
    """The Slen client: runs flows, reads their runs, keeps end customers and their credits."""

    __slots__ = ("_parts", "_transport", "customers", "executions", "operations", "webhooks")

    operations: Operations
    executions: Executions
    customers: Customers
    webhooks: Webhooks

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 65.0,
        connect_timeout: float = 5.0,
        retries: int = 2,
        logger: SlenLogger | None = None,
        span_recorder: SpanRecorder | None = None,
        webhook_secret: str | None = None,
        webhook_tolerance_seconds: int = 300,
        http_client: httpx.Client | None = None,
        headers: Mapping[str, str] | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        options = ClientOptions(
            api_key=api_key,
            timeout=timeout,
            connect_timeout=connect_timeout,
            retries=retries,
            logger=logger,
            webhook_secret=webhook_secret,
            webhook_tolerance_seconds=webhook_tolerance_seconds,
            headers=headers,
            base_url=base_url,
        )
        config = resolve_config(options)
        spans = recorder_of(span_recorder)

        if http_client is not None and not isinstance(http_client, httpx.Client):
            raise TypeError("Slen: http_client is an httpx.Client; AsyncSlen takes an httpx.AsyncClient.")

        http = _pool.sync_pool(config) if http_client is None else http_client
        self._build(Parts(config=config, http=http, owns=http_client is None, spans=spans, clock=_clock.SYSTEM_CLOCK))

    def _build(self, parts: Parts[httpx.Client]) -> None:
        self._parts = parts
        self._transport = SyncTransport(parts.config, parts.http, parts.clock)
        context = SyncContext(self._transport, parts.spans)
        self.operations = Operations(context)
        self.executions = Executions(context)
        self.customers = Customers(context)
        self.webhooks = webhooks_of(parts.config)

    def with_logger(self, logger: SlenLogger) -> "Slen":
        """A client like this one that writes its journal to logger, over the same connections and span recorder."""
        parts = self._parts
        copy = type(self).__new__(type(self))
        config = dataclasses.replace(parts.config, logger=logger_of(logger))
        copy._build(dataclasses.replace(parts, config=config, owns=False))

        return copy

    def health(
        self,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> Health:
        """Liveness of the API: a dependency that is down is named in the body, not in the status."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return self._transport.call(health_call(sending))

    def close(self) -> None:
        """Closes the connections of the HTTP client the SDK built; one passed as http_client is left to its owner."""
        if self._parts.owns:
            self._parts.http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Slen(timeout={self._parts.config.timeout!r}, retries={self._parts.config.retries!r})"

    def __reduce__(self) -> NoReturn:
        refuse_to_travel()


class AsyncSlen:
    """The Slen client for asyncio: runs flows, reads their runs, keeps end customers and their credits."""

    __slots__ = ("_parts", "_transport", "customers", "executions", "operations", "webhooks")

    operations: AsyncOperations
    executions: AsyncExecutions
    customers: AsyncCustomers
    webhooks: Webhooks

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 65.0,
        connect_timeout: float = 5.0,
        retries: int = 2,
        logger: SlenLogger | None = None,
        span_recorder: SpanRecorder | None = None,
        webhook_secret: str | None = None,
        webhook_tolerance_seconds: int = 300,
        http_client: httpx.AsyncClient | None = None,
        headers: Mapping[str, str] | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        options = ClientOptions(
            api_key=api_key,
            timeout=timeout,
            connect_timeout=connect_timeout,
            retries=retries,
            logger=logger,
            webhook_secret=webhook_secret,
            webhook_tolerance_seconds=webhook_tolerance_seconds,
            headers=headers,
            base_url=base_url,
        )
        config = resolve_config(options)
        spans = recorder_of(span_recorder)

        if http_client is not None and not isinstance(http_client, httpx.AsyncClient):
            raise TypeError("Slen: http_client is an httpx.AsyncClient; Slen takes an httpx.Client.")

        http = _pool.async_pool(config) if http_client is None else http_client
        self._build(Parts(config=config, http=http, owns=http_client is None, spans=spans, clock=_clock.SYSTEM_CLOCK))

    def _build(self, parts: Parts[httpx.AsyncClient]) -> None:
        self._parts = parts
        self._transport = AsyncTransport(parts.config, parts.http, parts.clock)
        context = AsyncContext(self._transport, parts.spans)
        self.operations = AsyncOperations(context)
        self.executions = AsyncExecutions(context)
        self.customers = AsyncCustomers(context)
        self.webhooks = webhooks_of(parts.config)

    def with_logger(self, logger: SlenLogger) -> "AsyncSlen":
        """A client like this one that writes its journal to logger, over the same connections and span recorder."""
        parts = self._parts
        copy = type(self).__new__(type(self))
        config = dataclasses.replace(parts.config, logger=logger_of(logger))
        copy._build(dataclasses.replace(parts, config=config, owns=False))

        return copy

    async def health(
        self,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        request_id: str | None = None,
    ) -> Health:
        """Liveness of the API: a dependency that is down is named in the body, not in the status."""
        sending = Sending(timeout=timeout, retries=retries, request_id=request_id)

        return await self._transport.call(health_call(sending))

    async def close(self) -> None:
        """Closes the connections of the HTTP client the SDK built; one passed as http_client is left to its owner."""
        if self._parts.owns:
            await self._parts.http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    def __repr__(self) -> str:
        return f"AsyncSlen(timeout={self._parts.config.timeout!r}, retries={self._parts.config.retries!r})"

    def __reduce__(self) -> NoReturn:
        refuse_to_travel()

import math
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from urllib.parse import quote, urlencode

import httpx

from slen._config import ClientConfig
from slen._errors import ConnectionError, TimeoutError
from slen._http._request import PLACEHOLDER, ApiRequest, QueryValue
from slen._version import __version__

USER_AGENT: Final = f"slen-sdk-python/{__version__} python/{platform.python_version()}"

# The headers the SDK owns; `headers` of the client cannot replace them.
OWN_HEADERS: Final = frozenset({"authorization", "accept", "content-type", "idempotency-key"})


# One request, built once for every attempt of its call: the same URL, headers and bytes each time.
@dataclass(frozen=True, slots=True, kw_only=True)
class Prepared:
    request: ApiRequest
    url: str
    headers: Mapping[str, str]
    timeout: httpx.Timeout
    seconds: float


def prepare(config: ClientConfig, request: ApiRequest) -> Prepared:
    seconds = request.sending.timeout if request.sending.timeout is not None else config.timeout

    return Prepared(
        request=request,
        url=url_of(config, request),
        headers=headers_of(config, request),
        timeout=phases_of(seconds, config.connect_timeout),
        seconds=float(seconds),
    )


def url_of(config: ClientConfig, request: ApiRequest) -> str:
    path = PLACEHOLDER.sub(lambda match: quote(request.params[match.group(1)], safe=""), request.endpoint.route)
    query = urlencode([(name, query_text(value)) for name, value in request.query.items() if value is not None])

    return f"{config.base_url}/api{path}" + (f"?{query}" if query else "")


def query_text(value: QueryValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"

    return str(value)


def headers_of(config: ClientConfig, request: ApiRequest) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    own_id = request.sending.request_id

    for name, value in config.headers.items():
        lower = name.lower()

        if lower == "user-agent":
            headers.pop("User-Agent", None)

        # The call's own id wins over one the client sends with every request.
        if lower not in OWN_HEADERS and not (lower == "x-request-id" and own_id is not None):
            headers[name] = value

    headers["Authorization"] = f"Bearer {config.api_key}"
    headers["Accept"] = "application/json"
    headers.update({"Content-Type": "application/json"} if request.body is not None else {})
    headers.update({"Idempotency-Key": request.idempotency_key} if request.idempotency_key is not None else {})
    headers.update({"X-Request-Id": own_id} if own_id is not None else {})

    return headers


# httpx counts by phase; every phase gets the attempt's time, and the connect phase at most its own.
def phases_of(seconds: float, connect: float) -> httpx.Timeout:
    limits = [limit for limit in (seconds, connect) if not math.isinf(limit)]

    return httpx.Timeout(None if math.isinf(seconds) else seconds, connect=min(limits, default=None))


def timed_out(prepared: Prepared) -> TimeoutError:
    return TimeoutError(
        f"Slen did not answer {prepared.request.endpoint} within {prepared.seconds:g} s.",
        request_id=prepared.request.sending.request_id,
    )


def unreachable(prepared: Prepared, cause: BaseException) -> ConnectionError:
    return ConnectionError(
        f"Slen could not be reached for {prepared.request.endpoint}: {describe(cause)}",
        request_id=prepared.request.sending.request_id,
    )


def describe(cause: BaseException) -> str:
    return str(cause) or type(cause).__name__

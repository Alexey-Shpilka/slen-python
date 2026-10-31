import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from slen._logger import SlenLogger, default_logger, is_logger

# The hosted API, `servers[0]` of the spec. Another address is for tests and a local stack only.
DEFAULT_BASE_URL: Final = "https://api.slen.ai"

# The one variable the SDK reads.
KEY_VARIABLE: Final = "SLEN_API_KEY"


@dataclass(frozen=True, slots=True, kw_only=True)
class ClientOptions:
    api_key: str | None = field(repr=False)
    timeout: float
    connect_timeout: float
    retries: int
    logger: SlenLogger | None
    webhook_secret: str | None = field(repr=False)
    webhook_tolerance_seconds: int
    headers: Mapping[str, str] | None
    base_url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ClientConfig:
    api_key: str = field(repr=False)
    base_url: str
    timeout: float
    connect_timeout: float
    retries: int
    headers: Mapping[str, str]
    logger: SlenLogger
    webhook_secret: str | None = field(repr=False)
    webhook_tolerance_seconds: int


def resolve_config(options: ClientOptions) -> ClientConfig:
    return ClientConfig(
        api_key=api_key_of(options.api_key),
        base_url=base_url_of(options.base_url),
        timeout=seconds_of("timeout", options.timeout),
        connect_timeout=seconds_of("connect_timeout", options.connect_timeout),
        retries=whole("retries", options.retries, 0),
        headers=headers_of(options.headers),
        logger=logger_of(options.logger),
        webhook_secret=secret_of(options.webhook_secret),
        webhook_tolerance_seconds=whole("webhook_tolerance_seconds", options.webhook_tolerance_seconds, 1),
    )


def api_key_of(given: str | None) -> str:
    key: object = os.environ.get(KEY_VARIABLE) if given is None else given

    if key is not None and not isinstance(key, str):
        raise TypeError("Slen: api_key is a string.")

    if key is None or not key.strip():
        raise ValueError(f"Slen: an api_key is required (pass api_key or set {KEY_VARIABLE}).")

    return key


def base_url_of(given: str) -> str:
    if not isinstance(given, str) or not given.strip():
        raise ValueError("Slen: the address of the API is a URL that is not empty.")

    return given.rstrip("/")


def seconds_of(name: str, value: object) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"Slen: {name} is a number of seconds, got {type(value).__name__}.")

    # Negated on purpose: NaN is not above 0 either.
    if not value > 0:
        raise ValueError(f"Slen: {name} must be a number above 0, got {value!r}.")

    return float(value)


def whole(name: str, value: object, least: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Slen: {name} is an integer, got {type(value).__name__}.")

    if value < least:
        raise ValueError(f"Slen: {name} must be an integer of at least {least}, got {value!r}.")

    return value


def headers_of(given: Mapping[str, str] | None) -> Mapping[str, str]:
    headers = dict(given or {})

    if not all(isinstance(name, str) and isinstance(value, str) for name, value in headers.items()):
        raise TypeError("Slen: headers is a mapping of strings to strings.")

    return MappingProxyType(headers)


def logger_of(given: SlenLogger | None) -> SlenLogger:
    if given is not None and not is_logger(given):
        raise TypeError("Slen: logger has debug, info, warning and error, as logging.Logger has.")

    return default_logger() if given is None else given


# An empty or blank secret is a variable that was not set, not a secret.
def secret_of(given: str | None) -> str | None:
    if given is not None and not isinstance(given, str):
        raise TypeError("Slen: webhook_secret is a string.")

    return None if given is None or not given.strip() else given

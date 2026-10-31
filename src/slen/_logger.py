import contextlib
import logging
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Protocol

LOGGER_NAME: Final = "slen"

# The events of the journal; the PHP and TypeScript SDKs write the same names with the same fields.
LOG_EVENTS: Final[tuple[str, ...]] = (
    "slen.request",
    "slen.response",
    "slen.retry",
    "slen.refused",
    "slen.unauthorized",
    "slen.failed",
    "slen.wait.poll",
    "slen.wait.poll_failed",
    "slen.webhook.rejected",
)

LEVELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "slen.request": "debug",
        "slen.response": "debug",
        "slen.retry": "warning",
        "slen.refused": "info",
        "slen.unauthorized": "error",
        "slen.failed": "error",
        "slen.wait.poll": "debug",
        "slen.wait.poll_failed": "warning",
        "slen.webhook.rejected": "warning",
    }
)


class SlenLogger(Protocol):
    """Where the SDK writes its journal: a logging.Logger, a LoggerAdapter, or anything with these four methods."""

    def debug(self, msg: str, /, *, extra: Mapping[str, object] | None = ...) -> None:
        """Writes an event of the journal at the debug level."""
        ...

    def info(self, msg: str, /, *, extra: Mapping[str, object] | None = ...) -> None:
        """Writes an event of the journal at the info level."""
        ...

    def warning(self, msg: str, /, *, extra: Mapping[str, object] | None = ...) -> None:
        """Writes an event of the journal at the warning level."""
        ...

    def error(self, msg: str, /, *, extra: Mapping[str, object] | None = ...) -> None:
        """Writes an event of the journal at the error level."""
        ...


logging.getLogger(LOGGER_NAME).addHandler(logging.NullHandler())


def default_logger() -> SlenLogger:
    return logging.getLogger(LOGGER_NAME)


def is_logger(value: object) -> bool:
    return all(callable(getattr(value, level, None)) for level in ("debug", "info", "warning", "error"))


def write_log(logger: SlenLogger, event: str, fields: Mapping[str, object]) -> None:
    # The journal is telemetry: a logger that throws does not fail the call.
    with contextlib.suppress(Exception):
        getattr(logger, LEVELS[event])(event, extra=dict(fields))

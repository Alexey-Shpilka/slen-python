import contextlib
import logging
from types import MappingProxyType
from typing import Final, Protocol

from slen._logger import SlenLogger, is_logger
from slen._observability._span import SlenSpan, attributes_of

METHOD_OF_LEVEL: Final = MappingProxyType(
    {logging.DEBUG: "debug", logging.INFO: "info", logging.WARNING: "warning", logging.ERROR: "error"}
)


class SpanRecorder(Protocol):
    """Where finished spans go: record() runs on the path of the call and must not block."""

    def record(self, span: SlenSpan) -> None:
        """Takes one finished span."""
        ...


class LoggerSpanRecorder:
    """Writes each span as one slen.span line of a logger, its attributes as the fields of the record."""

    def __init__(self, logger: SlenLogger, *, level: int = logging.INFO) -> None:
        if not is_logger(logger):
            raise TypeError("Slen: a LoggerSpanRecorder writes to a logger with debug, info, warning and error.")

        if level not in METHOD_OF_LEVEL:
            raise ValueError("Slen: the level of a LoggerSpanRecorder is DEBUG, INFO, WARNING or ERROR of logging.")

        self._logger = logger
        self._method = METHOD_OF_LEVEL[level]

    def record(self, span: SlenSpan) -> None:
        """Writes the span as one line."""
        getattr(self._logger, self._method)("slen.span", extra=attributes_of(span))


class NullSpanRecorder:
    __slots__ = ()

    def record(self, span: SlenSpan) -> None:
        pass


# A recorder is telemetry: one that throws does not fail the call it describes.
def record_safely(recorder: SpanRecorder, span: SlenSpan) -> None:
    with contextlib.suppress(Exception):
        recorder.record(span)

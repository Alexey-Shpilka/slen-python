"""The spans of the SDK as OpenTelemetry spans, through a tracer of the application; needs slen[otel]."""

import time

try:
    from opentelemetry import trace
except ImportError:
    raise ImportError('slen.otel needs OpenTelemetry: pip install "slen[otel]"') from None

from slen._observability._span import SlenSpan, attributes_of


class OtelSpanRecorder:
    """Writes each span through an OpenTelemetry tracer, so that it joins the traces of the application."""

    def __init__(self, tracer: trace.Tracer | None = None) -> None:
        self._tracer = trace.get_tracer("slen") if tracer is None else tracer

    def record(self, span: SlenSpan) -> None:
        """Writes the span, ended now and started duration_ms before; an outcome other than ok is an error status."""
        end = time.time_ns()
        started = end - span.duration_ms * 1_000_000
        written = self._tracer.start_span(
            f"slen.{span.operation}",
            kind=trace.SpanKind.CLIENT,
            start_time=started,
            attributes=attributes_of(span),
        )

        if span.outcome != "ok":
            written.set_status(trace.Status(trace.StatusCode.ERROR, span.error_code or span.outcome))

        written.end(end_time=end)


__all__ = ("OtelSpanRecorder",)

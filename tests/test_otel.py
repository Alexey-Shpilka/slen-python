# pyright: reportPrivateUsage=false
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from slen.otel import OtelSpanRecorder
from slen.testing import FakeTransport
from support.harness import Kind, data, drive, raised, run_result


def tracing() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    return provider, exporter


def test_a_run_becomes_a_client_span_of_the_application(kind: Kind) -> None:
    provider, exporter = tracing()
    fake = FakeTransport().push(200, data(run_result()))
    recorder = OtelSpanRecorder(provider.get_tracer("tests"))

    drive(kind, fake, lambda slen: slen.operations.execute("support.answer", {}), span_recorder=recorder)
    (span,) = exporter.get_finished_spans()

    assert span.name == "slen.operations.execute"
    assert span.kind is SpanKind.CLIENT
    assert dict(span.attributes or {}) == {
        "operation": "operations.execute",
        "outcome": "ok",
        "status": "completed",
        "duration_ms": 0,
        "execution_id": "74438200973594700",
        "operation_code": "support.answer",
        "estimated": "0.00412500",
        "cache_hit": False,
    }
    assert span.status.status_code is StatusCode.UNSET


def test_a_refused_run_is_a_span_with_an_error_status(kind: Kind) -> None:
    provider, exporter = tracing()
    fake = FakeTransport().push(402, {"error": {"code": "budget_exceeded"}})

    raised(
        kind,
        fake,
        lambda slen: slen.operations.execute("support.answer", {}),
        span_recorder=OtelSpanRecorder(provider.get_tracer("tests")),
    )
    (span,) = exporter.get_finished_spans()

    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "budget_exceeded"


def test_without_a_tracer_the_global_one_named_slen_is_used() -> None:
    assert OtelSpanRecorder()._tracer is not None

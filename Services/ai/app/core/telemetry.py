"""
telemetry.py — OpenTelemetry setup for the AI Service.

Configures OTLP gRPC exporter → Jaeger / Tempo / OTEL Collector.
Only active when settings.OTEL_ENABLED is True.

Owned by: AI Service.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_tracer_provider = None


def setup_telemetry(service_name: str, endpoint: str) -> None:
    """Configure OTLP span exporter and register global TracerProvider."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        global _tracer_provider
        _tracer_provider = provider

        logger.info(
            "OpenTelemetry configured",
            extra={"service": service_name, "endpoint": endpoint},
        )
    except ImportError:
        logger.warning("opentelemetry-sdk not installed — telemetry disabled")
    except Exception as exc:
        logger.warning("OpenTelemetry setup failed", extra={"error": str(exc)})


def get_tracer(name: str):
    """Returns an OpenTelemetry Tracer. Falls back to a no-op tracer if OTel unavailable."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


def get_current_trace_id() -> str | None:
    """Returns the current span's trace ID as a hex string, or None."""
    try:
        from opentelemetry import trace
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return None


class _NoOpSpan:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def set_attribute(self, *args): pass
    def set_status(self, *args): pass
    def record_exception(self, *args): pass


class _NoOpTracer:
    def start_as_current_span(self, name, **kwargs):
        return _NoOpSpan()

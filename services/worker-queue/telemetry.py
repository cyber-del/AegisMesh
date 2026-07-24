"""OpenTelemetry tracing + logging setup for AegisMesh services.

Kept deliberately small and explicit (no auto-instrument CLI magic) so the export path is
obvious and fully env-configurable. Import paths are pinned against the verified OTel
1.44.0 install — the logs API still lives under the `_logs` / `_log_exporter` (underscore)
modules in this version; do not "modernize" them without re-probing the SDK.

configure_telemetry() wires BOTH signals off one shared Resource and returns
(tracer, logger). The returned logger is a stdlib logger whose records are exported to
SigNoz over OTLP and automatically carry the active span's trace_id/span_id — that is what
makes trace<->log click-through work.
"""
import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter


def _resource(service_name: str) -> Resource:
    # service.name is the field SigNoz groups by; string keys avoid coupling to a moving
    # SERVICE_NAME import path.
    return Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("SERVICE_VERSION", "0.1.0"),
            "deployment.environment": os.getenv("DEPLOYMENT_ENV", "hackathon"),
        }
    )


def configure_telemetry(service_name: str):
    """Set up trace + log export to SigNoz over OTLP/gRPC. Returns (tracer, logger)."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    resource = _resource(service_name)

    # --- traces ---
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # --- logs --- (the separate export path; without this, IDs go nowhere)
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )

    otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))

    app_logger = logging.getLogger(service_name)
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(otel_handler)  # -> SigNoz, correlated to the active span
    app_logger.addHandler(console)       # -> local stdout, for debugging
    app_logger.propagate = False

    return trace.get_tracer(service_name), app_logger

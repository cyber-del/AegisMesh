"""OpenTelemetry tracing setup for AegisMesh services.

Kept deliberately small and explicit (no auto-instrument CLI magic) so the export
path is obvious and fully env-configurable. Import paths here are pinned against the
verified 1.44.0 / 0.65b0 OTel release set — do not "modernize" them without checking
the docs, the SDK moves things around between versions.
"""
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


def configure_tracing(service_name: str) -> trace.Tracer:
    """Wire a global TracerProvider that exports spans to SigNoz over OTLP/gRPC.

    Endpoint is read from OTEL_EXPORTER_OTLP_ENDPOINT (default the local SigNoz
    ingester at http://localhost:4317). `insecure=True` because the self-hosted
    collector speaks plaintext gRPC on 4317.
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # service.name is the field SigNoz groups traces by. We use string keys rather
    # than the SERVICE_NAME constant to avoid coupling to a moving import path.
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("SERVICE_VERSION", "0.1.0"),
            "deployment.environment": os.getenv("DEPLOYMENT_ENV", "hackathon"),
        }
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)

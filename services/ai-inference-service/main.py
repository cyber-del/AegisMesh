"""ai-inference-service — a fake LLM inference endpoint, fully traced.

POST /v1/infer accepts a prompt, simulates an LLM call with a small realistic delay,
and returns generated text plus token counts. Every request produces one OpenTelemetry
trace: the FastAPI server span plus a child "llm.generate" span carrying the token
counts as attributes (high-cardinality data belongs on spans, not metric labels).

Chaos faults (latency / rate-limit) are added in Phase 7 on top of this baseline.
"""
import asyncio
import os
import random
import time
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from telemetry import configure_telemetry

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "ai-inference-service")
MODEL_NAME = os.getenv("MODEL_NAME", "aegis-sim-1")
# Baseline per-request latency. Phase 7 Fault A will inflate this to 3-5s at runtime.
BASE_LATENCY_MS = int(os.getenv("INFER_BASE_LATENCY_MS", "150"))

tracer, log = configure_telemetry(SERVICE_NAME)

app = FastAPI(title="AegisMesh ai-inference-service", version="0.1.0")
# Auto-instrument inbound HTTP: creates the server span for every request.
FastAPIInstrumentor.instrument_app(app)


class InferRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 128


class InferResponse(BaseModel):
    model: str
    generated_text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token, floor of 1."""
    return max(1, len(text) // 4)


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME, "model": MODEL_NAME}


@app.post("/v1/infer", response_model=InferResponse)
async def infer(req: InferRequest):
    start = time.perf_counter()
    input_tokens = estimate_tokens(req.prompt)
    cap = min(req.max_tokens or 128, 512)
    log.info("inference request received (input_tokens=%d, max_tokens=%d)", input_tokens, cap)

    with tracer.start_as_current_span("llm.generate") as span:
        # Simulate model work. Kept short here; chaos inflates it later.
        delay_s = (BASE_LATENCY_MS + random.randint(0, 100)) / 1000.0
        await asyncio.sleep(delay_s)

        generated_text = f"[{MODEL_NAME}] response to: {req.prompt[:60]}"
        output_tokens = estimate_tokens(generated_text) + random.randint(5, cap)

        # Token counts + model as span attributes (bounded label sets go on metrics
        # in Phase 5; per-request values live here on the span).
        span.set_attribute("gen_ai.request.model", MODEL_NAME)
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        span.set_attribute("gen_ai.prompt.length_chars", len(req.prompt))

    latency_ms = int((time.perf_counter() - start) * 1000)
    return InferResponse(
        model=MODEL_NAME,
        generated_text=generated_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )

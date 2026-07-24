"""ai-inference-service — a fake LLM inference endpoint, fully traced, with two chaos faults.

POST /v1/infer accepts a prompt, simulates an LLM call, returns text + token counts. Every
request produces one OpenTelemetry trace (server span + "llm.generate" child) and records a
GenAI token-usage histogram.

Two INDEPENDENT chaos faults, both off by default, with DIFFERENT correct remediations:

  Fault A — POST /chaos/inject-latency
    Inference becomes slow (3-5s) but still SUCCEEDS and still handles work in parallel.
    Cascade: worker-queue slots are held 3-5s -> pool saturates -> gateway 5s timeout -> 504.
    Correct fix: RAISE worker concurrency (downstream has headroom).

  Fault B — POST /chaos/inject-token-ratelimit
    Inference is CAPACITY-limited: it rejects requests with 429 / "TokenQuotaExceeded" once
    concurrent in-flight exceeds a small capacity. It is load-SENSITIVE, not slow.
    Cascade: worker retries (holding slots) -> pool saturates -> some 504s, plus 429s.
    Correct fix: REDUCE load on the downstream (lower sampling / enable fallback). Raising
    concurrency floods the capacity-limited service and makes it WORSE.

  POST /chaos/reset clears all faults.
"""
import asyncio
import os
import random
import time
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from telemetry import configure_telemetry

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "ai-inference-service")
MODEL_NAME = os.getenv("MODEL_NAME", "aegis-sim-1")
BASE_LATENCY_MS = int(os.getenv("INFER_BASE_LATENCY_MS", "150"))

tracer, log, meter = configure_telemetry(SERVICE_NAME)

token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description="Number of input and output tokens used per GenAI request",
)

# --- chaos state (all faults OFF by default) ---
chaos_state = {
    "latency": False,
    "latency_min_s": float(os.getenv("CHAOS_LATENCY_MIN_S", "3.0")),
    "latency_max_s": float(os.getenv("CHAOS_LATENCY_MAX_S", "5.0")),
    "ratelimit": False,
    # Max concurrent inferences allowed under the rate-limit fault; excess -> 429. Default 1
    # (severe) so the cascade reaches api-gateway as 504s at the steady ~15-concurrent load.
    "capacity": int(os.getenv("CHAOS_RATELIMIT_CAPACITY", "1")),
}
_inflight = 0  # current concurrent inferences (single event loop -> no lock needed)

app = FastAPI(title="AegisMesh ai-inference-service", version="0.1.0")
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


class LatencyChaos(BaseModel):
    min_s: Optional[float] = None
    max_s: Optional[float] = None


class RateLimitChaos(BaseModel):
    capacity: Optional[int] = None


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME, "model": MODEL_NAME,
            "chaos": chaos_state, "inflight": _inflight}


@app.post("/v1/infer", response_model=InferResponse)
async def infer(req: InferRequest):
    global _inflight
    start = time.perf_counter()
    input_tokens = estimate_tokens(req.prompt)
    cap = min(req.max_tokens or 128, 512)
    span = trace.get_current_span()

    # --- Fault B: capacity-limited rate limit. Reject fast (no work) when over capacity. ---
    if chaos_state["ratelimit"] and _inflight >= chaos_state["capacity"]:
        span.set_attribute("error.type", "RateLimitError")
        span.set_attribute("gen_ai.response.finish_reason", "rate_limit")
        log.warning("TokenQuotaExceeded: over capacity (inflight=%d cap=%d) -> 429",
                    _inflight, chaos_state["capacity"])
        return JSONResponse(status_code=429,
                            content={"error": "TokenQuotaExceeded", "code": "rate_limit"})

    _inflight += 1
    log.info("inference request received (input_tokens=%d, max_tokens=%d)", input_tokens, cap)
    try:
        with tracer.start_as_current_span("llm.generate") as gen_span:
            # --- Fault A: injected latency. Still succeeds; still parallel-capable. ---
            if chaos_state["latency"]:
                delay_s = random.uniform(chaos_state["latency_min_s"], chaos_state["latency_max_s"])
            else:
                delay_s = (BASE_LATENCY_MS + random.randint(0, 100)) / 1000.0
            await asyncio.sleep(delay_s)

            generated_text = f"[{MODEL_NAME}] response to: {req.prompt[:60]}"
            output_tokens = estimate_tokens(generated_text) + random.randint(5, cap)

            gen_span.set_attribute("gen_ai.request.model", MODEL_NAME)
            gen_span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
            gen_span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
            gen_span.set_attribute("gen_ai.prompt.length_chars", len(req.prompt))
            token_usage.record(input_tokens, {"gen_ai.token.type": "input", "gen_ai.request.model": MODEL_NAME})
            token_usage.record(output_tokens, {"gen_ai.token.type": "output", "gen_ai.request.model": MODEL_NAME})
    finally:
        _inflight -= 1

    latency_ms = int((time.perf_counter() - start) * 1000)
    return InferResponse(
        model=MODEL_NAME,
        generated_text=generated_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )


# --------------------------------------------------------------------------------------
# Chaos control plane
# --------------------------------------------------------------------------------------
@app.post("/chaos/inject-latency")
async def inject_latency(cfg: Optional[LatencyChaos] = None):
    """Fault A: make inference slow (3-5s by default) but still successful."""
    chaos_state["latency"] = True
    if cfg:
        if cfg.min_s is not None:
            chaos_state["latency_min_s"] = cfg.min_s
        if cfg.max_s is not None:
            chaos_state["latency_max_s"] = cfg.max_s
    log.warning("CHAOS latency injected (%.1f-%.1fs per request)",
                chaos_state["latency_min_s"], chaos_state["latency_max_s"])
    return {"status": "latency_injected", "chaos": chaos_state}


@app.post("/chaos/inject-token-ratelimit")
async def inject_token_ratelimit(cfg: Optional[RateLimitChaos] = None):
    """Fault B: reject with 429/TokenQuotaExceeded once in-flight exceeds capacity."""
    chaos_state["ratelimit"] = True
    if cfg and cfg.capacity is not None:
        chaos_state["capacity"] = cfg.capacity
    log.warning("CHAOS token rate-limit injected (capacity=%d concurrent)", chaos_state["capacity"])
    return {"status": "ratelimit_injected", "chaos": chaos_state}


@app.post("/chaos/reset")
async def chaos_reset():
    """Clear all faults."""
    chaos_state["latency"] = False
    chaos_state["ratelimit"] = False
    log.warning("CHAOS reset — all faults cleared")
    return {"status": "reset", "chaos": chaos_state}

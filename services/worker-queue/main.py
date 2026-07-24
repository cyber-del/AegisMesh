"""worker-queue — bounded concurrency pool in front of ai-inference-service.

Each in-flight /v1/process request occupies one pool slot for its ENTIRE duration,
including any retries. The pool size is small by default (5) and can be resized live via
POST /admin/config without a restart — that live resize is the remediation the AI
controller applies for the latency fault (Phase 7 Fault A).

Why the retry holds the slot: it is what turns a slow or failing downstream into a real
cascade. Slots stay occupied -> the pool saturates -> new requests queue -> api-gateway's
5s budget is exceeded -> 504s. Nothing here is hardcoded to fail; the failure emerges from
genuine resource exhaustion.

Instrumented with FastAPI (server span) + httpx (client span, propagates context onward).
"""
import asyncio
import json
import os
import random
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Response
from pydantic import BaseModel

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from telemetry import configure_telemetry

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "worker-queue")
AI_INFERENCE_URL = os.getenv("AI_INFERENCE_URL", "http://localhost:8003")
MAX_WORKER_CONCURRENCY = int(os.getenv("MAX_WORKER_CONCURRENCY", "5"))
# Retry-with-backoff on downstream 429/5xx. The backoff is deliberately substantial: a
# retrying request keeps holding its pool slot, so under the rate-limit fault (Fault B)
# the pool saturates and the cascade reaches api-gateway as 504s (not just passed-through
# 429s). Healthy traffic and Fault A never retry, so this only shapes the failure path.
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_BACKOFF_MS = int(os.getenv("RETRY_BACKOFF_MS", "500"))
DOWNSTREAM_TIMEOUT_MS = int(os.getenv("DOWNSTREAM_TIMEOUT_MS", "10000"))

tracer, log, _meter = configure_telemetry(SERVICE_NAME)
HTTPXClientInstrumentor().instrument()


class ResizablePool:
    """An async concurrency limiter whose capacity can change at runtime.

    Unlike asyncio.Semaphore, `max` is mutable: resize() adjusts it and wakes waiters.
    Resizing DOWN never kills in-flight work — it just makes new acquires wait until
    active drops below the new max.
    """

    def __init__(self, size: int):
        self._max = size
        self._active = 0
        self._cond = asyncio.Condition()

    async def acquire(self) -> bool:
        """Occupy a slot. Returns True if the request had to wait (pool was saturated)."""
        async with self._cond:
            waited = self._active >= self._max
            while self._active >= self._max:
                await self._cond.wait()
            self._active += 1
            return waited

    async def release(self) -> None:
        async with self._cond:
            self._active -= 1
            self._cond.notify_all()

    async def resize(self, new_max: int) -> None:
        async with self._cond:
            self._max = new_max
            self._cond.notify_all()

    def stats(self) -> dict:
        return {"max": self._max, "active": self._active}


pool = ResizablePool(MAX_WORKER_CONCURRENCY)

# Runtime config the AI controller can toggle. Behaviour for the Phase 7 fault-B knobs
# (sampling / fallback) is wired in Phase 7; accepted and stored now for a stable contract.
config_state = {
    "LLM_SAMPLING_RATE": float(os.getenv("LLM_SAMPLING_RATE", "1.0")),
    "FALLBACK_ROUTING": os.getenv("FALLBACK_ROUTING", "false").lower() == "true",
}

client: httpx.AsyncClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = httpx.AsyncClient(timeout=httpx.Timeout(DOWNSTREAM_TIMEOUT_MS / 1000.0))
    yield
    await client.aclose()


app = FastAPI(title="AegisMesh worker-queue", version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)


class ProcessRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 128


class ConfigRequest(BaseModel):
    MAX_WORKER_CONCURRENCY: Optional[int] = None
    LLM_SAMPLING_RATE: Optional[float] = None
    FALLBACK_ROUTING: Optional[bool] = None


def _retryable(status_code: int) -> bool:
    """429 (rate limited) and 5xx are worth retrying; everything else is final."""
    return status_code == 429 or status_code >= 500


def _fallback_response(req: "ProcessRequest") -> Response:
    """A cheap, downstream-free 200. Used to shed load off a rate-limited backend."""
    body = json.dumps({
        "model": "fallback",
        "generated_text": "[degraded] fallback response (downstream load-shed)",
        "input_tokens": max(1, len(req.prompt) // 4),
        "output_tokens": 0,
        "latency_ms": 0,
        "fallback": True,
    })
    return Response(content=body, status_code=200, media_type="application/json")


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME, "pool": pool.stats(), "config": config_state}


@app.post("/v1/process")
async def process(req: ProcessRequest):
    span = trace.get_current_span()
    log.info("process request received (prompt_chars=%d)", len(req.prompt))

    # Fault-B remediation (controller-set): shed load off the downstream BEFORE taking a
    # pool slot. FALLBACK_ROUTING sheds everything; LLM_SAMPLING_RATE<1 sheds a fraction.
    # This is the CORRECT fix for the rate-limit fault and the WRONG one for latency.
    if config_state["FALLBACK_ROUTING"] or random.random() > config_state["LLM_SAMPLING_RATE"]:
        span.set_attribute("worker.fallback", True)
        log.info("serving fallback (sampling_rate=%.2f fallback_routing=%s) — downstream skipped",
                 config_state["LLM_SAMPLING_RATE"], config_state["FALLBACK_ROUTING"])
        return _fallback_response(req)

    waited = await pool.acquire()  # occupy a slot for the whole request, retries included
    stats = pool.stats()
    span.set_attribute("worker.pool.active", stats["active"])
    span.set_attribute("worker.pool.max", stats["max"])
    if waited:
        # This is the saturation signal the AI controller looks for in Fault A.
        log.warning("pool slot exhausted; request queued then acquired (active=%d max=%d)",
                    stats["active"], stats["max"])
    else:
        log.info("pool slot acquired (active=%d max=%d)", stats["active"], stats["max"])
    try:
        last_resp: Optional[httpx.Response] = None
        attempts = 0
        for attempt in range(MAX_RETRIES + 1):
            attempts = attempt + 1
            try:
                resp = await client.post(f"{AI_INFERENCE_URL}/v1/infer", json=req.model_dump())
                if not _retryable(resp.status_code):
                    span.set_attribute("worker.retries", attempt)
                    return Response(
                        content=resp.content,
                        status_code=resp.status_code,
                        media_type=resp.headers.get("content-type", "application/json"),
                    )
                last_resp = resp  # retryable status -> loop again (still holding the slot)
                if resp.status_code == 429:
                    log.warning("downstream rate limited (429) on attempt %d/%d",
                                attempt + 1, MAX_RETRIES + 1)
                else:
                    log.warning("downstream returned %d on attempt %d/%d",
                                resp.status_code, attempt + 1, MAX_RETRIES + 1)
            except httpx.HTTPError as exc:
                last_resp = None
                log.warning("downstream call failed (%s) on attempt %d/%d",
                            type(exc).__name__, attempt + 1, MAX_RETRIES + 1)
            if attempt < MAX_RETRIES:
                log.info("retry attempt %d after backoff", attempt + 2)
                await asyncio.sleep((RETRY_BACKOFF_MS * (2 ** attempt)) / 1000.0)

        span.set_attribute("worker.retries", attempts - 1)
        if last_resp is not None:
            return Response(
                content=last_resp.content,
                status_code=last_resp.status_code,
                media_type=last_resp.headers.get("content-type", "application/json"),
            )
        return Response(
            content='{"error":"downstream unreachable from worker-queue","code":"bad_gateway"}',
            status_code=502,
            media_type="application/json",
        )
    finally:
        await pool.release()


@app.post("/admin/config")
async def admin_config(cfg: ConfigRequest):
    """Live-reconfigure the worker. The AI controller calls this to remediate faults."""
    changed = {}
    if cfg.MAX_WORKER_CONCURRENCY is not None:
        await pool.resize(cfg.MAX_WORKER_CONCURRENCY)
        changed["MAX_WORKER_CONCURRENCY"] = cfg.MAX_WORKER_CONCURRENCY
    if cfg.LLM_SAMPLING_RATE is not None:
        config_state["LLM_SAMPLING_RATE"] = cfg.LLM_SAMPLING_RATE
        changed["LLM_SAMPLING_RATE"] = cfg.LLM_SAMPLING_RATE
    if cfg.FALLBACK_ROUTING is not None:
        config_state["FALLBACK_ROUTING"] = cfg.FALLBACK_ROUTING
        changed["FALLBACK_ROUTING"] = cfg.FALLBACK_ROUTING
    log.info("admin config updated: %s (pool now max=%d)", changed, pool.stats()["max"])
    return {"status": "updated", "changed": changed, "pool": pool.stats(), "config": config_state}

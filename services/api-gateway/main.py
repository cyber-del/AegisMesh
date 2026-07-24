"""api-gateway — the front door. Forwards /v1/generate to worker-queue with a hard timeout.

If worker-queue does not respond within GATEWAY_TIMEOUT_MS (default 5000ms), the gateway
returns HTTP 504. Under Phase 7 chaos, this is where the user-visible failure appears: the
downstream cascade saturates worker-queue, requests queue past 5s, and these 504s surface
here on their own.

Instrumented with FastAPI (inbound server span) + httpx (outbound client span). The httpx
instrumentation injects the W3C traceparent header, so the worker-queue and ai-inference
spans join THIS trace instead of starting new ones.
"""
import os
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Response
from pydantic import BaseModel

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from telemetry import configure_telemetry

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "api-gateway")
WORKER_QUEUE_URL = os.getenv("WORKER_QUEUE_URL", "http://localhost:8002")
GATEWAY_TIMEOUT_MS = int(os.getenv("GATEWAY_TIMEOUT_MS", "5000"))

_, log = configure_telemetry(SERVICE_NAME)
HTTPXClientInstrumentor().instrument()  # traces + propagates context on all httpx calls

# One shared async client; the 5s timeout is the whole point of this service.
client = httpx.AsyncClient(timeout=httpx.Timeout(GATEWAY_TIMEOUT_MS / 1000.0))


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client.aclose()


app = FastAPI(title="AegisMesh api-gateway", version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 128


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/v1/generate")
async def generate(req: GenerateRequest):
    log.info("generate request received (prompt_chars=%d)", len(req.prompt))
    try:
        resp = await client.post(f"{WORKER_QUEUE_URL}/v1/process", json=req.model_dump())
    except httpx.TimeoutException:
        # The failure the demo cares about: downstream took longer than our budget.
        log.warning("gateway timeout: downstream exceeded %dms budget -> 504", GATEWAY_TIMEOUT_MS)
        return Response(
            content='{"error":"upstream timeout at api-gateway","code":"gateway_timeout"}',
            status_code=504,
            media_type="application/json",
        )
    except httpx.HTTPError as exc:
        log.warning("upstream unreachable (%s) -> 502", type(exc).__name__)
        return Response(
            content=f'{{"error":"upstream unreachable at api-gateway","detail":"{type(exc).__name__}"}}',
            status_code=502,
            media_type="application/json",
        )
    # Pass the worker-queue response straight through, preserving its status code.
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )

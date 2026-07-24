"""load-generator — drives steady concurrent traffic through api-gateway.

Why it exists: (1) keep the SigNoz dashboards populated, and (2) supply the sustained
concurrent load that Phase 7's fault cascade needs — a bounded worker pool only saturates
when several requests are in flight at once.

Deliberately un-instrumented (no OpenTelemetry): api-gateway stays the trace root. Its HTTP
timeout is intentionally longer than the gateway's 5s budget so that when Phase 7 makes the
gateway return 504, we RECORD the 504 rather than timing out on our side first.

All knobs are env vars:
  TARGET_URL            default http://localhost:8001/v1/generate
  CONCURRENCY           number of concurrent workers (in-flight requests). default 15
  THINK_TIME_MS         per-worker pause between requests (jittered 0..N). default 0
  LOADGEN_MAX_TOKENS    max_tokens sent on each request. default 64
  LOADGEN_DURATION_S    stop after N seconds (0 = run forever). default 0
  LOADGEN_TIMEOUT_S     per-request client timeout. default 20 (> gateway's 5s)
  REPORT_EVERY_S        stats print interval. default 5
"""
import asyncio
import os
import random
import signal
import time

import httpx

TARGET_URL = os.getenv("TARGET_URL", "http://localhost:8001/v1/generate")
CONCURRENCY = int(os.getenv("CONCURRENCY", "15"))
THINK_TIME_MS = int(os.getenv("THINK_TIME_MS", "0"))
MAX_TOKENS = int(os.getenv("LOADGEN_MAX_TOKENS", "64"))
DURATION_S = int(os.getenv("LOADGEN_DURATION_S", "0"))
TIMEOUT_S = float(os.getenv("LOADGEN_TIMEOUT_S", "20"))
REPORT_EVERY_S = float(os.getenv("REPORT_EVERY_S", "5"))

PROMPTS = [
    "Summarize the incident in one sentence.",
    "What is the root cause of elevated latency?",
    "Explain backpressure to a new engineer.",
    "Draft a status update for the on-call channel.",
    "List three ways to reduce tail latency.",
    "Translate this alert into plain English.",
]

stats = {"sent": 0, "ok": 0, "http_504": 0, "http_429": 0, "http_5xx": 0, "err": 0}
_running = True


async def worker(client: httpx.AsyncClient):
    while _running:
        prompt = random.choice(PROMPTS)
        try:
            r = await client.post(TARGET_URL, json={"prompt": prompt, "max_tokens": MAX_TOKENS})
            stats["sent"] += 1
            if r.status_code == 200:
                stats["ok"] += 1
            elif r.status_code == 504:
                stats["http_504"] += 1
            elif r.status_code == 429:
                stats["http_429"] += 1
            elif r.status_code >= 500:
                stats["http_5xx"] += 1
            else:
                stats["err"] += 1
        except Exception:
            stats["sent"] += 1
            stats["err"] += 1
        if THINK_TIME_MS:
            await asyncio.sleep(random.uniform(0, THINK_TIME_MS) / 1000.0)


async def reporter(started: float):
    prev = 0
    while _running:
        await asyncio.sleep(REPORT_EVERY_S)
        sent = stats["sent"]
        rps = (sent - prev) / REPORT_EVERY_S
        prev = sent
        print(
            f"[loadgen] t={int(time.time()-started)}s conc={CONCURRENCY} rps~{rps:.1f} "
            f"sent={sent} ok={stats['ok']} 504={stats['http_504']} 429={stats['http_429']} "
            f"5xx={stats['http_5xx']} err={stats['err']}",
            flush=True,
        )


async def main():
    global _running

    def stop(*_):
        global _running
        _running = False

    try:
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
    except (ValueError, AttributeError):
        pass  # signals not settable on some platforms/threads

    print(
        f"[loadgen] starting -> {TARGET_URL} | concurrency={CONCURRENCY} "
        f"think_time_ms={THINK_TIME_MS} duration={'forever' if DURATION_S == 0 else f'{DURATION_S}s'}",
        flush=True,
    )
    started = time.time()
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S)) as client:
        tasks = [asyncio.create_task(worker(client)) for _ in range(CONCURRENCY)]
        tasks.append(asyncio.create_task(reporter(started)))
        if DURATION_S > 0:
            await asyncio.sleep(DURATION_S)
            _running = False
        await asyncio.gather(*tasks, return_exceptions=True)

    print(f"[loadgen] stopped. final: {stats}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

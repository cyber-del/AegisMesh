#!/usr/bin/env python3
"""MOCK aegis-controller for the AegisMesh control panel (frontend dev/demo).

Stdlib only, no dependencies. Serves the four /api/* endpoints from API_CONTRACT.md on
:8100 with CLEARLY-LABELLED canned data ([MOCK] prefix on every log line) and a slow,
scripted SSE stream, so the UI can be built and rehearsed standalone before the real
controller exists.

This is NOT the real controller. Swap it out by running the real aegis-controller on :8100.

Run:  py -3 frontend/mock_server.py            # defaults to port 8100
      py -3 frontend/mock_server.py 8100
"""
import json
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8100

# Live backend state (mock). GREEN baseline; goes RED on inject and heals via the scripts.
STATE = {
    "status": "GREEN",
    "latency_ms": 120,
    "active_worker_concurrency": 5,
    "active_fault": None,
    "guardrails_enabled": True,
}
STATE_LOCK = threading.Lock()

_events = []                    # append-only log of SSE events
_cond = threading.Condition()   # notified whenever an event is appended


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(stage, message, level, patch=None):
    """Append one SSE event (message auto-prefixed [MOCK]) and optionally patch STATE."""
    if patch:
        with STATE_LOCK:
            STATE.update(patch)
    ev = {"timestamp": now_iso(), "stage": stage, "message": f"[MOCK] {message}", "level": level}
    with _cond:
        _events.append(ev)
        _cond.notify_all()


# Scripted sequences: (delay_before_s, stage, message, level, state_patch|None)
def seq_latency():
    return [
        (0.3, "DETECT",    "latency SLA breach - p50 4800ms (threshold 1000ms)", "WARNING", {"status": "RED", "active_fault": "latency", "latency_ms": 4800}),
        (0.9, "DIAGNOSE",  "querying SigNoz traces for /v1/generate...", "INFO", None),
        (1.0, "DIAGNOSE",  "root cause: llm.generate spans 3-5s; worker pool saturated 5/5", "INFO", None),
        (0.8, "PLAN",      "proposed remediation: raise MAX_WORKER_CONCURRENCY 5 -> 50", "INFO", None),
        (0.8, "GUARDRAIL", "evaluating proposed action against safety policy...", "INFO", None),
        (0.7, "GUARDRAIL", "approved - concurrency increase within policy bounds", "SUCCESS", None),
        (0.9, "APPLY",     "PATCH worker-queue /admin/config { MAX_WORKER_CONCURRENCY: 50 }", "INFO", None),
        (1.0, "APPLY",     "applied - pool resized 5 -> 50, no restart", "SUCCESS", {"active_worker_concurrency": 50}),
        (1.3, "RESOLVE",   "latency recovering 4800ms -> 180ms", "SUCCESS", {"latency_ms": 180}),
        (0.7, "RESOLVE",   "status GREEN - incident resolved", "SUCCESS", {"status": "GREEN", "active_fault": None}),
        (0.7, "ALERT",     "wrote new SigNoz alert rule: worker_pool_saturation", "INFO", None),
    ]


def seq_ratelimit_guarded():
    # The star of the demo: the guardrail BLOCKS the naive (wrong) fix, agent re-plans.
    return [
        (0.3, "DETECT",    "error-rate spike - 41% HTTP 429 (TokenQuotaExceeded)", "WARNING", {"status": "RED", "active_fault": "ratelimit", "latency_ms": 210}),
        (0.9, "DIAGNOSE",  "querying SigNoz logs + traces...", "INFO", None),
        (1.0, "DIAGNOSE",  "root cause: downstream capacity-limited (rate limit), NOT slow", "INFO", None),
        (0.8, "PLAN",      "candidate remediation: raise MAX_WORKER_CONCURRENCY 5 -> 50", "WARNING", None),
        (0.8, "GUARDRAIL", "evaluating candidate against safety policy...", "INFO", None),
        (1.3, "GUARDRAIL", "REJECTED - raising concurrency floods a rate-limited service; would increase 429s. Action denied.", "BLOCKED", None),
        (1.0, "PLAN",      "re-planning with guardrail feedback: reduce load on downstream", "INFO", None),
        (0.8, "PLAN",      "revised remediation: enable FALLBACK_ROUTING (shed load)", "INFO", None),
        (0.7, "GUARDRAIL", "approved - load-shedding is safe under a rate limit", "SUCCESS", None),
        (0.9, "APPLY",     "PATCH worker-queue /admin/config { FALLBACK_ROUTING: true }", "INFO", None),
        (1.3, "RESOLVE",   "429 rate falling 41% -> 2%; status GREEN", "SUCCESS", {"status": "GREEN", "active_fault": None, "latency_ms": 140}),
        (0.7, "ALERT",     "wrote new SigNoz alert rule: token_quota_exceeded", "INFO", None),
    ]


def seq_ratelimit_unguarded():
    # Guardrails OFF: the naive fix is applied and makes it worse. Shows why the guard matters.
    return [
        (0.3, "DETECT",    "error-rate spike - 41% HTTP 429 (TokenQuotaExceeded)", "WARNING", {"status": "RED", "active_fault": "ratelimit", "latency_ms": 210}),
        (0.9, "DIAGNOSE",  "root cause: downstream capacity-limited (rate limit)", "INFO", None),
        (0.8, "PLAN",      "candidate remediation: raise MAX_WORKER_CONCURRENCY 5 -> 50", "WARNING", None),
        (0.8, "GUARDRAIL", "guardrails DISABLED - applying candidate WITHOUT safety review", "WARNING", None),
        (0.9, "APPLY",     "PATCH worker-queue /admin/config { MAX_WORKER_CONCURRENCY: 50 }", "INFO", {"active_worker_concurrency": 50}),
        (1.3, "RESOLVE",   "429 rate WORSENED 41% -> 63% - flooded the rate-limited downstream", "ERROR", None),
        (1.0, "PLAN",      "reverting; correct action is to reduce load (enable fallback)", "INFO", None),
        (0.9, "APPLY",     "PATCH worker-queue /admin/config { FALLBACK_ROUTING: true }", "INFO", None),
        (1.2, "RESOLVE",   "429 rate falling -> 2%; status GREEN", "SUCCESS", {"status": "GREEN", "active_fault": None, "latency_ms": 140}),
    ]


def run_sequence(fault):
    with STATE_LOCK:
        guarded = STATE["guardrails_enabled"]
    if fault == "latency":
        steps = seq_latency()
    elif fault == "ratelimit":
        steps = seq_ratelimit_guarded() if guarded else seq_ratelimit_unguarded()
    else:
        emit("ERROR", "unknown fault '%s'" % fault, "ERROR")
        return
    for delay, stage, message, level, patch in steps:
        time.sleep(delay)
        emit(stage, message, level, patch)


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, ev):
        self.wfile.write(("data: " + json.dumps(ev) + "\n\n").encode())
        self.wfile.flush()

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            with STATE_LOCK:
                self._json(dict(STATE))
        elif self.path == "/api/logs/stream":
            self._stream()
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            body = {}
        if self.path == "/api/chaos/inject":
            fault = body.get("fault")
            emit("DETECT", "chaos inject requested: %s" % fault, "WARNING",
                 {"status": "RED", "active_fault": fault})
            threading.Thread(target=run_sequence, args=(fault,), daemon=True).start()
            self._json({"ok": True, "fault": fault})
        elif self.path == "/api/guardrails/toggle":
            enabled = bool(body.get("enabled"))
            emit("GUARDRAIL", "guardrails %s" % ("ENABLED" if enabled else "DISABLED"),
                 "INFO", {"guardrails_enabled": enabled})
            self._json({"ok": True, "guardrails_enabled": enabled})
        else:
            self._json({"error": "not found"}, 404)

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()
        with _cond:
            idx = len(_events)  # start live from the current tail
        try:
            self._sse({"timestamp": now_iso(), "stage": "HEARTBEAT",
                       "message": "[MOCK] stream connected", "level": "INFO"})
            while True:
                with _cond:
                    if idx >= len(_events):
                        _cond.wait(timeout=3.0)
                    new = _events[idx:]
                    idx = len(_events)
                if new:
                    for ev in new:
                        self._sse(ev)
                else:
                    self._sse({"timestamp": now_iso(), "stage": "HEARTBEAT",
                               "message": "heartbeat", "level": "INFO"})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass  # keep the console quiet


def main():
    print("=" * 64)
    print("  MOCK aegis-controller  ->  http://localhost:%d" % PORT)
    print("  Serves /api/* with CLEARLY-LABELLED mock data ([MOCK] prefix).")
    print("  This is NOT the real controller - frontend dev/demo only.")
    print("=" * 64, flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()

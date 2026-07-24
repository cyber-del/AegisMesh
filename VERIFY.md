# VERIFY.md — how to confirm each phase of AegisMesh works

This file is the evidence trail for the judges. For every phase, it records the **exact
command to run** and the **exact thing to look for** (usually in the SigNoz UI at
http://localhost:8080). If a step here doesn't reproduce, that phase is not done.

Scope: the observable system only — the three instrumented microservices, the load
generator, the chaos engine, and the SigNoz/Docker setup. The AI controller and control
panel are out of scope for this file.

---

## Phase 0 — Repo hygiene

**What it proves:** the repository is structured, ignores the right files, and never
tracks secrets.

**Verify:**
1. From the repo root (`H:\AegisMesh`), run:
   ```powershell
   git status
   ```
   Expect a clean tree after the Phase 0 commit (no stray untracked files).
2. Confirm the service scaffold exists:
   ```powershell
   Get-ChildItem services
   ```
   Expect four folders: `api-gateway`, `worker-queue`, `ai-inference-service`,
   `load-generator`.
3. Confirm `.env` is ignored and NOT tracked:
   ```powershell
   git check-ignore .env          # prints ".env"  -> it is ignored
   git ls-files .env              # prints nothing -> it is not tracked
   ```
4. Confirm the template IS tracked:
   ```powershell
   git ls-files .env.example      # prints ".env.example"
   ```

**What you should see:** clean git status, four service folders, `.env` ignored and
untracked, `.env.example` present and tracked.

---

## Phase 1 — SigNoz running locally (Foundry + MCP)

**What it proves:** the full SigNoz backend is running and reachable, so telemetry has
somewhere to land, and the MCP server (for the AI controller) is up on the reserved port.

**Prerequisites:** Docker Desktop running with >= 4 GB RAM; ports 8080 / 4317 / 4318 / 8000
free. `foundryctl` installed at `~/.local/bin/foundryctl.exe` via
`curl -fsSL https://signoz.io/foundry.sh | bash` (run in Git Bash; it auto-detects Windows).

**Bring it up (from repo root, in Git Bash so foundryctl is on PATH):**
```bash
export PATH="$HOME/.local/bin:$PATH"
foundryctl forge -f deploy/casting.yaml
docker compose --project-directory pours/deployment -f pours/deployment/compose.yaml up -d
```
(One-shot equivalent: `foundryctl cast -f deploy/casting.yaml`.)

**Verify:**
1. Container health — every `signoz-*` and `ingester` should be `running`/`healthy`.
   `...clickhouse-user-scripts` legitimately shows `Exited (0)` (one-shot init):
   ```bash
   docker compose --project-directory pours/deployment -f pours/deployment/compose.yaml ps -a
   ```
2. Watch the segfault-risk component — must be 0 restarts:
   ```bash
   docker inspect signoz-telemetrykeeper-clickhousekeeper-0 --format 'restarts={{.RestartCount}} state={{.State.Status}}'
   ```
3. UI answers:
   ```bash
   curl http://localhost:8080/api/v1/health    # -> HTTP 200
   ```
4. MCP server listening on the reserved port:
   ```bash
   docker logs signoz-mcp --tail 3    # -> "Listening for MCP clients" addr ":8000" endpoint "/mcp"
   ```

**What you should see:** open http://localhost:8080 in a browser -> SigNoz UI loads and
prompts you to create an admin account (email + password). After login, the app shell
(Services / Traces / Logs / Dashboards) renders with **no data yet** — data starts flowing
in Phase 2.

**Note:** the MCP server runs but has no `SIGNOZ_API_KEY`, so it serves `/mcp` but cannot
query telemetry until the team lead supplies a key (SigNoz UI -> Settings -> API Keys). See
HANDOVER.md section 5.

---

## Phase 2 — ai-inference-service, one trace

**What it proves:** the whole telemetry pipeline works end to end — a real HTTP request to
a real service produces a real trace that lands in SigNoz. Everything after this is
repetition of a proven path.

**Run the service (from repo root, Git Bash):**
```bash
.venv/Scripts/python.exe -m uvicorn main:app \
  --app-dir services/ai-inference-service --host 0.0.0.0 --port 8003
```
(First time: `py -3 -m venv .venv` then
`.venv/Scripts/python.exe -m pip install -r services/ai-inference-service/requirements.txt`.)

**Hit it (generates the trace):**
```bash
curl -X POST http://localhost:8003/v1/infer -H "Content-Type: application/json" \
  -d '{"prompt":"Explain what an SRE does in one sentence.","max_tokens":64}'
```
Expect JSON: `model`, `generated_text`, `input_tokens`, `output_tokens`, `latency_ms`.

**Verify in SigNoz (http://localhost:8080):**
1. Left nav -> **Traces** (or **Services**). A service named **`ai-inference-service`**
   appears.
2. Open a recent trace. It has **two spans**: the FastAPI server span (`POST /v1/infer`)
   and a child span **`llm.generate`**.
3. Click `llm.generate` -> its **Attributes** show `gen_ai.request.model=aegis-sim-1`,
   `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.prompt.length_chars`.

**What you should see:** your exact request as a connected 2-span trace under
`ai-inference-service`, with token counts on the `llm.generate` span. Spans batch-export
every ~5s, so allow a few seconds after the request.

**Note:** service currently runs on the host (not containerized yet) exporting to
`localhost:4317`. Containerization is Phase 8; the OTLP endpoint is env-configurable so the
switch is just an env var.

---

## Phase 3 — Three services, one connected trace

**What it proves:** a single user request flows api-gateway -> worker-queue ->
ai-inference-service and shows up in SigNoz as ONE trace spanning all three services
(context propagation via httpx works), not three disconnected traces.

**Run all three (each in its own shell, from repo root):**
```bash
.venv/Scripts/python.exe -m uvicorn main:app --app-dir services/ai-inference-service --port 8003
.venv/Scripts/python.exe -m uvicorn main:app --app-dir services/worker-queue         --port 8002
.venv/Scripts/python.exe -m uvicorn main:app --app-dir services/api-gateway           --port 8001
```

**Hit the front door (generates the connected trace):**
```bash
curl -X POST http://localhost:8001/v1/generate -H "Content-Type: application/json" \
  -d '{"prompt":"connected trace probe","max_tokens":48}'
```

**Verify in SigNoz (http://localhost:8080):** Traces -> open a recent trace. It contains
spans from **all three** services (`api-gateway`, `worker-queue`, `ai-inference-service`)
in one waterfall: gateway server -> gateway httpx client -> worker server -> worker httpx
client -> inference server -> `llm.generate`.

**Definitive check without the UI (proves connectedness):**
```bash
docker exec signoz-telemetrystore-clickhouse-0-0 clickhouse-client --query "
SELECT traceID, arraySort(groupUniqArray(serviceName)) AS services, count() AS spans
FROM signoz_traces.signoz_index_v3 WHERE timestamp > now() - INTERVAL 5 MINUTE
GROUP BY traceID ORDER BY spans DESC LIMIT 5 FORMAT Vertical"
```
A gateway request shows one `traceID` with services
`['ai-inference-service','api-gateway','worker-queue']`.

**Live pool resize (the Fault-A remediation, verify it works now):**
```bash
curl -X POST http://localhost:8002/admin/config -H "Content-Type: application/json" \
  -d '{"MAX_WORKER_CONCURRENCY":50}'          # -> {"status":"updated",...,"pool":{"max":50,...}}
curl http://localhost:8002/health              # confirm pool.max is now 50
```

**Note:** each trace currently has ~15 spans because the ASGI layer adds `http send` /
`http receive` sub-spans. Harmless; optional cleanup via FastAPIInstrumentor exclude.

---

## Phase 4 — Logs correlated to traces

**What it proves:** application logs from all three services reach SigNoz over their own
OTLP log pipeline AND carry the request's trace_id/span_id, so you can open a trace and
jump straight to that request's log lines.

**Generate correlated logs:**
```bash
curl -X POST http://localhost:8001/v1/generate -H "Content-Type: application/json" \
  -d '{"prompt":"log correlation probe"}'
```

**Verify in SigNoz (http://localhost:8080):**
1. **Traces** -> open the trace -> use **Related Logs / Go to logs** (or the logs tab on the
   span). You should see log lines for THIS request:
   - api-gateway: `generate request received`
   - worker-queue: `process request received`, `pool slot acquired`
   - ai-inference-service: `inference request received`
2. Or in **Logs**, filter by that `trace_id` — all lines from the 3 services appear.

**Definitive check without the UI (log trace_ids match real traces):**
```bash
docker exec signoz-telemetrystore-clickhouse-0-0 clickhouse-client --query "
SELECT trace_id, count() AS log_lines,
       arraySort(groupUniqArray(resources_string['service.name'])) AS services
FROM signoz_logs.logs_v2
WHERE timestamp > now() - INTERVAL 3 MINUTE AND trace_id != ''
  AND trace_id IN (SELECT traceID FROM signoz_traces.signoz_index_v3
                   WHERE timestamp > now() - INTERVAL 5 MINUTE)
GROUP BY trace_id ORDER BY log_lines DESC LIMIT 5 FORMAT Vertical"
```
Each gateway request shows one trace_id with log lines from all three services.

**Event vocabulary (what to look for later):** `pool slot exhausted` (Fault A saturation),
`downstream rate limited (429)` / `retry attempt` (Fault B), `gateway timeout ... -> 504`.

---

## Phase 5 — Token metrics

**What it proves:** ai-inference-service emits a GenAI-semconv token metric that shows up in
SigNoz's metrics explorer, with a deliberately bounded label set (no cardinality explosion).

**Metric:** `gen_ai.client.token.usage` — a **histogram** (the current GenAI semantic
convention; the plan's guessed counter name `gen_ai.usage.*` is actually the *span
attribute* key, not the metric). SigNoz stores it as the derived series
`gen_ai.client.token.usage.{sum,count,bucket,min,max}`.

**Label set (and why it is bounded):**
- `gen_ai.token.type` — exactly two values: `input`, `output`.
- `gen_ai.request.model` — the model name (a small fixed set; here just `aegis-sim-1`).
- `service.name` — carried on the **Resource**, not as a metric label.
- **Nothing per-request** (no prompt text, request id, or user id) is on a label — those
  live on span attributes (`gen_ai.usage.input_tokens` / `output_tokens` on `llm.generate`).
  Result: series count = token_type(2) x model(small), constant regardless of traffic. We
  confirmed exactly 2 series for `.sum` after 12 varied requests.

**Generate metrics:**
```bash
for i in $(seq 1 12); do curl -s -X POST http://localhost:8001/v1/generate \
  -H "Content-Type: application/json" -d "{\"prompt\":\"tokens $i\",\"max_tokens\":$((20*i))}" -o /dev/null; done
```

**Verify in SigNoz (http://localhost:8080):** Metrics explorer -> search
`gen_ai.client.token.usage`. Plot the **sum**, group by `gen_ai.token.type` to see input vs
output token volume over time.

**Definitive check without the UI (bounded labels):**
```bash
docker exec signoz-telemetrystore-clickhouse-0-0 clickhouse-client --query "
SELECT DISTINCT JSONExtractString(labels,'gen_ai.token.type') AS token_type,
       JSONExtractString(labels,'gen_ai.request.model') AS model
FROM signoz_metrics.time_series_v4
WHERE metric_name='gen_ai.client.token.usage.sum' FORMAT Vertical"
```
Expect only two rows: input and output, both `aegis-sim-1`.

---

## Phase 6 — Load generator

**What it proves:** the system takes steady concurrent load (so dashboards are never empty
and Phase 7's cascade has traffic to cascade under).

**Run it (from repo root):**
```bash
CONCURRENCY=15 .venv/Scripts/python.exe services/load-generator/loadgen.py
# bounded smoke test: prepend LOADGEN_DURATION_S=8
```

**What you should see:** a stats line every 5s, e.g.
`[loadgen] ... rps~24 sent=165 ok=165 504=0 429=0 ...`. With no faults, everything is 200
OK even though the pool of 5 is saturating (requests queue but clear well under 5s).

**Verify in SigNoz (http://localhost:8080):** Services/Traces show a continuous stream of
`api-gateway` traffic; the token metric and request-rate charts are populated.

**Knobs:** `CONCURRENCY` (default 15), `THINK_TIME_MS`, `LOADGEN_MAX_TOKENS`,
`LOADGEN_DURATION_S` (0 = forever), `LOADGEN_TIMEOUT_S` (20, > gateway 5s), `TARGET_URL`.

---

## Phase 7 — Chaos engine (two faults, opposite fixes)

**What it proves:** with steady load, each fault causes gateway 504s **on its own** (real
resource exhaustion, nothing hardcoded), and the two faults require OPPOSITE remediations.

**Precondition:** load generator running (`CONCURRENCY=15`), all services healthy, clean
baseline (all 200s).

### Fault A — latency
```bash
curl -X POST http://localhost:8003/chaos/inject-latency          # 3-5s per inference
# ~15-20s later: gateway 504s climb; throughput collapses. Cause: pool of 5 held 3-5s.
curl -X POST http://localhost:8002/admin/config -d '{"MAX_WORKER_CONCURRENCY":50}'  # CORRECT FIX
# 504s stop; all requests succeed again (slower, because inference is still slow).
curl -X POST http://localhost:8003/chaos/reset
curl -X POST http://localhost:8002/admin/config -d '{"MAX_WORKER_CONCURRENCY":5}'   # back to baseline
```

### Fault B — token rate limit
```bash
curl -X POST http://localhost:8003/chaos/inject-token-ratelimit -d '{"capacity":1}'
# ~15-25s later: ai-inference emits 429/TokenQuotaExceeded; worker retries hold slots ->
# pool saturates -> gateway 504s (plus 429s). Same edge symptom, different cause.
curl -X POST http://localhost:8002/admin/config -d '{"FALLBACK_ROUTING":true}'       # CORRECT FIX
#   (or a low sampling rate: -d '{"LLM_SAMPLING_RATE":0.1}') -> load shed -> 504s stop.
# WRONG FIX to demonstrate: {"MAX_WORKER_CONCURRENCY":50} floods capacity=1 -> 429 storm.
curl -X POST http://localhost:8003/chaos/reset
curl -X POST http://localhost:8002/admin/config -d '{"MAX_WORKER_CONCURRENCY":5,"LLM_SAMPLING_RATE":1.0,"FALLBACK_ROUTING":false}'
```

**Which SigNoz signal distinguishes them (this is what the AI controller keys on):**
| | Fault A (latency) | Fault B (rate limit) |
|---|---|---|
| api-gateway | 504s | 504s **and** 429s |
| ai-inference `llm.generate` span | duration **3-5s** | duration normal (~150ms) |
| ai-inference status | 200 | **HTTP 429** |
| ai-inference logs | (normal) | **`TokenQuotaExceeded`** |
| worker-queue logs | `pool slot exhausted` | `pool slot exhausted` + `downstream rate limited (429)` + `retry attempt` |
| Correct remediation | raise `MAX_WORKER_CONCURRENCY` | lower `LLM_SAMPLING_RATE` / `FALLBACK_ROUTING` |

**Verify in SigNoz:** watch the `api-gateway` service error rate climb after each inject;
open a failing trace — for A the `llm.generate` span is 3-5s; for B ai-inference shows 429
spans and `TokenQuotaExceeded` logs. After the correct fix, the error rate falls back.

---

## Phase 8 — Package and run clean (Docker Compose)

**What it proves:** the whole system (3 services + load generator) comes up from a single
command, wired to the running SigNoz collector, and emits the same telemetry as the host
version.

**Precondition:** SigNoz already running (Phase 1) — this creates the external
`signoz-network` and the `signoz-ingester` collector alias.

**Bring up the AegisMesh services (from repo root):**
```bash
docker compose up -d --build
docker compose ps            # all four aegis-* containers Up
```
Services publish 8001/8002/8003 on the host exactly like the host version; internally they
talk over `signoz-network` (`ai-inference`, `worker-queue`, `api-gateway` by name) and export
OTLP to `signoz-ingester:4317`.

**Verify:**
```bash
curl http://localhost:8001/health   # api-gateway ok
curl -X POST http://localhost:8001/v1/generate -H "Content-Type: application/json" \
  -d '{"prompt":"compose smoke test"}'
```
Then in SigNoz: the same connected 3-service traces, correlated logs, token metric, and the
Phase 7 chaos endpoints all work identically (the load generator container drives steady
traffic automatically).

**Tear down:**
```bash
docker compose down          # stop AegisMesh services (leaves SigNoz running)
```

**Clean-room bring-up (as a judge would):** clone the repo to a fresh folder and bring the
whole thing up from scratch — SigNoz first, then the services:
```bash
git clone <repo> aegis-clean && cd aegis-clean
export PATH="$HOME/.local/bin:$PATH"
foundryctl forge -f deploy/casting.yaml
docker compose --project-directory pours/deployment -f pours/deployment/compose.yaml up -d
docker compose up -d --build     # the AegisMesh services
```

---

<!-- Append one section per phase below, following the same shape. -->

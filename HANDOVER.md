# HANDOVER — AegisMesh observable system (Teammate B)

Plain-English handover for teammates who did not build this and are not deep in
OpenTelemetry. Read at 1am and still make sense of it.

Scope of THIS work: the three instrumented microservices, the load generator, the chaos
engine, and the SigNoz/Docker setup. NOT the AI controller (team lead) or the control panel
(teammate A).

TL;DR: SigNoz is up; three services emit connected traces + correlated logs + token metrics;
a load generator keeps it busy; two chaos faults each cause the *same* edge failure (gateway
504s) but need *opposite* fixes. Everything runs with `docker compose up -d`.

---

## 1. What works right now

Run it: SigNoz is already up (Phase 1). Then `docker compose up -d --build` from the repo
root brings up all four AegisMesh containers.

- **SigNoz observability backend** — http://localhost:8080 (create an admin account on first
  open). All telemetry lands here.
- **SigNoz MCP server** on port 8000 for the AI controller. `docker logs signoz-mcp --tail 3`
  shows it listening on `/mcp`. Needs an API key to return data (section 5).
- **Three instrumented services**, containerized, on the SigNoz network:
  - api-gateway `:8001`, worker-queue `:8002`, ai-inference-service `:8003`.
  - One `POST /v1/generate` produces ONE trace spanning all three services, plus log lines
    from each carrying the same trace_id, plus a token metric.
  - *See it:* `curl -X POST localhost:8001/v1/generate -d '{"prompt":"hi"}' -H "Content-Type: application/json"`,
    then open Traces in SigNoz.
- **Correlated logs** — open a trace -> Related Logs (or filter Logs by trace_id).
- **Token metric** — `gen_ai.client.token.usage` (histogram) in the Metrics explorer, grouped
  by `gen_ai.token.type` (input/output). Bounded labels only.
- **Load generator** container drives ~15 concurrent requests continuously, so dashboards are
  never empty.
- **Chaos engine** — two faults, both cause gateway 504s under load on their own (real
  saturation, nothing hardcoded), each needing the OPPOSITE fix. See sections 5 and VERIFY.md
  Phase 7 for the exact commands.

## 2. What is not done / rough edges

- **MCP has no API key**, so the AI controller can't query telemetry through it yet. The team
  lead generates one in SigNoz (Settings -> API Keys) and injects it into the `signoz-mcp`
  container. ~10 min. Needed for the AI-controller demo.
- **Trace noise:** each trace carries ~15 spans because the ASGI layer adds `http send` /
  `http receive` sub-spans. Cosmetic; optional one-line cleanup (FastAPIInstrumentor exclude).
- **Chaos is load-tuned:** cascades are tuned for ~15 concurrent, pool 5, Fault B capacity 1.
  Change those a lot and re-check 504s still emerge (VERIFY.md Phase 7).
- **No CORS on the services** — if teammate A's control panel calls these endpoints directly
  from the browser (origin :5173), it will hit CORS errors. Not yet enabled; ~5 min to add
  FastAPI CORSMiddleware if they don't proxy through a backend. See section 6.
- **Working docs may be local-only:** `VERIFY.md`, `HANDOVER.md`, `PROGRESS.md` are gitignored
  (a deliberate choice), so a fresh clone does NOT include them, and local tooling has been
  observed deleting them — see section 7.

## 3. How we approached it, and why

Build order was deliberate, one proven layer before the next:

1. **SigNoz first, then ONE traced service, and we did not build anything else until that
   single trace was visible in SigNoz.** The entire value of the project is telemetry landing
   in SigNoz; if the pipeline is broken, nothing downstream matters. Proving one trace end to
   end (Phase 2) means everything after is repetition of a known-good path, not new risk.
2. **Then three connected services (Phase 3).** The make-or-break detail is that a single user
   request produces ONE trace across all three, not three disconnected ones. That only works
   if the outbound HTTP client is instrumented (context propagation via the `traceparent`
   header), not just the web framework — a classic place teams lose a day.
3. **Then the other signals** — logs correlated to traces (Phase 4), token metrics (Phase 5) —
   each verified in SigNoz before moving on.
4. **Load generator (Phase 6) before chaos (Phase 7)**, because the failures only cascade
   under concurrent load; you cannot demonstrate them on a single request.
5. **Two deliberately different faults (Phase 7).** They look identical at the edge (gateway
   504s) but have different root causes and require OPPOSITE fixes. This is the whole point:
   the AI agent has to genuinely diagnose from telemetry, not pattern-match one known answer.
   If both faults had the same fix, the agent could "succeed" without understanding anything.
6. **Package last (Phase 8)** and prove it builds from a clean clone.

Everything is verified by reading real data out of SigNoz's ClickHouse, not by trusting that
"it should work" — because the plan's hard rule was: never fabricate telemetry.

## 4. Decisions the team must know about

- **Port 8000 is SigNoz MCP's — nothing else binds it.** The services use 8001/8002/8003, UI
  8080, OTLP 4317/4318, MCP 8000, and (not ours) 8100 controller / 5173 control panel.
- **The two-fault chaos design, and why "raise concurrency" is the WRONG fix for Fault B:**
  - Fault A (latency): downstream is slow but has headroom -> add parallelism (raise
    `MAX_WORKER_CONCURRENCY`). Correct.
  - Fault B (rate limit): downstream is capacity-limited and load-SENSITIVE -> raising
    concurrency floods it with more concurrent calls and produces MORE 429s. The correct fix
    is the opposite: reduce load (lower `LLM_SAMPLING_RATE` or enable `FALLBACK_ROUTING`).
  - One-line rule for the agent: *slow spans -> add parallelism; 429/quota errors -> shed load.*
- **Token metric follows the real GenAI semantic convention** — a histogram
  `gen_ai.client.token.usage` with a `gen_ai.token.type` attribute — NOT the plan's guessed
  counter names `gen_ai.usage.input_tokens/output_tokens` (those are the *span attribute* keys,
  still set on the `llm.generate` span).
- **SigNoz install uses Foundry (`foundryctl`), not the deprecated install.sh.** casting.yaml
  requires `kind: Installation`. MCP is a first-class Foundry component
  (`spec.mcp.spec.enabled: true`), not a separate manual install.
- **SigNoz runs on Docker Desktop, not WSL-native Docker.** SigNoz's docs warn of a ClickHouse
  Keeper segfault under Docker Desktop on Windows; we tried it anyway (faster) and it ran clean
  (0 restarts). Fallback if it ever crash-loops: native Docker Engine inside a WSL2 distro.
- **Fault B tuning:** retry backoff was raised to 3x500ms and rate-limit capacity set to 1 so
  the pool genuinely saturates into 504s at ~15 concurrent. At higher capacity only 429s
  appear, not 504s (the closed-loop load self-limits). Nothing is hardcoded to fail.
- **Repo layout was flattened** on 2026-07-24 from a broken nested-repo-in-a-repo into a single
  repo at `H:\AegisMesh` (remote `github.com/cyber-del/AegisMesh`). History intact.

## 5. For the team lead (AI controller) — endpoint contracts + fault signals

All on the host (containers publish these ports):

- **ai-inference-service** — `http://localhost:8003`
  - `POST /v1/infer` — req `{"prompt":"<text>","max_tokens":<int?>}` -> res
    `{"model","generated_text","input_tokens","output_tokens","latency_ms"}`.
  - `GET /health` -> includes `chaos` state and `inflight`.
  - Chaos: `POST /chaos/inject-latency` (opt `{"min_s":3,"max_s":5}`),
    `POST /chaos/inject-token-ratelimit` (opt `{"capacity":1}`), `POST /chaos/reset`.
  - Telemetry: 1 trace/request, service `ai-inference-service`, spans `POST /v1/infer` +
    `llm.generate` (token counts on `gen_ai.usage.input_tokens/output_tokens`).
- **api-gateway** — `http://localhost:8001`
  - `POST /v1/generate` — same body; returns downstream JSON, or **504** past the 5s budget,
    502 if unreachable. `GET /health`.
- **worker-queue** — `http://localhost:8002`
  - `POST /v1/process` — internal; api-gateway calls this.
  - `POST /admin/config` — `{"MAX_WORKER_CONCURRENCY":<int>, "LLM_SAMPLING_RATE":<0..1>,
    "FALLBACK_ROUTING":<bool>}`, applied live. **The remediation endpoint.** Returns
    `{"status":"updated","changed":{...},"pool":{"max","active"},"config":{...}}`.
  - `GET /health` — live `pool` + `config`.

**Which SigNoz signal distinguishes the faults (both look like gateway 504s):**

| | Fault A (latency) | Fault B (rate limit) |
|---|---|---|
| api-gateway | 504s | 504s **and** 429s |
| ai-inference `llm.generate` span | **3-5s** | fast (~150ms) |
| ai-inference response | 200 | **HTTP 429** |
| ai-inference logs | normal | **`TokenQuotaExceeded`** |
| worker-queue logs | `pool slot exhausted` | + `downstream rate limited (429)` + `retry attempt` |
| **Correct fix (POST /admin/config)** | `{"MAX_WORKER_CONCURRENCY":50}` | `{"FALLBACK_ROUTING":true}` or low `LLM_SAMPLING_RATE` |

To write a new SigNoz alert rule after remediation, the API base is the same SigNoz instance
(http://localhost:8080); the MCP server can also create/query alerts once it has an API key.

## 6. For teammate A (control panel)

The panel likely needs manual buttons + a status view. Endpoints (all `http://localhost:<port>`):

- **Trigger Fault A:** `POST :8003/chaos/inject-latency` -> `{"status":"latency_injected","chaos":{...}}`
- **Trigger Fault B:** `POST :8003/chaos/inject-token-ratelimit` body `{"capacity":1}` ->
  `{"status":"ratelimit_injected","chaos":{...}}`
- **Reset chaos:** `POST :8003/chaos/reset` -> `{"status":"reset","chaos":{...}}`
- **Fix — add parallelism:** `POST :8002/admin/config` body `{"MAX_WORKER_CONCURRENCY":50}`
- **Fix — shed load:** `POST :8002/admin/config` body `{"FALLBACK_ROUTING":true}` (or
  `{"LLM_SAMPLING_RATE":0.1}`)
- **Send a test request:** `POST :8001/v1/generate` body `{"prompt":"...","max_tokens":64}`
- **Status polling:**
  - `GET :8003/health` -> `chaos` (which fault is on), `inflight`.
  - `GET :8002/health` -> `pool` (`max`,`active`) and `config` (`LLM_SAMPLING_RATE`,
    `FALLBACK_ROUTING`).

Suggested UI state: show which fault is active (from :8003 health), the worker pool
`active/max` and sampling/fallback (from :8002 health), and a live error-rate read from
SigNoz. **Flag:** these endpoints have no CORS headers yet — if the panel calls them straight
from the browser it will be blocked; either proxy through a backend or ask us to enable CORS
(quick). Nothing here was hardcoded in the panel by us; all values are live from the services.

## 7. Things someone should review or double-check

- **`.env` was previously committed** (empty); now untracked + gitignored so no secret can
  enter history. Local `.env` untouched. `contracts.json` at repo root is an empty placeholder.
- **`CLAUDE.md`** is now a plain gitignored file (was a stray directory at the start).
- **Working docs (`VERIFY.md`, `HANDOVER.md`, `PROGRESS.md`) are gitignored** — they do NOT
  appear in a fresh clone, AND local tooling was observed deleting them from disk once. If you
  want them to survive reliably (and be visible to judges/team), the robust fix is to un-ignore
  and commit them (they can't be auto-cleaned once tracked). Otherwise keep a backup copy.
- **Runs on this machine via Docker Desktop on Windows.** The ClickHouse Keeper segfault risk
  didn't materialize but could on another machine / after a Docker update.
- **Fault B needs capacity=1 to reach 504s** at 15 concurrent — verify on the demo machine
  that the cascade still appears (timing-dependent).

## 8. Known risks before submission

- **ClickHouse Keeper could segfault** under Docker Desktop on another machine -> SigNoz down.
  Mitigation: test on the demo machine ahead of time; fallback is WSL-native Docker Engine.
- **First `docker compose up` pulls/builds images** (a few minutes) and SigNoz itself pulls
  several GB. Do a full dry-run on the demo machine/network before the demo; don't do it live.
- **Chaos cascade timing is load-dependent.** If the demo machine is much faster/slower, the
  504s may take longer to appear or need a capacity/concurrency tweak. Rehearse the exact
  inject->observe->fix sequence in VERIFY.md Phase 7.
- **MCP without an API key returns nothing** — if the AI-controller demo depends on MCP,
  generate and wire the key beforehand, or the agent will look broken.
- **Port conflicts:** 8001/8002/8003/8080/8000/4317/4318 must be free on the demo machine.
- **We never push; V. Abhishek Prakash pushes manually.** Confirm the branch is pushed before
  submission — none of this is on the remote until then.

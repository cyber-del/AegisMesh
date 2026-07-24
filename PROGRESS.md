# PROGRESS — AegisMesh (Teammate B: observable system + telemetry)

Status of each phase. One line each: `DONE / PARTIAL / NOT STARTED` + the exact next
action. Read this first at the start of every session, alongside `CLAUDE.md`
(`CLAUDE.md/Context.md`), `HANDOVER.md`, and `git log --oneline -15`.

| Phase | Status | Next action |
|-------|--------|-------------|
| 0 — Repo hygiene | **DONE** | — |
| 1 — SigNoz running locally (Foundry + MCP) | NOT STARTED | Install foundryctl; write `deploy/casting.yaml` (Docker Compose mode, MCP enabled); bring up; CHECKPOINT 1 at http://localhost:8080 |
| 2 — ai-inference-service, one trace | NOT STARTED | Build FastAPI service on :8003 with OTLP gRPC export; find the trace in SigNoz (CHECKPOINT 2) |
| 3 — Three connected services, one trace | NOT STARTED | Add api-gateway (:8001) + worker-queue (:8002); instrument outbound HTTP client so all 3 share one trace (CHECKPOINT 3) |
| 4 — Logs correlated to traces | NOT STARTED | Export logs to SigNoz with trace_id/span_id; click-through from trace (CHECKPOINT 4) |
| 5 — Token metrics | NOT STARTED | Emit gen_ai.usage.* counters, bounded labels only (CHECKPOINT 5) |
| 6 — Load generator | NOT STARTED | Continuous 10–20 concurrent requests through api-gateway, env-configurable |
| 7 — Chaos engine (two faults, opposite fixes) | NOT STARTED | Fault A latency -> pool saturation -> 504; Fault B 429/ratelimit; /chaos/reset (CHECKPOINT 7) |
| 8 — Package + clean-room bring-up | NOT STARTED | docker-compose.yml for all services + load gen; fill .env.example; fresh-clone test |
| 9 — Handover report | LIVING | Keep HANDOVER.md sections 1/2/7 current after every phase; full report at the end |

## Notes carried forward
- Repo was flattened from a nested layout on 2026-07-24; real repo is now at
  `H:\AegisMesh` with remote `github.com/cyber-del/AegisMesh` (branch `main`).
- `CLAUDE.md` is a **directory** containing `Context.md` (the project context). It is
  gitignored (local only). Left as-is; content read and honored.
- Root-level `casting.yaml` and `contracts.json` are committed but **empty** placeholders.
  `casting.yaml` will be superseded by `deploy/casting.yaml` in Phase 1. `contracts.json`
  is left for now (API-contract doc; can be filled once endpoints are built).

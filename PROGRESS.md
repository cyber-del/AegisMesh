# PROGRESS — AegisMesh (Teammate B: observable system + telemetry)

Status of each phase. Read this first at the start of every session, alongside `CLAUDE.md`,
`HANDOVER.md`, and `git log --oneline -15`.

**ALL PHASES 0–9 COMPLETE.** Final commit: `e4d1276` (Phase 8). Phase 9 handover docs are
local-only (gitignored). Nothing pushed — V. Abhishek Prakash pushes manually.

| Phase | Status | Commit |
|-------|--------|--------|
| 0 — Repo hygiene | **DONE** | 2c37980 |
| 1 — SigNoz running locally (Foundry + MCP) | **DONE** | 9591b7c |
| 2 — ai-inference-service, one trace | **DONE** | 4c98dda |
| 3 — Three connected services, one trace | **DONE** | d7e5967 |
| 4 — Logs correlated to traces | **DONE** | c861827 |
| 5 — Token metrics | **DONE** | 1db2bc7 |
| 6 — Load generator | **DONE** | b9338e1 |
| 7 — Chaos engine (two faults, opposite fixes) | **DONE** | 35f009c |
| 8 — Package + clean-room bring-up | **DONE** | e4d1276 |
| 9 — Handover report | **DONE** (full 8-section HANDOVER.md, local) | — |

## Pre-submission checklist (from HANDOVER §8)
- [ ] `git push` — none of the 9 commits are on the remote until done manually.
- [ ] Wire an MCP API key (SigNoz Settings -> API Keys) into the `signoz-mcp` container.
- [ ] Rehearse the chaos sequence on the demo machine (timing is load-dependent).
- [ ] Decide whether VERIFY.md/HANDOVER.md should be committed for judges (currently local).

## How to run
- **SigNoz:** `export PATH="$HOME/.local/bin:$PATH"; foundryctl forge -f deploy/casting.yaml`
  then `docker compose --project-directory pours/deployment -f pours/deployment/compose.yaml up -d`.
- **AegisMesh services:** `docker compose up -d --build` (needs SigNoz up first — joins its
  external `signoz-network`). Stop with `docker compose down`.
- **Host/dev alternative:** run each service via `.venv/Scripts/python.exe -m uvicorn main:app
  --app-dir services/<svc> --port <port>` (see VERIFY.md).

## Key facts carried forward
- **SigNoz on Docker Desktop** (not WSL-native). ClickHouse Keeper segfault risk did NOT occur
  (0 restarts). Fallback: native Docker Engine in a WSL2 Ubuntu distro.
- `foundryctl.exe v0.2.16` at `~/.local/bin/` (Git Bash; not on PATH by default).
- **Python 3.10.11** via `py -3` (`python`/`python3` not on the Git Bash PATH). Containers use
  `python:3.11-slim`. Shared dev venv at repo-root `.venv` (gitignored).
- **OTel versions (verified 2026-07-24):** core api/sdk/exporter `1.44.0`, contrib
  instrumentation `0.65b0`. Logs API uses the underscore `_logs`/`_log_exporter` modules.
- **Token metric** = `gen_ai.client.token.usage` histogram (semconv), bounded labels
  `gen_ai.token.type` + `gen_ai.request.model`.
- **Chaos tuning:** Fault B needs rate-limit capacity=1 + retry backoff 3x500ms to cascade to
  504s at ~15 concurrent.
- Repo flattened from a nested layout on 2026-07-24; real repo at `H:\AegisMesh`, remote
  `github.com/cyber-del/AegisMesh`, branch `main`.
- **HANDOVER.md/PROGRESS.md/VERIFY.md are gitignored (local-only)** and were observed being
  auto-deleted by local tooling once (recreated 2026-07-24). If they must persist reliably,
  un-ignore + commit them (tracked files aren't auto-cleaned).

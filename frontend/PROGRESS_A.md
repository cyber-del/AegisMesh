# PROGRESS_A — AegisMesh control panel (Teammate A: frontend)

One line per phase. Read this first at the start of every session, with `CLAUDE.md`,
`HANDOVER_A.md`, and `git log --oneline -15`. Committed/tracked (never gitignored).

**RESUME HERE:** Phase 1 — build `frontend/index.html`.

| Phase | Status | Next action |
|-------|--------|-------------|
| 0 — Lock API contract + mock it | **DONE** | contract drafted (lead must confirm fault strings + CORS); mock on :8100 |
| 1 — Panel driven by real/mock data | NOT STARTED | build index.html: banner polls /api/status, SSE terminal, DISCONNECTED default |
| 2 — Two faults + guardrail moment | NOT STARTED | two inject buttons; BLOCKED styling; guardrails toggle state |
| 3 — Real backend swap + polish | NOT STARTED | base URL const -> :8100; 1080p polish; verify DISCONNECTED + JS syntax |
| 4 — Handover report | NOT STARTED | write HANDOVER_A.md |

## Notes carried forward
- Scope: `frontend/` ONLY. Single-file vanilla `index.html` (no React/Vite/build). Backend at
  `http://localhost:8100` (NOT 8000 — that's SigNoz MCP). UI served on :5173 or opened as file://.
- **Contract drafted — lead must confirm:** exact `fault` string values (`"latency"` /
  `"ratelimit"`) and add `Access-Control-Allow-Origin` (CORS) on the controller. See
  `API_CONTRACT.md`.
- Mock: `py -3 frontend/mock_server.py` (stdlib only, port 8100). All log lines prefixed
  `[MOCK]`. Emits a BLOCKED event on the ratelimit fault with guardrails ON.
- Tooling: Python 3.10.11 via `py -3`. **node is NOT installed** — `node --check` isn't
  possible; JS is reviewed manually + must be eyeballed in a browser (noted for handover).
- Git identity: V. Abhishek Prakash <abhishekprakashv02@gmail.com>. No AI attribution. Never
  push. Stage only `frontend/` files (leave teammate B's untracked changes alone).

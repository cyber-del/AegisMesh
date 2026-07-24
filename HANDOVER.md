# HANDOVER — AegisMesh observable system (Teammate B)

Living document. Written in plain English for teammates who did not build this and are not
deep in OpenTelemetry. Updated after every phase (sections 1, 2, 7 at minimum). The full
8-section report is completed at the end.

Scope: the three instrumented microservices, the load generator, the chaos engine, and the
SigNoz/Docker setup. NOT the AI controller (team lead) or the control panel (teammate A).

---

## 1. What works right now

- **The repository is clean and correctly structured.** The project lives at
  `H:\AegisMesh` (git remote `github.com/cyber-del/AegisMesh`, branch `main`). There is a
  `services/` folder with one subfolder per service, secrets are gitignored, and there is a
  `VERIFY.md` describing how to check each phase.
  *See for yourself:* run `git status` (clean) and `Get-ChildItem services` (four folders).
- **SigNoz is running locally (the whole observability backend).** One command deploys it
  via SigNoz Foundry; all containers are healthy. This is where all telemetry will land.
  *See for yourself:* open **http://localhost:8080** — the SigNoz UI loads (first time, it
  asks you to create an admin account). No data in it yet; that starts in Phase 2.
- **The SigNoz MCP server is up on port 8000** (the thing the AI controller talks to).
  *See for yourself:* `docker logs signoz-mcp --tail 3` shows "Listening for MCP clients"
  on `:8000`, endpoint `/mcp`. It still needs an API key to return data — see section 5.

## 2. What is not done

- **The three microservices, load generator, and chaos engine (Phases 2–8)** are not built
  yet — so right now SigNoz has no data flowing into it. See `PROGRESS.md` for exact
  per-phase status and the next action.
  *Rough effort remaining:* the full service build + instrumentation + chaos + packaging.
  Needed for the demo: all of it.
- **MCP has no API key yet**, so the AI controller can't query SigNoz through it until the
  team lead generates one (SigNoz UI -> Settings -> API Keys) and supplies it to the MCP
  container. ~10 min of work. Needed for the AI-controller demo.

## 7. Things someone should review or double-check

- **Repo was flattened on 2026-07-24.** It started as a git repo nested one level too deep
  (`H:\AegisMesh\AegisMesh`) wrapped by a second throwaway repo. I moved the real repo up
  to `H:\AegisMesh` and deleted the throwaway. History and the `cyber-del` remote are
  intact. If anything looks off, the repo is safe to re-clone from origin.
- **`CLAUDE.md` is a directory** (`CLAUDE.md/Context.md`), not a file. It is gitignored, so
  it is local-only and harmless — but Claude Code auto-loads a `CLAUDE.md` *file*, so the
  IDE will not auto-load this context. Consider converting it to a plain `CLAUDE.md` file if
  that matters to you.
- **`.env` was previously committed** (empty). It is now untracked and gitignored so no
  secret can ever enter history. The local `.env` file is untouched.
- **`contracts.json` at the repo root is an empty placeholder** committed earlier. The old
  empty root `casting.yaml` was removed in Phase 1 (the real one is `deploy/casting.yaml`).
- **SigNoz runs on Docker Desktop, not WSL-native Docker.** SigNoz's docs recommend
  WSL-native Docker Engine on Windows to avoid a ClickHouse Keeper segfault. We tried Docker
  Desktop (faster) and it worked cleanly — 0 restarts, healthy. Worth re-checking on any
  fresh machine or after a Docker Desktop update; the documented fallback is Docker Engine
  inside a WSL2 Ubuntu distro.
- **`foundryctl` details vs the original blueprint:** the blog example omitted `kind`, but
  this version (v0.2.16) requires `kind: Installation`. MCP is a first-class Foundry
  component (`spec.mcp.spec.enabled: true`), NOT a fully separate install as one doc page
  implied. The generated `pours/` is gitignored; the resolved `casting.yaml.lock` is
  committed so the exact stack is reproducible.

---

<!-- Sections 3, 4, 5, 6, 8 are completed in the Phase 9 full handover. -->

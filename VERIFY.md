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

<!-- Append one section per phase below, following the same shape. -->

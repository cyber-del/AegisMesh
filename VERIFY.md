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

<!-- Append one section per phase below, following the same shape. -->

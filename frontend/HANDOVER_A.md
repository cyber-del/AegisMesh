# HANDOVER_A — AegisMesh control panel (Teammate A: frontend)

Plain English, for a tired teammate at 1am. This is the UI judges watch in the demo video:
the system going GREEN → RED → GREEN, with an AI agent diagnosing and a guardrail blocking a
dangerous action.

Scope: `frontend/` only. One file you double-click: `frontend/index.html`. No build step, no
React, no npm. A tiny Python mock backend lets it run before the real controller exists.

---

## How to run it (30 seconds)

```powershell
# 1. start the mock backend (stdlib Python, no installs)
py -3 frontend/mock_server.py            # serves http://localhost:8100

# 2. open the panel — either way works:
#    a) double-click frontend/index.html   (opens as file://)
#    b) or serve it:  cd frontend ; py -3 -m http.server 5173   then open http://localhost:5173
```
The mock's log lines are all prefixed `[MOCK]` so they can never be mistaken for real data.

## 1. What works right now

- **The panel renders and is driven entirely by backend data.** Four regions: title, status
  banner, controls, live terminal. *See it:* open `index.html` with the mock running.
- **Status banner** polls `GET /api/status` every second and shows GREEN / RED / DISCONNECTED,
  plus latency, worker concurrency, guardrails state. When RED it names the active fault.
  *See it:* start the mock → banner goes GREEN 120ms; stop the mock → it falls back to
  DISCONNECTED within ~1s.
- **Never shows a fake-healthy state.** Before any data, and on any fetch failure, it shows a
  neutral "● DISCONNECTED — waiting for controller". No hardcoded 120ms/green. *See it:* open
  the file with NO mock running → DISCONNECTED.
- **Two fault buttons** — "Inject Latency Fault" and "Inject Rate-Limit Fault" — POST
  `{ "fault": "latency" }` / `{ "fault": "ratelimit" }` to `/api/chaos/inject`. *See it:* click
  either → banner goes RED with that fault named, terminal streams the agent's work.
- **Live terminal** connects to `GET /api/logs/stream` (SSE), colours each line by level
  (INFO/SUCCESS/WARNING/ERROR/BLOCKED), auto-scrolls, ignores HEARTBEAT keep-alives.
- **The guardrail BLOCK moment** — when a `level:"BLOCKED"` event arrives, the line gets a
  bold red/amber style **and** a big pinned "🛑 GUARDRAIL BLOCKED" alert pops at the top so it
  can't scroll away on camera. *See it:* with guardrails ON, click "Inject Rate-Limit Fault".
- **Guardrails toggle** shows its own state: green "ON — protected" / amber "OFF —
  unprotected", so the contrast reads on camera. Clicking it POSTs `/api/guardrails/toggle`.
- **One config constant** `API_BASE = "http://localhost:8100"` at the top of the script — the
  only line to change to point at a different backend.

Everything above is verified by program (see §4). The actual on-screen look is not — see §4.

## 2. What is NOT done / fragile

- **The real backend flow is UNVERIFIED.** I built against the mock because the lead's
  controller may not exist yet. When it is up on :8100, we must run the panel against it and
  confirm the shapes match `API_CONTRACT.md`. *Effort:* ~15 min once the controller exists.
  *Demo-critical:* yes for the real demo; the mock demo already works today.
- **JS was not run in a real engine.** `node` is not installed on this machine, so I could not
  do `node --check` or a headless load. I verified bracket/quote balance with a
  comment/string-aware parser (PASS), but a human must open it in a browser once to be 100%.
  *Effort:* 2 min. *Demo-critical:* yes (do it before recording).
- **No automated visual test.** Colours, layout, the emoji (🛑), the banner transition, the
  block-alert pop — a human has to eyeball these (I can't see a browser). *Effort:* 5 min.
- **Fault string values are assumed** (`"latency"` / `"ratelimit"`). If the lead's controller
  expects different strings, change the two lines `inject("latency")` / `inject("ratelimit")`.

## 3. What the lead (controller) must provide — see API_CONTRACT.md

1. **Confirm the four endpoints** match `frontend/API_CONTRACT.md` exactly (status, chaos/inject,
   guardrails/toggle, logs/stream SSE), including the JSON field names.
2. **CORS.** The controller MUST send `Access-Control-Allow-Origin: *` (or echo the UI origin)
   on every `/api/*` response — including the SSE stream and an `OPTIONS` preflight for the two
   POSTs. Without it the browser blocks everything and the panel stays DISCONNECTED. (The mock
   already does this, so the mock demo works; the real controller must match.)
3. **Confirm the exact `fault` string values** the controller expects for the two chaos endpoints.
4. **Confirm the status enum is exactly `GREEN` / `RED`** (any other value → UI shows DISCONNECTED).
5. If the real backend differs from the contract, tell me the difference — I adjust the UI, I
   do NOT reshape it to hide a mismatch. Any mismatch gets recorded here.

## 4. Things to review / where I guessed

- **I guessed the `/api/*` shapes and the two fault strings** — all documented in
  `API_CONTRACT.md` as items for the lead to confirm. Not invented on a whim; they mirror
  teammate B's real chaos endpoints (inject-latency / inject-token-ratelimit).
- **Self-checks that a program CAN confirm (done):** all four mock endpoints return the right
  shapes; CORS preflight returns 204 with the header; the SSE stream emits events including a
  BLOCKED one; both buttons POST the right fault; `.log.blocked` styling + `#blockAlert` exist
  and are applied; JS brackets/quotes balance (comment/string-aware); the initial and
  no-backend state is DISCONNECTED (no hardcoded health).
- **Needs a human to eyeball (cannot be machine-checked here):**
  - Open `index.html` in a real browser and confirm it renders (no JS console errors).
  - Colours/contrast/layout at 1080p; the 🛑 emoji renders; the banner GREEN↔RED transition is
    smooth; the pinned block alert pops and is readable.
  - The on-camera feel of the GREEN→RED→GREEN sequence.
- **Only works with the mock so far** — real backend untested (see §2).
- **Opening via `file://`** works with the mock's permissive CORS, but if any browser is fussy
  about `file://` + EventSource, serve it (`py -3 -m http.server 5173`) and open
  `http://localhost:5173`.

## 5. Demo notes (for the 2.5-minute video)

Recommended on-camera sequence:
1. Start the mock, open the panel → banner is **GREEN 120ms**. Point out guardrails **ON**.
2. Click **Inject Latency Fault** → banner flips **RED · fault: latency**; the terminal streams
   the agent detecting → diagnosing (pool saturated) → guardrail approving → applying (raise
   concurrency) → **GREEN** again, latency 4800 → 180ms. This is the GREEN→RED→GREEN story.
3. (Let it settle back to GREEN.) Click **Inject Rate-Limit Fault** with guardrails **ON**. The
   agent diagnoses a rate limit, proposes the naive fix (raise concurrency) — and the
   **🛑 GUARDRAIL BLOCKED** alert pops. The agent re-plans to the correct fix (shed load) →
   **GREEN**.
4. Optional kicker: toggle guardrails **OFF**, inject rate-limit again → the naive fix is
   applied and **makes it worse** (red ERROR line) → shows exactly why the guardrail matters.

**The one moment that must land:** the **🛑 GUARDRAIL BLOCKED** pinned alert in step 3. Frame
the recording so the top-center alert is fully visible. It is the most memorable 10 seconds and
the clearest proof the agent is reasoning, not replaying a script.

Recording: 1080p, browser maximised, dark theme (already the default).

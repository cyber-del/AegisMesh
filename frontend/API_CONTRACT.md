# API_CONTRACT.md — what the control panel expects from the controller

The frontend (`frontend/index.html`) talks to the **aegis-controller** (team lead) at
**`http://localhost:8100`**. It does NOT talk to teammate B's services directly.

This document is the contract. The mock server (`mock_server.py`) implements exactly these
shapes so the UI can be built standalone. **Lead: please confirm each endpoint matches, or
tell me where it differs — I'll adjust the UI, never the other way around.**

Base URL is a single constant at the top of `index.html`: `const API_BASE = "http://localhost:8100"`.

---

## 1. `GET /api/status`  (polled every 1s by the banner)

Response `200 application/json`:
```json
{
  "status": "GREEN",
  "latency_ms": 120,
  "active_worker_concurrency": 5,
  "active_fault": null,
  "guardrails_enabled": true
}
```
- `status`: `"GREEN"` | `"RED"`. (Any other value / a failed fetch → UI shows DISCONNECTED.)
- `latency_ms`: integer, current p50/observed latency.
- `active_worker_concurrency`: integer, worker-queue pool size.
- `active_fault`: string or `null`. When RED, the UI surfaces this so judges see which fault is live.
- `guardrails_enabled`: bool, drives the toggle's ON/OFF display.

## 2. `POST /api/chaos/inject`

Request body `application/json`:
```json
{ "fault": "latency" }
```
- `fault`: one of the fault identifiers below.
- **⚠️ OPEN QUESTION FOR THE LEAD — confirm these exact string values.** The UI sends
  `"latency"` and `"ratelimit"`. The lead's controller maps them onto teammate B's real chaos
  endpoints (`/chaos/inject-latency` and `/chaos/inject-token-ratelimit`). If the controller
  expects different strings (e.g. `"inject-latency"`, `"token-ratelimit"`), tell me the exact
  values and I'll change the two button handlers — it's a one-line-each edit.

Response: any `2xx` (body ignored by the UI; the banner reflects the *next* `/api/status` poll).

## 3. `POST /api/guardrails/toggle`

Request body `application/json`:
```json
{ "enabled": true }
```
- Turns the safety guardrail on/off. Response: any `2xx`. The UI re-reads `/api/status` to
  confirm `guardrails_enabled`.

## 4. `GET /api/logs/stream`  (Server-Sent Events)

`Content-Type: text/event-stream`. Each SSE message is one JSON object:
```
data: {"timestamp":"2026-07-25T10:00:01Z","stage":"DIAGNOSE","message":"...","level":"INFO"}

```
- `level`: `"INFO"` | `"SUCCESS"` | `"WARNING"` | `"ERROR"` | `"BLOCKED"`.
- `stage`: short label (e.g. `DETECT`, `DIAGNOSE`, `GUARDRAIL`, `APPLY`, `RESOLVE`). Free text.
- `message`: the human-readable log line shown in the terminal.
- **`level: "BLOCKED"`** is the guardrail-rejection moment — the UI styles it boldly (🛑). Send
  it whenever the guardrail refuses a proposed action.
- A message with `stage: "HEARTBEAT"` is a keep-alive; the UI ignores it. Send one every few
  seconds so the stream stays open through proxies.

---

## Required from the lead (blocking items)

1. **CORS.** The UI runs on `http://localhost:5173` (or `file://`) and the controller on
   `:8100` — a different origin. The controller **must** send
   `Access-Control-Allow-Origin: *` (or echo the UI origin) on every `/api/*` response,
   including the SSE endpoint and an `OPTIONS` preflight for the two POSTs. Without this,
   every request fails in the browser with a CORS error and the panel stays DISCONNECTED.
2. **Confirm the exact `fault` string values** (see endpoint 2).
3. Confirm the status enum is exactly `GREEN` / `RED` (not `green`/`healthy`/etc.).

## What the UI guarantees back to the lead

- It renders ONLY what these endpoints return. No fabricated events, no scripted healing.
- Before data arrives or on any fetch failure it shows a neutral DISCONNECTED state, never a
  fake-healthy banner.
- If the real backend's shapes differ from this contract, the mismatch is recorded in
  `HANDOVER_A.md` — the UI is not reshaped to hide it.

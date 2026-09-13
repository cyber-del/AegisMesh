# AegisMesh

An autonomous SRE controller, built for the Agents of SigNoz Hackathon 2026 (Track 01).

Four instrumented microservices run under a simulated load. When one of them is pushed into a fault, the controller reads correlated traces, logs and token-usage metrics over the Model Context Protocol, asks an LLM what to change, checks that proposal against a guardrail engine, and applies the change to the running service through an admin endpoint. Nothing restarts.

## Architecture

```
[ api-gateway ] -> [ worker-queue ] -> [ ai-inference-service ]      [ load-generator ]
    :8001              :8002                  :8003                   (drives traffic)
         |                  |                      |
         +------------------+----------------------+
                            |  OpenTelemetry (traces, logs, GenAI token metrics)
                            v
                   [ self-hosted SigNoz ]
                            |
                            |  JSON-RPC 2.0 over MCP
                            v
                   [ Aegis SRE controller :8100 ]
                      diagnosis -> guardrails -> hot patch
```

## How a fault is handled

1. A fault is injected from the dashboard, for example queue latency on `worker-queue`.
2. The controller asks for trace spans, correlated logs and metric aggregates over MCP.
3. An LLM reads that telemetry and proposes a configuration change with a confidence score.
4. The guardrail engine checks the proposal in a fixed order: a destructive-command blacklist, a whitelist of parameters that may be changed, a service-scope check, value-range clamping, and a cooldown window.
5. If the proposal fails a check it is blocked and re-planned into a safe fallback. If it passes, the controller posts it to the target service's `/admin/config` endpoint.
6. The controller writes an alert rule so the same fault is recognised next time, and takes a shorter path when it recurs.

## The services

Each service exposes `/health`, its own work endpoint, `/admin/config` for live reconfiguration, and chaos endpoints that inject the faults the controller is meant to fix.

The hot patch is the part worth checking. Posting `{"capacity": 42}` to `ai-inference-service/admin/config` changes the running service's capacity and returns what it changed. No restart, no redeploy.

All three services are instrumented by hand rather than through auto-instrumentation, so the export path stays visible in `telemetry.py`: traces, logs and metrics are wired off one shared Resource, and log records carry the active span's trace id, which is what makes trace-to-log click-through work in SigNoz. The inference service records a `gen_ai.client.token.usage` histogram per request.

## Guardrails

Five checks run before anything is applied:

- A blacklist of destructive commands
- A whitelist of parameters that may be changed at all
- A check that the parameter belongs to the service being patched
- Range clamping, so an approved parameter cannot be given an unsafe value
- A cooldown window, so the same target cannot be patched repeatedly

A blocked proposal is not discarded. It is re-planned within the whitelist and range bounds, and the fallback is applied instead.

## What this is not

- **The timings shown in the dashboard are scripted, not measured.** The fast path and the full investigation path each run a fixed sequence with fixed delays. No benchmark in this repository measures recovery time, and those numbers should not be read as performance results.
- **The controller talks to a mock MCP server by default.** `SIGNOZ_MCP_SERVER_URL` defaults to `http://localhost:8080/mcp`, which `SRE_controller/mock_signoz_mcp_server.py` serves. The client also falls back to generated telemetry when a call fails. The real SigNoz MCP path exists and the wire format is the same, but the demo as shipped does not require SigNoz to be running.
- **The guardrails can be turned off.** `GuardrailEngine.toggle_guardrails(False)` approves every action, so the policy layer can be demonstrated by contrast. It is on by default.
- **The faults are injected, not real.** They come from chaos endpoints, not from production traffic.
- **`vector-db` appears in the topology but does not run.** It has a `main.py` and no Dockerfile, and `docker-compose.yml` defines four services without it.
- **There is no test suite for the controller.** `test_day1.py` and `test_day2.py` assert on returned values, not on behaviour under load.

## Running it

Requires Python 3.10 or newer and Docker.

```bash
docker compose up
```

That builds the three services and the load generator on the `signoz-network`, with healthchecks gating startup order. The SigNoz stack itself is deployed separately from `deploy/casting.yaml`, which creates that network.

To run the controller:

```bash
cd SRE_controller
python mock_signoz_mcp_server.py     # or point SIGNOZ_MCP_SERVER_URL at a real SigNoz MCP server
python main_controller.py
```

Then open `frontend/index.html` in a browser.

## Built with

Python, FastAPI, OpenTelemetry, SigNoz, Docker, and the Model Context Protocol. The LLM diagnosis calls Gemini or GPT-4o over their REST APIs.

## Who built what

A two-person hackathon team. 

**V. Abhishek Prakash** built the instrumented service layer: the three FastAPI microservices with their chaos and admin endpoints, the three `telemetry.py` modules, the Dockerfiles and `docker-compose.yml`, the self-hosted SigNoz deployment in `deploy/`, the load generator, and the frontend.

**cyber-del** built the SRE controller in `SRE_controller/`: the diagnostic agent, the guardrail engine, the remediator, the MCP client and the control loop.


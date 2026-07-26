"""
AegisMesh - SigNoz MCP Protocol Server (Port 8080)
Implements JSON-RPC 2.0 endpoint for testing over-the-wire SigNoz MCP tool calls.
"""

from fastapi import FastAPI, Request
import uvicorn
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SigNozMCPServer] %(message)s")
logger = logging.getLogger("SigNozMCPServer")

app = FastAPI(title="SigNoz MCP Server", version="1.0.0")

@app.post("/mcp")
async def handle_mcp_jsonrpc(request: Request):
    data = await request.json()
    method = data.get("method")
    req_id = data.get("id", 1)
    params = data.get("params", {})
    tool_name = params.get("name")
    args = params.get("arguments", {})

    logger.info(f"Received JSON-RPC 2.0 tool call: method='{method}', tool='{tool_name}', args={args}")

    if tool_name == "get_trace_spans":
        trace_id = args.get("trace_id", "trace-cascade-ratelimit-504")
        if "ratelimit" in trace_id.lower():
            spans = [
                {"span_id": "span-gw-001", "service": "api-gateway", "name": "POST /v1/generate", "duration_ms": 5042, "status_code": "ERROR", "attributes": {"http.status_code": 504}},
                {"span_id": "span-wq-002", "service": "worker-queue", "name": "enqueue_job", "duration_ms": 120, "status_code": "OK", "attributes": {}},
                {"span_id": "span-ai-003", "service": "ai-inference-service", "name": "vllm_generate", "duration_ms": 4980, "status_code": "ERROR", "attributes": {"gen_ai.usage.input_tokens": 1420}},
                {"span_id": "span-db-004", "service": "vector-db", "name": "pgvector_search", "duration_ms": 45, "status_code": "OK", "attributes": {}}
            ]
        elif "dblock" in trace_id.lower():
            spans = [
                {"span_id": "span-gw-001", "service": "api-gateway", "name": "POST /v1/generate", "duration_ms": 5042, "status_code": "ERROR", "attributes": {"http.status_code": 504}},
                {"span_id": "span-wq-002", "service": "worker-queue", "name": "enqueue_job", "duration_ms": 200, "status_code": "OK", "attributes": {}},
                {"span_id": "span-ai-003", "service": "ai-inference-service", "name": "vllm_generate", "duration_ms": 300, "status_code": "OK", "attributes": {}},
                {"span_id": "span-db-004", "service": "vector-db", "name": "pgvector_search", "duration_ms": 4820, "status_code": "ERROR", "attributes": {"db.error": "ConnectionLockTimeout"}}
            ]
        else:
            spans = [
                {"span_id": "span-gw-001", "service": "api-gateway", "name": "POST /v1/generate", "duration_ms": 5042, "status_code": "ERROR", "attributes": {"http.status_code": 504}},
                {"span_id": "span-wq-002", "service": "worker-queue", "name": "enqueue_job", "duration_ms": 5010, "status_code": "ERROR", "attributes": {"queue.depth": 48}},
                {"span_id": "span-ai-003", "service": "ai-inference-service", "name": "vllm_generate", "duration_ms": 150, "status_code": "OK", "attributes": {}},
                {"span_id": "span-db-004", "service": "vector-db", "name": "pgvector_search", "duration_ms": 50, "status_code": "OK", "attributes": {}}
            ]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "trace_id": trace_id,
                "root_service": "api-gateway",
                "duration_ms": 5042,
                "spans": spans
            }
        }

    elif tool_name == "get_correlated_logs":
        span_id = args.get("span_id", "")
        trace_id = args.get("trace_id", "")
        if "ratelimit" in trace_id.lower() or "span-ai" in span_id.lower():
            logs = [{"timestamp": "2026-07-26T12:15:00Z", "severity": "ERROR", "service": "ai-inference-service", "body": "RateLimitError: vLLM Token rate limit 500 tokens/sec exceeded for model gpt-4o."}]
        elif "dblock" in trace_id.lower() or "span-db" in span_id.lower():
            logs = [{"timestamp": "2026-07-26T12:15:00Z", "severity": "ERROR", "service": "vector-db", "body": "ConnectionLockTimeout: pgvector database connection pool locked."}]
        else:
            logs = [{"timestamp": "2026-07-26T12:15:00Z", "severity": "ERROR", "service": "worker-queue", "body": "QueueWorkerException: Connection pool exhausted (5/5 active workers blocked)."}]
        return {"jsonrpc": "2.0", "id": req_id, "result": logs}

    elif tool_name == "get_metric_aggregates":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "metric": args.get("metric_name", "gen_ai.usage.input_tokens"),
                "unit": "tokens/sec",
                "threshold_exceeded": True,
                "rates": [{"timestamp": "12:14", "value": 1420}]
            }
        }

    elif tool_name == "create_alert_rule":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "status": "CREATED",
                "rule_id": "rule-signoz-mcp-8080-001",
                "alert_name": args.get("alert_name", "AI Token Rate Limit Spike"),
                "severity": "CRITICAL"
            }
        }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}

if __name__ == "__main__":
    uvicorn.run("mock_signoz_mcp_server:app", host="0.0.0.0", port=8080)

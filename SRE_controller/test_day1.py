"""
AegisMesh - Day 1 Verification Script
Tests SigNoz MCP Telemetry queries & LLM Multi-Signal Root Cause Diagnosis.
"""

import sys
import asyncio
import json
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from mcp_client import SigNozMCPClient
from diagnostic_agent import DiagnosticAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] Day1Test: %(message)s")
logger = logging.getLogger("Day1Test")

async def run_day1_test():
    print("=" * 70)
    print("AEGIS MESH - DAY 1 VERIFICATION TEST")
    print("=" * 70)

    # 1. Initialize MCP Client & Diagnostic Agent
    mcp = SigNozMCPClient()
    agent = DiagnosticAgent()

    test_trace_id = "trace-cascade-504-88f9"
    test_span_id = "span-ai-003"

    try:
        # 2. Fetch Multi-Signal Telemetry via MCP Client
        logger.info(f"Step 1: Fetching Traces from SigNoz MCP for trace_id={test_trace_id}...")
        traces = await mcp.get_trace_spans(test_trace_id)
        
        logger.info(f"Step 2: Fetching Correlated Logs from SigNoz MCP for span_id={test_span_id}...")
        logs = await mcp.get_correlated_logs(test_span_id)
        
        logger.info("Step 3: Fetching GenAI Token Usage Metrics from SigNoz MCP...")
        metrics = await mcp.get_metric_aggregates("gen_ai.usage.input_tokens", timeframe="5m")

        print("\n📊 TELEMETRY BUNDLE RECEIVED FROM SIGNOZ MCP:")
        print(f"  • Trace Status: {traces.get('http_status')} ({traces.get('error')})")
        print(f"  • Correlated Logs Count: {len(logs)}")
        print(f"  • Token Rate Spike: {metrics.get('rates', [{}])[-1].get('value')} tokens/sec")

        # 3. Execute LLM Multi-Signal Root-Cause Analysis
        logger.info("Step 4: Executing Multi-Signal LLM Diagnosis...")
        diagnosis = await agent.analyze(traces, logs, metrics)

        print("\n🧠 LLM DIAGNOSIS RESULT (STRUCTURED JSON):")
        print("-" * 50)
        print(json.dumps(diagnosis.model_dump(), indent=2))
        print("-" * 50)

        # 4. Verify Output Accuracy
        assert diagnosis.failing_service == "ai-inference-service"
        assert diagnosis.target_param == "MAX_WORKER_CONCURRENCY"
        assert diagnosis.recommended_value == 50

        print("\n✅ DAY 1 VERIFICATION PASSED SUCCESSFULLY!")
        print("Your SRE Controller successfully queried SigNoz MCP telemetry and derived the correct root cause!")
        print("=" * 70)

    finally:
        await mcp.close()

if __name__ == "__main__":
    asyncio.run(run_day1_test())

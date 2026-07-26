"""
AegisMesh - Day 2 Verification Script
Tests Guardrail Evaluation, Hot-Patch Execution, and E2E Self-Healing Pipeline.
"""

import sys
import asyncio
import json
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from diagnostic_agent import DiagnosisResult
from guardrail_engine import GuardrailEngine
from remediator import Remediator
from main_controller import execute_autonomous_healing_loop, system_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] Day2Test: %(message)s")
logger = logging.getLogger("Day2Test")

async def run_day2_test():
    print("=" * 70)
    print("AEGIS MESH - DAY 2 VERIFICATION TEST")
    print("=" * 70)

    # 1. Test Guardrail Engine Policy Checks
    print("\n🛡️ TEST 1: GUARDRAIL CONTROL ENGINE EVALUATION")
    guardrail = GuardrailEngine(cooldown_seconds=1)

    # Valid Diagnosis
    valid_diag = DiagnosisResult(
        failing_service="ai-inference-service",
        failure_mode="TOKEN_RATE_LIMIT_EXHAUSTION",
        recommended_action="ADJUST_WORKER_CONCURRENCY",
        target_param="MAX_WORKER_CONCURRENCY",
        recommended_value=50,
        confidence=0.98,
        explanation="Valid action"
    )

    decision = guardrail.evaluate_action(valid_diag)
    print(f"  • Valid Action Result: Approved={decision.approved} ({decision.reason})")
    assert decision.approved == True

    # Invalid Action (Blacklisted keyword)
    malicious_diag = DiagnosisResult(
        failing_service="ai-inference-service",
        failure_mode="HACK",
        recommended_action="RAW_SQL",
        target_param="DROP TABLE users",
        recommended_value=1,
        confidence=0.99,
        explanation="DROP DATABASE"
    )

    bad_decision = guardrail.evaluate_action(malicious_diag)
    print(f"  • Malicious Action Result: Approved={bad_decision.approved} ({bad_decision.reason})")
    assert bad_decision.approved == False

    # 2. Test Remediator Hot-Patch
    print("\n🔧 TEST 2: RUNTIME HOT-PATCH EXECUTION")
    remediator = Remediator()
    patch_result = await remediator.apply_hot_patch("worker-queue", "MAX_WORKER_CONCURRENCY", 50)
    print(f"  • Hot-Patch Response: Status={patch_result.get('status')}, Applied={patch_result.get('applied_patch')}")
    assert patch_result.get("status") == "SUCCESS"
    await remediator.close()

    # 3. Test End-to-End Autonomous Healing Pipeline
    print("\n🚀 TEST 3: END-TO-END AUTONOMOUS SELF-HEALING PIPELINE")
    await execute_autonomous_healing_loop("trace-day2-test-999")

    print("\n📊 SYSTEM STATE AFTER HEALING:")
    print(f"  • Health Status: {system_state['status']}")
    print(f"  • Latency: {system_state['latency_ms']}ms")
    print(f"  • Concurrency: {system_state['active_worker_concurrency']}")
    print(f"  • Duration: {system_state['last_healing_event'].get('duration_sec')}s")

    assert system_state["status"] == "GREEN"
    assert system_state["latency_ms"] == 120

    print("\n✅ DAY 2 VERIFICATION PASSED SUCCESSFULLY!")
    print("Your Guardrails, Remediator, and E2E Self-Healing Loop are 100% operational!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_day2_test())

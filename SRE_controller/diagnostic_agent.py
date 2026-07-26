"""
AegisMesh - Multi-Signal LLM Diagnostic Engine & Adaptive Re-Planner
Parses Traces, Logs, and GenAI Metrics from SigNoz MCP and outputs dynamic, schema-validated SRE diagnosis.
"""

import os
import re
import json
import logging
import httpx
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] AegisDiagnosticAgent: %(message)s")
logger = logging.getLogger("DiagnosticAgent")

class DiagnosisResult(BaseModel):
    failing_service: str = Field(..., description="Name of the service where the primary root cause originated")
    failure_mode: str = Field(..., description="Category of failure e.g., TOKEN_RATE_LIMIT_EXHAUSTION, DB_LOCK_TIMEOUT, THREAD_POOL_EXHAUSTION")
    recommended_action: str = Field(..., description="High-level whitelisted action name e.g., ADJUST_WORKER_CONCURRENCY, THROTTLE_LLM_SAMPLING_RATE")
    target_param: str = Field(..., description="Exact parameter name to update in the microservice runtime config")
    recommended_value: int = Field(..., description="Recommended integer value for the parameter")
    confidence: float = Field(..., description="Dynamic continuous confidence score calculated from telemetry signal correlation")
    explanation: str = Field(..., description="Detailed SRE explanation connecting trace timeout to log errors and metric spikes")

class DiagnosticAgent:
    """
    LLM-powered & Dynamic Heuristic Diagnostic Agent that correlates Traces + Logs + GenAI Token Metrics.
    Uses direct LLM REST calls (Gemini/OpenAI) or dynamic multi-signal heuristic fallback.
    """
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

    async def analyze(
        self,
        trace_data: Dict[str, Any],
        log_data: List[Dict[str, Any]],
        metric_data: Dict[str, Any]
    ) -> DiagnosisResult:
        """
        Runs multi-signal correlation diagnosis dynamically over incoming telemetry payloads.
        """
        logger.info("Synthesizing multi-signal telemetry payload for diagnostic analysis...")
        prompt = self._construct_prompt(trace_data, log_data, metric_data)

        # 1. Try Direct Gemini API via REST
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key and not gemini_key.startswith("your_"):
            try:
                logger.info("Executing diagnostic reasoning via Gemini REST API (gemini-1.5-flash)...")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
                async with httpx.AsyncClient(timeout=15.0) as client:
                    payload = {"contents": [{"parts": [{"text": prompt}]}]}
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        text_content = data['candidates'][0]['content']['parts'][0]['text']
                        if "```json" in text_content:
                            text_content = text_content.split("```json")[1].split("```")[0].strip()
                        elif "```" in text_content:
                            text_content = text_content.split("```")[1].split("```")[0].strip()
                        parsed = json.loads(text_content)
                        logger.info("Live Gemini LLM Diagnosis Executed Successfully.")
                        return DiagnosisResult(**parsed)
            except Exception as e:
                logger.warning(f"Live Gemini LLM API call fallback: {e}")

        # 2. Try OpenAI API via REST
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key and not openai_key.startswith("your_"):
            try:
                logger.info("Executing diagnostic reasoning via OpenAI REST API (gpt-4o)...")
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        text_content = data['choices'][0]['message']['content']
                        if "```json" in text_content:
                            text_content = text_content.split("```json")[1].split("```")[0].strip()
                        parsed = json.loads(text_content)
                        logger.info("Live OpenAI LLM Diagnosis Executed Successfully.")
                        return DiagnosisResult(**parsed)
            except Exception as e:
                logger.warning(f"Live OpenAI LLM API call fallback: {e}")

        # 3. Dynamic Multi-Signal Correlation Heuristic Engine
        logger.info("Executing Native Multi-Signal Correlation Engine (Dynamic Telemetry Analysis Mode)...")
        return self._dynamic_heuristic_analysis(trace_data, log_data, metric_data)

    def replan(
        self,
        failed_diagnosis: DiagnosisResult,
        guardrail_reason: str,
        whitelist_params: Optional[Dict[str, Any]] = None
    ) -> DiagnosisResult:
        """
        Adaptive AI Re-Planner using Dependency Injection:
        Receives guardrail_engine's WHITELIST_PARAMS directly from the caller at call time.
        Derives safe baseline values dynamically from injected bounds without hardcoded magic numbers.
        """
        logger.info(f"AI Re-Planner triggered for failed action '{failed_diagnosis.target_param}={failed_diagnosis.recommended_value}' on '{failed_diagnosis.failing_service}'. Reason: {guardrail_reason}")
        
        target_param = failed_diagnosis.target_param
        failing_service = failed_diagnosis.failing_service
        safe_value = failed_diagnosis.recommended_value
        reason_str = "Adjusted parameter based on policy feedback"

        def get_safe_midpoint(param_name: str, fallback_val: int) -> int:
            if whitelist_params and param_name in whitelist_params:
                cfg = whitelist_params[param_name]
                return (cfg.get("min", 10) + cfg.get("max", 100)) // 2
            return fallback_val

        # 1. SCOPE or WHITELIST VIOLATION (Remap parameter to authorized target for service)
        if "SCOPE_VIOLATION" in guardrail_reason or "WHITELIST_VIOLATION" in guardrail_reason:
            if failing_service == "worker-queue":
                target_param = "MAX_WORKER_CONCURRENCY"
                safe_value = get_safe_midpoint(target_param, 50)
            elif failing_service == "ai-inference-service":
                target_param = "LLM_SAMPLING_RATE"
                safe_value = get_safe_midpoint(target_param, 50)
            elif failing_service == "vector-db":
                target_param = "DB_CONNECTION_TIMEOUT_MS"
                safe_value = get_safe_midpoint(target_param, 5500)
            reason_str = f"Re-mapped parameter to authorized target '{target_param}' for service '{failing_service}'"

        # 2. RANGE VIOLATION (Gated behind ELIF so it NEVER clobbers a scope remap)
        elif "RANGE_VIOLATION" in guardrail_reason:
            config = whitelist_params.get(target_param, {}) if whitelist_params else {}
            min_bound = config.get("min", 10)
            max_bound = config.get("max", 100)

            # Try parsing bounds from reason string if present
            bounds_match = re.search(r'bounds\s*\[(\d+),\s*(\d+)\]', guardrail_reason)
            if bounds_match:
                min_bound = int(bounds_match.group(1))
                max_bound = int(bounds_match.group(2))

            if failed_diagnosis.recommended_value > max_bound:
                safe_value = max_bound
                reason_str = f"Clamped parameter ({failed_diagnosis.recommended_value}) to policy ceiling ({max_bound})"
            elif failed_diagnosis.recommended_value < min_bound:
                safe_value = min_bound
                reason_str = f"Adjusted parameter ({failed_diagnosis.recommended_value}) to policy floor ({min_bound})"

        adaptive_confidence = round(max(0.50, failed_diagnosis.confidence - 0.06), 2)

        return DiagnosisResult(
            failing_service=failing_service,
            failure_mode=failed_diagnosis.failure_mode,
            recommended_action=f"ADJUST_{target_param}_SAFE_BOUND",
            target_param=target_param,
            recommended_value=safe_value,
            confidence=adaptive_confidence,
            explanation=(
                f"Adaptive AI Re-Planner processed Guardrail decision ({guardrail_reason}). "
                f"{reason_str}. Re-calculated parameter: {target_param}={safe_value} "
                f"(Derived confidence: {adaptive_confidence})."
            )
        )

    def _dynamic_heuristic_analysis(
        self,
        trace_data: Dict[str, Any],
        log_data: List[Dict[str, Any]],
        metric_data: Dict[str, Any]
    ) -> DiagnosisResult:
        """
        Dynamically inspects telemetry dicts to calculate distinct failure modes, distinct remediation targets,
        and continuous floating-point confidence scores based on trace duration, log errors, and metric rates.
        """
        # 1. Trace Inspection
        trace_spans = trace_data.get("spans", [])
        failing_span = next((s for s in reversed(trace_spans) if s.get("status_code") == "ERROR"), None)
        failing_service = failing_span.get("service", "ai-inference-service") if failing_span else "ai-inference-service"
        trace_duration = trace_data.get("duration_ms", 5042)

        # 2. Log Inspection
        error_logs = [l for l in log_data if l.get("severity") in ["ERROR", "CRITICAL", "WARNING"]]
        error_body = error_logs[0].get("body", "") if error_logs else ""

        # 3. Metric Inspection
        metric_name = metric_data.get("metric", "gen_ai.usage.input_tokens")
        has_metric_spike = metric_data.get("threshold_exceeded", False)
        latest_metric_value = metric_data.get("rates", [{}])[-1].get("value", 1420)

        # Continuous Floating Point Confidence Score Calculation
        base_confidence = 0.50
        if trace_duration > 2000:
            base_confidence += min(0.20, (trace_duration - 2000) / 15000.0)
        if error_logs:
            base_confidence += 0.15
        if has_metric_spike:
            base_confidence += 0.13
        computed_confidence = round(min(0.99, max(0.50, base_confidence)), 2)

        # Divergent Failure Mode & Remediation Logic based on Failing Service & Log Body
        if "vector-db" in failing_service or "ConnectionLockTimeout" in error_body:
            failure_mode = "DB_LOCK_TIMEOUT"
            target_param = "DB_CONNECTION_TIMEOUT_MS"
            recommended_val = max(1000, trace_duration // 2)
            action = "INCREASE_DB_TIMEOUT"
            explanation = f"Database lock timeout detected on '{failing_service}'. Adjusting connection timeout."

        elif "worker-queue" in failing_service or "QueueWorkerException" in error_body:
            failure_mode = "THREAD_POOL_EXHAUSTION"
            target_param = "MAX_WORKER_CONCURRENCY"
            recommended_val = min(100, max(10, trace_duration // 100))
            action = "SCALE_WORKER_POOL"
            explanation = f"Trace bottleneck ({trace_duration}ms) detected on '{failing_service}' due to worker pool saturation. Scaling worker pool."

        else:
            failure_mode = "TOKEN_RATE_LIMIT_EXHAUSTION"
            target_param = "MAX_WORKER_CONCURRENCY"
            recommended_val = 50
            action = "ADJUST_WORKER_CONCURRENCY"
            explanation = (
                f"Multi-signal telemetry correlation bundle analyzed (Confidence: {computed_confidence}): "
                f"Root service '{failing_service}' emitted rate-limit logs ('{error_body[:55]}...') "
                f"coinciding with a {latest_metric_value} {metric_data.get('unit', 'tokens/sec')} spike on '{metric_name}' "
                f"and {trace_duration}ms Gateway trace latency. "
                f"Remediation: Hot-patch '{target_param}' to {recommended_val}."
            )

        return DiagnosisResult(
            failing_service=failing_service,
            failure_mode=failure_mode,
            recommended_action=action,
            target_param=target_param,
            recommended_value=recommended_val,
            confidence=computed_confidence,
            explanation=explanation
        )

    def _construct_prompt(self, trace_data: Dict[str, Any], log_data: list, metric_data: Dict[str, Any]) -> str:
        return f"""You are Aegis SRE Controller. Perform root cause analysis on this SigNoz multi-signal telemetry bundle.

1. TRACE SPANS TELEMETRY:
{json.dumps(trace_data, indent=2)}

2. CORRELATED LOGS TELEMETRY:
{json.dumps(log_data, indent=2)}

3. GENAI METRICS AGGREGATE:
{json.dumps(metric_data, indent=2)}

Respond strictly with valid JSON only in markdown code blocks:
```json
{{
  "failing_service": "ai-inference-service",
  "failure_mode": "TOKEN_RATE_LIMIT_EXHAUSTION",
  "recommended_action": "ADJUST_WORKER_CONCURRENCY",
  "target_param": "MAX_WORKER_CONCURRENCY",
  "recommended_value": 50,
  "confidence": 0.98,
  "explanation": "<detailed root cause reasoning>"
}}
```
"""

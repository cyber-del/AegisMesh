"""
AegisMesh - Zero-Trust Guardrail Control Engine
Validates LLM diagnostic decisions against strict whitelist parameters, authorized service scopes, security blacklists, and cooldown timers.
"""

import time
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from diagnostic_agent import DiagnosisResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] AegisGuardrail: %(message)s")
logger = logging.getLogger("GuardrailEngine")

class GuardrailDecision(BaseModel):
    approved: bool = Field(..., description="Whether the proposed action passed all policy checks")
    action: str = Field(..., description="Whitelisted action name evaluated")
    target_param: str = Field(..., description="Target runtime parameter")
    target_value: int = Field(..., description="Target value to set")
    reason: str = Field(..., description="Detailed policy evaluation explanation")
    cooldown_remaining_sec: int = Field(default=0, description="Remaining seconds if blocked by cooldown")

class GuardrailEngine:
    """
    Zero-Trust Policy Checker for SRE Autonomous Remediation.
    Enforces Whitelists, Target Service Scopes, Security Blacklists, and Cooldown Timers.
    """
    WHITELIST_PARAMS = {
        "MAX_WORKER_CONCURRENCY": {"min": 10, "max": 100, "allowed_services": ["worker-queue", "api-gateway", "ai-inference-service"]},
        "LLM_SAMPLING_RATE": {"min": 1, "max": 100, "allowed_services": ["ai-inference-service"]},
        "QUEUE_TIMEOUT_MS": {"min": 100, "max": 5000, "allowed_services": ["worker-queue"]},
        "DB_CONNECTION_TIMEOUT_MS": {"min": 1000, "max": 10000, "allowed_services": ["vector-db"]}
    }

    FORBIDDEN_KEYWORDS = [
        "DROP", "DELETE", "TRUNCATE", "RM -RF", "CHMOD", "CHOWN",
        "/ETC/", "PASSWORD", "SECRET", "CREDENTIAL", "SUDO"
    ]

    def __init__(self, cooldown_seconds: int = 10):
        self.cooldown_seconds = cooldown_seconds
        self.last_execution_time: Dict[str, float] = {}
        self.guardrails_enabled: bool = True

    def toggle_guardrails(self, enabled: bool) -> bool:
        self.guardrails_enabled = enabled
        logger.info(f"Guardrail Control Engine state updated: enabled={self.guardrails_enabled}")
        return self.guardrails_enabled

    def evaluate_action(self, diagnosis: DiagnosisResult) -> GuardrailDecision:
        """
        Evaluates a DiagnosisResult against zero-trust policy rules.
        Order of evaluation: Blacklist ➔ Whitelist Param ➔ Service Scope Auth ➔ Range Bounds ➔ Cooldown Timers.
        """
        param = diagnosis.target_param
        val = diagnosis.recommended_value
        service = diagnosis.failing_service
        explanation_upper = diagnosis.explanation.upper()

        logger.info(f"Evaluating Guardrail Policy for action: set {param}={val} on {service}")

        # If Guardrails are manually toggled OFF (for hackathon demo policy testing)
        if not self.guardrails_enabled:
            logger.warning("Guardrails are currently DISABLED (Demo Mode). Action automatically approved.")
            return GuardrailDecision(
                approved=True,
                action=diagnosis.recommended_action,
                target_param=param,
                target_value=val,
                reason="GUARDRAILS_DISABLED: Policy checks bypassed in demo mode."
            )

        # 1. Security Blacklist Filter
        for keyword in self.FORBIDDEN_KEYWORDS:
            if keyword in explanation_upper or keyword in param.upper():
                logger.error(f"GUARDRAIL BLOCKED: Forbidden keyword '{keyword}' detected in action payload.")
                return GuardrailDecision(
                    approved=False,
                    action=diagnosis.recommended_action,
                    target_param=param,
                    target_value=val,
                    reason=f"SECURITY_POLICY_VIOLATION: Forbidden keyword '{keyword}' detected."
                )

        # 2. Whitelist Parameter Check
        if param not in self.WHITELIST_PARAMS:
            logger.error(f"GUARDRAIL BLOCKED: Parameter '{param}' is not in the approved whitelist.")
            return GuardrailDecision(
                approved=False,
                action=diagnosis.recommended_action,
                target_param=param,
                target_value=val,
                reason=f"WHITELIST_VIOLATION: Parameter '{param}' is not authorized for autonomous hot-patching."
            )

        config = self.WHITELIST_PARAMS[param]

        # 3. Target Service Scope Authorization Check
        allowed_services = config.get("allowed_services", [])
        if allowed_services and service not in allowed_services:
            logger.error(f"GUARDRAIL BLOCKED: Parameter '{param}' is not authorized for target service '{service}'. Allowed: {allowed_services}")
            return GuardrailDecision(
                approved=False,
                action=diagnosis.recommended_action,
                target_param=param,
                target_value=val,
                reason=f"SCOPE_VIOLATION: Parameter '{param}' is authorized only for services {allowed_services}, not '{service}'."
            )

        # 4. Value Boundary Check
        min_val = config["min"]
        max_val = config["max"]
        if not (min_val <= val <= max_val):
            logger.error(f"GUARDRAIL BLOCKED: Value {val} for '{param}' out of safe range [{min_val}, {max_val}].")
            return GuardrailDecision(
                approved=False,
                action=diagnosis.recommended_action,
                target_param=param,
                target_value=val,
                reason=f"RANGE_VIOLATION: Value {val} for '{param}' is outside safe bounds [{min_val}, {max_val}]."
            )

        # 5. Cooldown Timer Check
        now = time.time()
        last_time = self.last_execution_time.get(service, 0)
        elapsed = now - last_time
        if elapsed < self.cooldown_seconds:
            remaining = int(self.cooldown_seconds - elapsed)
            logger.warning(f"GUARDRAIL BLOCKED: Cooldown active for service '{service}'. {remaining}s remaining.")
            return GuardrailDecision(
                approved=False,
                action=diagnosis.recommended_action,
                target_param=param,
                target_value=val,
                reason=f"COOLDOWN_ACTIVE: Action on '{service}' locked for another {remaining} seconds.",
                cooldown_remaining_sec=remaining
            )

        # Record execution time upon approval
        self.last_execution_time[service] = now

        logger.info(f"✅ GUARDRAIL PASSED: Action '{param}={val}' on '{service}' is APPROVED.")
        return GuardrailDecision(
            approved=True,
            action=diagnosis.recommended_action,
            target_param=param,
            target_value=val,
            reason="POLICY_PASSED: Whitelist, service scope, security blacklist, and cooldown checks passed successfully."
        )

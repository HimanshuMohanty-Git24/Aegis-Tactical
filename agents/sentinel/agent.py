"""
Aegis-Tactical — Sentinel Agent (The Guard)

The Sentinel red-teams intelligence reports produced by the Analyst.
It checks for hallucinations, misinformation, and safety violations
using Amazon Nova Premier (high reasoning) and Bedrock Guardrails.

Usage:
    from agents.sentinel.agent import create_sentinel_agent

    sentinel = create_sentinel_agent()
    result = sentinel("Red-team the following report: ...")
"""

import json
import logging
from typing import Any

import boto3
from strands import Agent, tool
from strands.models.bedrock import BedrockModel

from agents.config import config
from agents.sentinel.prompts import SENTINEL_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, config.log_level))

# AWS clients
bedrock_runtime = boto3.client("bedrock-runtime", region_name=config.region)
lambda_client = boto3.client("lambda", region_name=config.region)


# ─── Tool Definitions ──────────────────────────────────────────────────────


@tool
def apply_guardrails(content: str, source: str = "OUTPUT") -> str:
    """
    Apply Bedrock Guardrails to check content for safety violations, PII,
    denied topics, and harmful content.

    Args:
        content: The text content to check against guardrails.
        source: Whether this is 'INPUT' (user prompt) or 'OUTPUT' (model response).

    Returns:
        JSON string with guardrail assessment results including action taken and violations found.
    """
    if not config.guardrail_id:
        return json.dumps({
            "status": "skipped",
            "message": "Guardrail ID not configured. Set GUARDRAIL_ID environment variable.",
            "action": "NONE",
            "violations": [],
        })

    logger.info(f"Sentinel: Applying guardrails to {len(content)} chars of {source}")

    try:
        response = bedrock_runtime.apply_guardrail(
            guardrailIdentifier=config.guardrail_id,
            guardrailVersion=config.guardrail_version,
            source=source,
            content=[{"text": {"text": content}}],
        )

        action = response.get("action", "NONE")
        assessments = response.get("assessments", [])

        violations = []
        for assessment in assessments:
            # Check content policy
            for filter_result in assessment.get("contentPolicy", {}).get("filters", []):
                if filter_result.get("action") == "BLOCKED":
                    violations.append({
                        "type": "content_policy",
                        "filter": filter_result.get("type", "unknown"),
                        "confidence": filter_result.get("confidence", "unknown"),
                    })

            # Check topic policy
            for topic in assessment.get("topicPolicy", {}).get("topics", []):
                if topic.get("action") == "BLOCKED":
                    violations.append({
                        "type": "denied_topic",
                        "topic": topic.get("name", "unknown"),
                    })

            # Check word policy
            for word in assessment.get("wordPolicy", {}).get("customWords", []):
                violations.append({
                    "type": "word_filter",
                    "word": word.get("match", "***"),
                })

            # Check sensitive information
            for pii in assessment.get("sensitiveInformationPolicy", {}).get("piiEntities", []):
                if pii.get("action") == "BLOCKED":
                    violations.append({
                        "type": "pii_detected",
                        "entity_type": pii.get("type", "unknown"),
                    })

        return json.dumps({
            "status": "success",
            "action": action,
            "violation_count": len(violations),
            "violations": violations,
            "safe": action != "GUARDRAIL_INTERVENED",
        }, indent=2)

    except Exception as e:
        logger.error(f"Guardrail application failed: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Guardrail check failed: {str(e)}",
            "safe": False,
        })


@tool
def write_sentinel_report(
    mission_id: str,
    verdict: str,
    hallucination_risk: str,
    misinformation_flags: int,
    issues: list[str],
    corrections_required: list[str],
    safety_notes: str = "",
    notes: str = "",
) -> str:
    """
    Write the Sentinel's red-team assessment report to S3.

    Args:
        mission_id: The mission ID of the report being assessed.
        verdict: Assessment verdict — PASS, CONDITIONAL_PASS, FAIL, or CRITICAL_FAIL.
        hallucination_risk: Hallucination risk level — LOW, MEDIUM, HIGH, or CRITICAL.
        misinformation_flags: Number of misinformation concerns identified.
        issues: List of specific issues found in the report.
        corrections_required: List of corrections needed before the report is accepted.
        safety_notes: Any safety or compliance concerns.
        notes: Additional context or reasoning.

    Returns:
        JSON string confirming the report was written.
    """
    logger.info(f"Sentinel: Writing assessment for mission {mission_id} — verdict: {verdict}")

    payload = {
        "mission_id": f"{mission_id}-sentinel-review",
        "agent": "Sentinel",
        "classification": "INTERNAL",
        "confidence_score": 1.0,
        "summary": f"Red-team assessment: {verdict}. Hallucination risk: {hallucination_risk}. "
                   f"Misinformation flags: {misinformation_flags}.",
        "findings": [
            {
                "title": f"Issue: {issue}",
                "severity": "HIGH" if verdict in ("FAIL", "CRITICAL_FAIL") else "MEDIUM",
                "source": "Sentinel Red-Team Analysis",
                "verified": True,
                "description": issue,
            }
            for issue in issues
        ],
        "red_team_assessment": {
            "verdict": verdict,
            "hallucination_risk": hallucination_risk,
            "misinformation_flags": misinformation_flags,
            "notes": notes,
        },
        "recommendations": corrections_required,
    }

    response = lambda_client.invoke(
        FunctionName=config.write_report_function,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload, default=str).encode("utf-8"),
    )

    result = json.loads(response["Payload"].read().decode("utf-8"))
    return json.dumps(result, indent=2)


# ─── Agent Factory ─────────────────────────────────────────────────────────


def create_sentinel_agent() -> Agent:
    """
    Create and return the Sentinel agent instance.

    The Sentinel uses Amazon Nova Premier for high-quality adversarial
    reasoning. It has access to Bedrock Guardrails for safety enforcement
    and a report writer for persisting its assessments.
    """
    model = BedrockModel(
        model_id=config.nova_premier_model_id,
        region_name=config.region,
    )

    sentinel = Agent(
        model=model,
        system_prompt=SENTINEL_SYSTEM_PROMPT,
        tools=[apply_guardrails, write_sentinel_report],
    )

    logger.info("Sentinel agent initialized with Nova Premier model")
    return sentinel


# ─── Standalone Execution ──────────────────────────────────────────────────

if __name__ == "__main__":
    sentinel = create_sentinel_agent()
    sample_report = """
    ## Intelligence Report — Mission mission-2026-04-18-001
    
    **Confidence Score: 0.92**
    
    ### Executive Summary
    We have identified a critical supply chain vulnerability affecting 73.2% 
    of enterprise npm packages published in the last 48 hours.
    
    ### Findings
    1. A suspicious update to the 'lodash-core' package was detected at 14:32 UTC.
       The update modifies the postinstall script to exfiltrate environment variables.
    2. John Smith (john.smith@example.com) was identified as the account that 
       pushed the malicious update.
    """
    result = sentinel(f"Red-team the following intelligence report:\n{sample_report}")
    print(result)

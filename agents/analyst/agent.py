"""
Aegis-Tactical — Analyst Agent (The Researcher)

The Analyst performs RAG-based verification against the ground truth
Knowledge Base and generates structured intelligence reports. Powered
by Amazon Nova Premier for high-quality reasoning.

Usage:
    from agents.analyst.agent import create_analyst_agent

    analyst = create_analyst_agent()
    result = analyst("Verify and analyze the following intelligence: ...")
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import boto3
from strands import Agent, tool
from strands.models.bedrock import BedrockModel

from agents.config import config
from agents.analyst.prompts import ANALYST_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, config.log_level))

# AWS clients
bedrock_agent_client = boto3.client("bedrock-agent-runtime", region_name=config.region)
lambda_client = boto3.client("lambda", region_name=config.region)


# ─── Tool Definitions ──────────────────────────────────────────────────────


@tool
def query_knowledge_base(query: str, max_results: int = 5) -> str:
    """
    Query the Aegis-Tactical Knowledge Base to retrieve relevant ground truth documents.
    Use this to verify claims, find corroborating evidence, or discover contradictions.

    Args:
        query: The search query — a question or claim to verify against ground truth.
        max_results: Maximum number of relevant passages to return (default 5).

    Returns:
        JSON string with relevant passages, their source documents, and relevance scores.
    """
    if not config.knowledge_base_id:
        return json.dumps({
            "status": "error",
            "message": "Knowledge Base ID not configured. Set KNOWLEDGE_BASE_ID environment variable.",
        })

    logger.info(f"Analyst: Querying knowledge base — '{query[:80]}...'")

    try:
        response = bedrock_agent_client.retrieve(
            knowledgeBaseId=config.knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": min(max_results, 25),
                }
            },
        )

        results = []
        for item in response.get("retrievalResults", []):
            content = item.get("content", {}).get("text", "")
            location = item.get("location", {})
            score = item.get("score", 0.0)

            source_info = "Unknown"
            if location.get("type") == "S3":
                source_info = location.get("s3Location", {}).get("uri", "Unknown S3 location")

            results.append({
                "text": content[:2000],  # Limit passage length
                "source": source_info,
                "relevance_score": round(score, 4),
            })

        return json.dumps({
            "status": "success",
            "query": query,
            "result_count": len(results),
            "results": results,
        }, indent=2)

    except Exception as e:
        logger.error(f"Knowledge Base query failed: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Knowledge Base query failed: {str(e)}",
        })


@tool
def write_report(
    mission_id: str,
    summary: str,
    findings: list[dict[str, Any]],
    confidence_score: float,
    classification: str = "UNCLASSIFIED",
    recommendations: list[str] = None,
) -> str:
    """
    Write a structured intelligence report and persist it to secure S3 storage.

    Args:
        mission_id: Unique mission identifier (e.g., 'mission-2026-04-18-001').
        summary: Executive summary of the analysis (2-3 sentences).
        findings: List of finding objects, each with 'title', 'severity', 'source', 'verified', 'description'.
        confidence_score: Overall confidence score (0.0 to 1.0).
        classification: Report classification level (UNCLASSIFIED, CONFIDENTIAL, SECRET).
        recommendations: List of actionable recommendations.

    Returns:
        JSON string with the S3 location of the written report.
    """
    if recommendations is None:
        recommendations = []

    logger.info(f"Analyst: Writing report for mission {mission_id}")

    payload = {
        "mission_id": mission_id,
        "agent": "Analyst",
        "classification": classification,
        "confidence_score": confidence_score,
        "summary": summary,
        "findings": findings,
        "recommendations": recommendations,
    }

    response = lambda_client.invoke(
        FunctionName=config.write_report_function,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload, default=str).encode("utf-8"),
    )

    result = json.loads(response["Payload"].read().decode("utf-8"))
    return json.dumps(result, indent=2)


# ─── Agent Factory ─────────────────────────────────────────────────────────


def create_analyst_agent() -> Agent:
    """
    Create and return the Analyst agent instance.

    The Analyst uses Amazon Nova Premier for deep reasoning and has access
    to the Knowledge Base for RAG verification and a report writer for
    persisting findings.
    """
    model = BedrockModel(
        model_id=config.nova_premier_model_id,
        region_name=config.region,
    )

    analyst = Agent(
        model=model,
        system_prompt=ANALYST_SYSTEM_PROMPT,
        tools=[query_knowledge_base, write_report],
    )

    logger.info("Analyst agent initialized with Nova Premier model")
    return analyst


# ─── Standalone Execution ──────────────────────────────────────────────────

if __name__ == "__main__":
    analyst = create_analyst_agent()
    result = analyst(
        "Verify the following intelligence: "
        "There has been a new supply chain attack targeting npm packages. "
        "Cross-reference with our ground truth knowledge base and produce a report."
    )
    print(result)

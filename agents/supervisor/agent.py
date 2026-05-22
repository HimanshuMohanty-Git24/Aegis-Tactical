"""
Aegis-Tactical — Supervisor Agent (The General)

The Supervisor orchestrates the entire multi-agent system using the
Agent-as-Tool pattern. It delegates tasks to the Scout, Analyst, and
Sentinel agents, manages the mission lifecycle, and delivers the
final briefing to the user.

Usage:
    from agents.supervisor.agent import create_supervisor_agent

    supervisor = create_supervisor_agent()
    result = supervisor("Investigate recent supply chain security threats and verify against our intelligence base")
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from strands import Agent, tool
from strands.models.bedrock import BedrockModel

from agents.config import config
from agents.supervisor.prompts import SUPERVISOR_SYSTEM_PROMPT
from agents.scout.agent import create_scout_agent
from agents.analyst.agent import create_analyst_agent
from agents.sentinel.agent import create_sentinel_agent

logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, config.log_level))

# ─── Sub-Agent Instances (lazy-initialized) ────────────────────────────────
_scout_agent = None
_analyst_agent = None
_sentinel_agent = None


def _get_scout():
    global _scout_agent
    if _scout_agent is None:
        _scout_agent = create_scout_agent()
    return _scout_agent


def _get_analyst():
    global _analyst_agent
    if _analyst_agent is None:
        _analyst_agent = create_analyst_agent()
    return _analyst_agent


def _get_sentinel():
    global _sentinel_agent
    if _sentinel_agent is None:
        _sentinel_agent = create_sentinel_agent()
    return _sentinel_agent


# ─── Tool Definitions (Agent-as-Tool Pattern) ──────────────────────────────


@tool
def deploy_scout(task_description: str) -> str:
    """
    Deploy the Scout agent to gather intelligence from external sources.
    The Scout can fetch news, parse RSS feeds, and monitor GitHub repositories.

    Args:
        task_description: Clear, specific instructions for what intelligence
            the Scout should gather. Be explicit about sources and topics.
            Example: "Fetch the latest cybersecurity news and check the
            aws/aws-cdk GitHub repo for recent commits related to security."

    Returns:
        The Scout's intelligence report as a string.
    """
    logger.info(f"Supervisor: Deploying Scout — '{task_description[:100]}...'")

    try:
        scout = _get_scout()
        result = scout(task_description)
        response = str(result)
        logger.info(f"Supervisor: Scout returned {len(response)} chars")
        return response
    except Exception as e:
        error_msg = f"Scout agent failed: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"status": "error", "agent": "Scout", "message": error_msg})


@tool
def deploy_analyst(task_description: str) -> str:
    """
    Deploy the Analyst agent to verify intelligence against the ground truth
    Knowledge Base and produce structured analysis reports.

    Args:
        task_description: Clear instructions for the Analyst, including the
            raw intelligence to analyze and specific verification requests.
            Always include the Scout's findings in the task description.
            Example: "Verify and analyze the following Scout intelligence:
            [Scout findings here]. Cross-reference with ground truth and
            produce a report with mission ID 'mission-2026-04-18-001'."

    Returns:
        The Analyst's verified intelligence report as a string.
    """
    logger.info(f"Supervisor: Deploying Analyst — '{task_description[:100]}...'")

    try:
        analyst = _get_analyst()
        result = analyst(task_description)
        response = str(result)
        logger.info(f"Supervisor: Analyst returned {len(response)} chars")
        return response
    except Exception as e:
        error_msg = f"Analyst agent failed: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"status": "error", "agent": "Analyst", "message": error_msg})


@tool
def deploy_sentinel(task_description: str) -> str:
    """
    Deploy the Sentinel agent to red-team an intelligence report.
    The Sentinel checks for hallucinations, misinformation, and safety violations.

    THIS MUST BE DEPLOYED before any report is delivered to the user as "verified."

    Args:
        task_description: The full Analyst report to red-team, along with any
            specific concerns to investigate. Always include the complete report.
            Example: "Red-team the following intelligence report: [full report].
            Pay special attention to the confidence scores and source citations."

    Returns:
        The Sentinel's red-team assessment including verdict (PASS/FAIL) and issues found.
    """
    logger.info(f"Supervisor: Deploying Sentinel — '{task_description[:100]}...'")

    try:
        sentinel = _get_sentinel()
        result = sentinel(task_description)
        response = str(result)
        logger.info(f"Supervisor: Sentinel returned {len(response)} chars")
        return response
    except Exception as e:
        error_msg = f"Sentinel agent failed: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"status": "error", "agent": "Sentinel", "message": error_msg})


@tool
def generate_mission_id() -> str:
    """
    Generate a unique mission ID for the current operation.
    Format: mission-YYYY-MM-DD-HHMMSS

    Returns:
        A unique mission ID string.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    mission_id = f"mission-{ts}"
    logger.info(f"Supervisor: Generated mission ID: {mission_id}")
    return mission_id


# ─── Agent Factory ─────────────────────────────────────────────────────────


def create_supervisor_agent() -> Agent:
    """
    Create and return the Supervisor agent instance.

    The Supervisor uses Amazon Nova Premier for strategic reasoning and
    uses the Agent-as-Tool pattern to delegate to Scout, Analyst, and
    Sentinel sub-agents.
    """
    model = BedrockModel(
        model_id=config.nova_premier_model_id,
        region_name=config.region,
    )

    supervisor = Agent(
        model=model,
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        tools=[deploy_scout, deploy_analyst, deploy_sentinel, generate_mission_id],
    )

    logger.info("Supervisor agent initialized with Nova Premier model — Agent-as-Tool pattern")
    return supervisor


# ─── Main Entry Point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("  AEGIS-TACTICAL — Multi-Agent Intelligence System")
    print("  Type 'exit' to quit")
    print("=" * 70)

    supervisor = create_supervisor_agent()

    while True:
        try:
            user_input = input("\n[AEGIS] Enter mission objective > ").strip()
            if user_input.lower() in ("exit", "quit", "q"):
                print("Aegis-Tactical shutting down. Stay vigilant.")
                break
            if not user_input:
                continue

            print("\n[AEGIS] Mission acknowledged. Deploying agents...\n")
            result = supervisor(user_input)
            print("\n" + "=" * 70)
            print("[AEGIS] MISSION BRIEFING:")
            print("=" * 70)
            print(result)
            print("=" * 70)

        except KeyboardInterrupt:
            print("\nAegis-Tactical interrupted. Shutting down.")
            break
        except Exception as e:
            print(f"\n[AEGIS] System error: {e}")
            logger.error(f"Supervisor execution error: {e}", exc_info=True)

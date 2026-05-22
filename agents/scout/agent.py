"""
Aegis-Tactical — Scout Agent (The Gatherer)

The Scout is a fast, lightweight intelligence collection agent powered by
Amazon Nova Lite. It uses Lambda tools to fetch data from news feeds,
RSS sources, and GitHub repositories.

Usage:
    from agents.scout.agent import create_scout_agent

    scout = create_scout_agent()
    result = scout("Gather the latest news about supply chain security threats")
"""

import json
import logging
from typing import Any

import boto3
from strands import Agent, tool
from strands.models.bedrock import BedrockModel

from agents.config import config
from agents.scout.prompts import SCOUT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, config.log_level))

# Initialize Lambda client for invoking tool functions
lambda_client = boto3.client("lambda", region_name=config.region)


# ─── Tool Definitions ──────────────────────────────────────────────────────


@tool
def fetch_news(query: str = "", max_articles: int = 10) -> str:
    """
    Fetch latest news headlines from global RSS news feeds.
    Optionally filter results by a search keyword.

    Args:
        query: Optional search keyword to filter news articles.
        max_articles: Maximum number of articles to return (default 10, max 50).

    Returns:
        JSON string with news articles including title, source, URL, snippet, and timestamp.
    """
    logger.info(f"Scout: Invoking fetch_news — query='{query}', max={max_articles}")

    payload = {
        "query": query,
        "max_articles": min(max_articles, 50),
    }

    response = lambda_client.invoke(
        FunctionName=config.fetch_news_function,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )

    result = json.loads(response["Payload"].read().decode("utf-8"))
    return json.dumps(result, indent=2)


@tool
def fetch_rss(feeds: list[str], max_entries_per_feed: int = 20) -> str:
    """
    Parse RSS or Atom feeds and extract structured entries.

    Args:
        feeds: List of RSS/Atom feed URLs to parse.
        max_entries_per_feed: Maximum entries to return per feed (default 20).

    Returns:
        JSON string with structured feed data including titles, links, descriptions, and dates.
    """
    logger.info(f"Scout: Invoking fetch_rss — {len(feeds)} feeds")

    payload = {
        "feeds": feeds,
        "max_entries_per_feed": min(max_entries_per_feed, 100),
    }

    response = lambda_client.invoke(
        FunctionName=config.fetch_rss_function,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )

    result = json.loads(response["Payload"].read().decode("utf-8"))
    return json.dumps(result, indent=2)


@tool
def fetch_github(owner: str, repo: str, actions: list[str] = None, max_results: int = 20) -> str:
    """
    Fetch recent activity from a GitHub repository including commits, events, and repo info.

    Args:
        owner: GitHub repository owner (e.g., 'aws').
        repo: GitHub repository name (e.g., 'aws-cdk').
        actions: List of data to fetch — options: 'commits', 'events', 'info'. Defaults to all.
        max_results: Maximum results per action (default 20).

    Returns:
        JSON string with repository info, recent commits, and events.
    """
    if actions is None:
        actions = ["commits", "events", "info"]

    logger.info(f"Scout: Invoking fetch_github — {owner}/{repo}, actions={actions}")

    payload = {
        "owner": owner,
        "repo": repo,
        "actions": actions,
        "max_results": min(max_results, 100),
    }

    response = lambda_client.invoke(
        FunctionName=config.fetch_github_function,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )

    result = json.loads(response["Payload"].read().decode("utf-8"))
    return json.dumps(result, indent=2)


# ─── Agent Factory ─────────────────────────────────────────────────────────


def create_scout_agent() -> Agent:
    """
    Create and return the Scout agent instance.

    The Scout uses Amazon Nova Lite for fast, cost-effective intelligence
    gathering. It has access to three tools: fetch_news, fetch_rss, and
    fetch_github.
    """
    model = BedrockModel(
        model_id=config.nova_lite_model_id,
        region_name=config.region,
    )

    scout = Agent(
        model=model,
        system_prompt=SCOUT_SYSTEM_PROMPT,
        tools=[fetch_news, fetch_rss, fetch_github],
    )

    logger.info("Scout agent initialized with Nova Lite model")
    return scout


# ─── Standalone Execution ──────────────────────────────────────────────────

if __name__ == "__main__":
    scout = create_scout_agent()
    result = scout("Gather the latest cybersecurity news and check the aws/aws-cdk GitHub repo for recent activity")
    print(result)

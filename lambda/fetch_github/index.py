"""
Aegis-Tactical — fetch_github Lambda
Fetches recent commits, events, and repository activity from the GitHub REST API.
Returns structured JSON with commit data and repository metadata.
"""

import json
import os
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "20"))


def github_request(path: str) -> dict | list | None:
    """Make an authenticated (or anonymous) request to GitHub API."""
    url = f"{GITHUB_API_BASE}{path}"
    headers = {
        "User-Agent": "AegisTactical/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        logger.error(f"GitHub API error for {url}: {e.code} {e.reason}")
        return None
    except Exception as e:
        logger.error(f"Failed to call GitHub API {url}: {e}")
        return None


def fetch_commits(owner: str, repo: str, max_count: int) -> list[dict[str, str]]:
    """Fetch recent commits from a GitHub repository."""
    data = github_request(f"/repos/{owner}/{repo}/commits?per_page={max_count}")
    if not data or not isinstance(data, list):
        return []
    
    commits = []
    for item in data[:max_count]:
        commit_data = item.get("commit", {})
        author_data = commit_data.get("author", {})
        commits.append({
            "sha": item.get("sha", "")[:7],
            "message": commit_data.get("message", "").split("\n")[0],  # First line only
            "author": author_data.get("name", "unknown"),
            "date": author_data.get("date", ""),
            "url": item.get("html_url", ""),
        })
    
    return commits


def fetch_events(owner: str, repo: str, max_count: int) -> list[dict[str, str]]:
    """Fetch recent events (pushes, PRs, issues) from a GitHub repository."""
    data = github_request(f"/repos/{owner}/{repo}/events?per_page={max_count}")
    if not data or not isinstance(data, list):
        return []
    
    events = []
    for item in data[:max_count]:
        events.append({
            "type": item.get("type", ""),
            "actor": item.get("actor", {}).get("login", "unknown"),
            "created_at": item.get("created_at", ""),
            "payload_action": item.get("payload", {}).get("action", ""),
        })
    
    return events


def fetch_repo_info(owner: str, repo: str) -> dict[str, Any]:
    """Fetch repository metadata."""
    data = github_request(f"/repos/{owner}/{repo}")
    if not data or not isinstance(data, dict):
        return {}
    
    return {
        "full_name": data.get("full_name", ""),
        "description": data.get("description", ""),
        "language": data.get("language", ""),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "last_pushed": data.get("pushed_at", ""),
        "default_branch": data.get("default_branch", "main"),
        "topics": data.get("topics", []),
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler for fetching GitHub activity.
    
    Input event:
    {
        "owner": "aws",
        "repo": "aws-cdk",
        "actions": ["commits", "events", "info"],
        "max_results": 20
    }
    """
    logger.info(f"fetch_github invoked with event: {json.dumps(event)}")
    
    owner = event.get("owner", "")
    repo = event.get("repo", "")
    
    if not owner or not repo:
        return {
            "status": "error",
            "message": "Both 'owner' and 'repo' are required. Example: owner='aws', repo='aws-cdk'",
        }
    
    actions = event.get("actions", ["commits", "info"])
    max_results = min(event.get("max_results", MAX_RESULTS), 100)
    
    result: dict[str, Any] = {
        "status": "success",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "repository": f"{owner}/{repo}",
    }
    
    if "info" in actions:
        result["repo_info"] = fetch_repo_info(owner, repo)
    
    if "commits" in actions:
        result["recent_commits"] = fetch_commits(owner, repo, max_results)
    
    if "events" in actions:
        result["recent_events"] = fetch_events(owner, repo, max_results)
    
    logger.info(f"fetch_github returning data for {owner}/{repo}")
    return result

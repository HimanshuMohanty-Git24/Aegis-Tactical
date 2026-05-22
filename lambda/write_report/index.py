"""
Aegis-Tactical - write_report Lambda
Writes structured analysis reports to S3 as timestamped Markdown files.
Used by the Analyst and Sentinel stages to persist their findings.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REPORT_BUCKET = os.environ.get("REPORT_BUCKET", "")
REPORT_PREFIX = os.environ.get("REPORT_PREFIX", "reports/")

s3_client = boto3.client("s3")

YES_NO_PREFIXES = ("is ", "are ", "was ", "were ", "do ", "does ", "did ", "can ", "will ", "has ", "have ")

OPEN_POSITIVE_TERMS = {
    "open", "opened", "reopen", "reopened", "operational", "resumed", "accessible", "passage",
}
OPEN_NEGATIVE_TERMS = {
    "closed", "blocked", "blockade", "attacked", "attack", "fired", "threat", "uncertain", "risk",
    "disrupt", "disrupted", "control",
}


def _source_trust_score(source: str) -> float:
    source_lower = source.lower()
    if "reuters" in source_lower:
        return 0.95
    if "bbc" in source_lower:
        return 0.90
    if "nyt" in source_lower or "new york times" in source_lower:
        return 0.88
    if "associated press" in source_lower or "ap " in source_lower:
        return 0.87
    return 0.70


def _contains_term(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return bool(re.search(rf"\b{re.escape(term)}\b", text))


def _extract_objective(report: dict[str, Any]) -> str:
    objective = str(report.get("objective", "")).strip()
    if objective:
        return objective

    summary = str(report.get("summary", ""))
    marker = "objective:"
    idx = summary.lower().find(marker)
    if idx >= 0:
        return summary[idx + len(marker):].strip().rstrip(".")
    return ""


def _extract_scout_payload(report: dict[str, Any]) -> dict[str, Any]:
    payload = report.get("scout_payload")
    if isinstance(payload, dict):
        return payload

    findings = report.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            description = finding.get("description")
            if not isinstance(description, str):
                continue
            candidate = description.strip()
            if not candidate.startswith("{"):
                continue
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get("articles"), list):
                return parsed

    return {"status": "unknown", "articles": [], "total_results": 0}


def _normalize_articles(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw_articles = payload.get("articles", [])
    if not isinstance(raw_articles, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in raw_articles:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "title": str(item.get("title", "")).strip(),
                "source": str(item.get("source", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "snippet": str(item.get("snippet", "")).strip(),
                "published_at": str(item.get("published_at", "")).strip(),
            }
        )
    return normalized


def _is_yes_no_question(objective: str) -> bool:
    return objective.strip().lower().startswith(YES_NO_PREFIXES)


def _evaluate_objective(objective: str, articles: list[dict[str, str]]) -> dict[str, Any]:
    objective_lower = objective.lower().strip()
    yes_no = _is_yes_no_question(objective)

    positive_hits = 0
    negative_hits = 0

    for article in articles:
        text = f"{article.get('title', '')} {article.get('snippet', '')}".lower()
        positive = any(_contains_term(text, term) for term in OPEN_POSITIVE_TERMS)
        negative = any(_contains_term(text, term) for term in OPEN_NEGATIVE_TERMS)
        if positive:
            positive_hits += 1
        if negative:
            negative_hits += 1

    contradiction = positive_hits > 0 and negative_hits > 0
    article_count = len(articles)
    unique_sources = len({a.get("source", "") for a in articles if a.get("source")})

    if article_count > 0:
        avg_trust = sum(_source_trust_score(a.get("source", "")) for a in articles) / article_count
    else:
        avg_trust = 0.0

    if article_count == 0:
        confidence = 0.20
    else:
        volume_factor = min(article_count / 10.0, 1.0)
        diversity_factor = min(unique_sources / 5.0, 1.0)
        confidence = 0.35 + (0.30 * avg_trust) + (0.20 * volume_factor) + (0.15 * diversity_factor)
        if contradiction:
            confidence -= 0.12
        confidence = max(0.20, min(0.95, confidence))
    confidence = round(confidence, 2)

    if article_count >= 8 and unique_sources >= 3 and avg_trust >= 0.80:
        evidence_quality = "HIGH"
    elif article_count >= 4 and unique_sources >= 2:
        evidence_quality = "MEDIUM"
    else:
        evidence_quality = "LOW"

    if article_count == 0:
        analyst_verdict = "INSUFFICIENT_EVIDENCE"
    elif contradiction and abs(positive_hits - negative_hits) <= 1:
        analyst_verdict = "DISPUTED"
    elif confidence >= 0.72:
        analyst_verdict = "SUPPORTED"
    elif confidence >= 0.50:
        analyst_verdict = "PARTIALLY_SUPPORTED"
    else:
        analyst_verdict = "LOW_CONFIDENCE"

    if article_count == 0:
        direct_answer = "Insufficient current evidence to answer confidently."
    elif yes_no:
        if contradiction and abs(positive_hits - negative_hits) <= 1:
            direct_answer = "Disputed: sources conflict, so the answer is not stable yet."
        elif positive_hits > negative_hits:
            direct_answer = "Likely yes, but the operating environment remains volatile."
        else:
            direct_answer = "Likely no, based on available coverage and risk indicators."
    else:
        direct_answer = (
            f"Observed {article_count} relevant articles across {unique_sources} sources; "
            f"evidence quality is {evidence_quality}."
        )

    verified = confidence >= 0.65 and unique_sources >= 2 and article_count >= 3 and not (
        contradiction and abs(positive_hits - negative_hits) <= 1
    )

    if article_count == 0:
        suggested_sentinel_verdict = "CRITICAL_FAIL"
        hallucination_risk = "HIGH"
        misinformation_flags = 1
    elif analyst_verdict == "SUPPORTED" and confidence >= 0.72 and not contradiction:
        suggested_sentinel_verdict = "PASS"
        hallucination_risk = "LOW"
        misinformation_flags = 0
    elif confidence >= 0.50:
        suggested_sentinel_verdict = "CONDITIONAL_PASS"
        hallucination_risk = "MEDIUM"
        misinformation_flags = 1 if contradiction else 0
    else:
        suggested_sentinel_verdict = "CRITICAL_FAIL"
        hallucination_risk = "HIGH"
        misinformation_flags = 2

    recommendations: list[str] = []
    if article_count == 0:
        recommendations.append("Expand source coverage and rerun with a broader objective keyword set.")
    if contradiction:
        recommendations.append("Treat the claim as unstable until multiple trusted sources converge.")
    if not verified:
        recommendations.append("Require human analyst review before operational decisions.")
    if confidence < 0.65:
        recommendations.append("Schedule a follow-up mission in 30-60 minutes for updated evidence.")
    if not recommendations:
        recommendations.append("Continue monitoring for changes and refresh the mission on material updates.")

    return {
        "objective": objective,
        "article_count": article_count,
        "unique_sources": unique_sources,
        "average_source_trust": round(avg_trust, 2),
        "positive_hits": positive_hits,
        "negative_hits": negative_hits,
        "contradiction": contradiction,
        "confidence_score": confidence,
        "evidence_quality": evidence_quality,
        "analyst_verdict": analyst_verdict,
        "direct_answer": direct_answer,
        "verified": verified,
        "suggested_sentinel_verdict": suggested_sentinel_verdict,
        "hallucination_risk": hallucination_risk,
        "misinformation_flags": misinformation_flags,
        "recommendations": recommendations,
    }


def _enrich_analyst_report(report: dict[str, Any]) -> dict[str, Any]:
    objective = _extract_objective(report)
    scout_payload = _extract_scout_payload(report)
    articles = _normalize_articles(scout_payload)
    analysis = _evaluate_objective(objective, articles)

    report["objective"] = analysis["objective"]
    report["scout_payload"] = scout_payload
    report["confidence_score"] = analysis["confidence_score"]
    report["analyst_verdict"] = analysis["analyst_verdict"]
    report["direct_answer"] = analysis["direct_answer"]
    report["evidence_quality"] = analysis["evidence_quality"]
    report["supporting_metrics"] = {
        "articles_reviewed": analysis["article_count"],
        "unique_sources": analysis["unique_sources"],
        "average_source_trust": analysis["average_source_trust"],
        "contradiction_detected": analysis["contradiction"],
        "positive_signal_hits": analysis["positive_hits"],
        "negative_signal_hits": analysis["negative_hits"],
    }
    report["suggested_sentinel_verdict"] = analysis["suggested_sentinel_verdict"]
    report["hallucination_risk"] = analysis["hallucination_risk"]
    report["misinformation_flags"] = analysis["misinformation_flags"]
    report["recommendations"] = analysis["recommendations"]

    findings = report.get("findings")
    if isinstance(findings, list) and findings:
        primary = findings[0]
        if isinstance(primary, dict):
            primary["verified"] = analysis["verified"]
            if analysis["article_count"] == 0:
                primary["severity"] = "HIGH"
            elif analysis["contradiction"]:
                primary["severity"] = "MEDIUM"
            elif analysis["confidence_score"] >= 0.72:
                primary["severity"] = "LOW"
            else:
                primary["severity"] = "MEDIUM"
    else:
        report["findings"] = [
            {
                "title": "Evidence Assessment",
                "severity": "MEDIUM",
                "source": "Analyst Agent",
                "verified": analysis["verified"],
                "description": json.dumps(
                    {
                        "objective": analysis["objective"],
                        "articles_reviewed": analysis["article_count"],
                        "unique_sources": analysis["unique_sources"],
                        "direct_answer": analysis["direct_answer"],
                        "analyst_verdict": analysis["analyst_verdict"],
                    }
                ),
            }
        ]

    summary_prefix = "Objective assessment"
    report["summary"] = (
        f"{summary_prefix}: {analysis['objective']}. "
        f"Reviewed {analysis['article_count']} articles across {analysis['unique_sources']} sources."
    )

    return report


def _enrich_sentinel_response(report: dict[str, Any]) -> dict[str, Any]:
    red_team = report.get("red_team_assessment", {})
    if not isinstance(red_team, dict):
        red_team = {}

    verdict = str(red_team.get("verdict", report.get("suggested_sentinel_verdict", "CONDITIONAL_PASS")))
    report["suggested_sentinel_verdict"] = verdict
    report["hallucination_risk"] = str(red_team.get("hallucination_risk", report.get("hallucination_risk", "MEDIUM")))
    report["misinformation_flags"] = int(red_team.get("misinformation_flags", report.get("misinformation_flags", 0)))

    if "confidence_score" not in report:
        report["confidence_score"] = 0.90

    return report


def generate_report_markdown(report: dict[str, Any]) -> str:
    """Convert a structured report dict into a formatted Markdown document."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    md_lines = [
        "# Aegis-Tactical Intelligence Report",
        "",
        f"**Generated:** {timestamp}",
        f"**Mission ID:** {report.get('mission_id', 'N/A')}",
        f"**Agent:** {report.get('agent', 'Unknown')}",
        f"**Classification:** {report.get('classification', 'UNCLASSIFIED')}",
        f"**Confidence Score:** {report.get('confidence_score', 'N/A')}",
        f"**Analyst Verdict:** {report.get('analyst_verdict', 'N/A')}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        f"{report.get('summary', 'No summary provided.')}",
        "",
    ]

    direct_answer = report.get("direct_answer")
    if direct_answer:
        md_lines.extend(
            [
                "---",
                "",
                "## Direct Answer",
                "",
                f"**Answer:** {direct_answer}",
                f"**Evidence Quality:** {report.get('evidence_quality', 'N/A')}",
                f"**Sentinel Route:** {report.get('suggested_sentinel_verdict', 'N/A')}",
                "",
            ]
        )

    supporting_metrics = report.get("supporting_metrics")
    if isinstance(supporting_metrics, dict) and supporting_metrics:
        md_lines.extend(
            [
                "---",
                "",
                "## Evidence Metrics",
                "",
                f"- **Articles Reviewed:** {supporting_metrics.get('articles_reviewed', 0)}",
                f"- **Unique Sources:** {supporting_metrics.get('unique_sources', 0)}",
                f"- **Average Source Trust:** {supporting_metrics.get('average_source_trust', 0)}",
                f"- **Contradiction Detected:** {supporting_metrics.get('contradiction_detected', False)}",
                "",
            ]
        )

    md_lines.extend(["---", "", "## Detailed Findings", ""])

    findings = report.get("findings", [])
    if isinstance(findings, list) and findings:
        for i, finding in enumerate(findings, 1):
            if not isinstance(finding, dict):
                continue
            md_lines.append(f"### Finding {i}: {finding.get('title', 'Untitled')}")
            md_lines.append("")
            md_lines.append(f"- **Severity:** {finding.get('severity', 'Unknown')}")
            md_lines.append(f"- **Source:** {finding.get('source', 'N/A')}")
            md_lines.append(f"- **Verified:** {'Yes' if finding.get('verified') else 'No'}")
            md_lines.append("")
            md_lines.append(f"{finding.get('description', 'No description.')}")
            md_lines.append("")
    else:
        md_lines.append("No specific findings to report.")
        md_lines.append("")

    red_team = report.get("red_team_assessment")
    if isinstance(red_team, dict) and red_team:
        md_lines.extend(
            [
                "---",
                "",
                "## Red-Team Assessment",
                "",
                f"**Overall Verdict:** {red_team.get('verdict', 'N/A')}",
                f"**Hallucination Risk:** {red_team.get('hallucination_risk', report.get('hallucination_risk', 'N/A'))}",
                f"**Misinformation Flags:** {red_team.get('misinformation_flags', report.get('misinformation_flags', 0))}",
                "",
                f"{red_team.get('notes', '')}",
                "",
            ]
        )

    recommendations = report.get("recommendations", [])
    if isinstance(recommendations, list) and recommendations:
        md_lines.extend(["---", "", "## Recommendations", ""])
        for rec in recommendations:
            md_lines.append(f"- {rec}")
        md_lines.append("")

    md_lines.extend(["---", "", "*Report generated by Aegis-Tactical Intelligence System*"])
    return "\n".join(md_lines)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for writing reports to S3."""
    logger.info("write_report invoked with event keys: %s", list(event.keys()))

    if not REPORT_BUCKET:
        return {
            "status": "error",
            "message": "REPORT_BUCKET environment variable not set.",
        }

    report = dict(event)
    mission_id = report.get("mission_id", f"mission-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}")
    report["mission_id"] = mission_id

    agent_name = str(report.get("agent", "")).strip().lower()
    if agent_name == "analyst":
        report = _enrich_analyst_report(report)
    elif agent_name == "sentinel":
        report = _enrich_sentinel_response(report)

    report_markdown = generate_report_markdown(report)

    timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    filename = f"{mission_id}.md"
    s3_key = f"{REPORT_PREFIX}{timestamp}/{filename}"

    try:
        s3_client.put_object(
            Bucket=REPORT_BUCKET,
            Key=s3_key,
            Body=report_markdown.encode("utf-8"),
            ContentType="text/markdown",
            Metadata={
                "mission-id": mission_id,
                "agent": str(report.get("agent", "unknown")),
                "classification": str(report.get("classification", "UNCLASSIFIED")),
                "confidence-score": str(report.get("confidence_score", "")),
            },
        )
        logger.info("Report written to s3://%s/%s", REPORT_BUCKET, s3_key)
    except Exception as exc:
        logger.error("Failed to write report to S3: %s", exc)
        return {
            "status": "error",
            "message": f"Failed to write report: {str(exc)}",
        }

    json_key = s3_key.replace(".md", ".json")
    try:
        s3_client.put_object(
            Bucket=REPORT_BUCKET,
            Key=json_key,
            Body=json.dumps(report, indent=2, default=str).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception as exc:
        logger.warning("Failed to write JSON report: %s", exc)

    return {
        "status": "success",
        "mission_id": mission_id,
        "report_location": f"s3://{REPORT_BUCKET}/{s3_key}",
        "json_location": f"s3://{REPORT_BUCKET}/{json_key}",
        "report_size_bytes": len(report_markdown.encode("utf-8")),
        "written_at": datetime.now(timezone.utc).isoformat(),
        "direct_answer": report.get("direct_answer"),
        "analyst_verdict": report.get("analyst_verdict"),
        "confidence_score": report.get("confidence_score"),
        "evidence_quality": report.get("evidence_quality"),
        "suggested_sentinel_verdict": report.get("suggested_sentinel_verdict"),
        "hallucination_risk": report.get("hallucination_risk"),
        "misinformation_flags": report.get("misinformation_flags"),
        "recommendations": report.get("recommendations", []),
        "red_team_assessment": report.get("red_team_assessment", {}),
    }

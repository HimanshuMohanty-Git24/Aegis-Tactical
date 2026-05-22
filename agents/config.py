"""
Aegis-Tactical — Shared Configuration
Loads configuration from environment variables or SSM Parameter Store.
"""

import os
from dataclasses import dataclass, field


@dataclass
class AegisConfig:
    """Central configuration for all Aegis-Tactical agents."""

    # AWS Region
    region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", "us-east-1"))

    # ── Model IDs ──────────────────────────────────────────────────────
    # Amazon Nova Premier — high reasoning (Supervisor, Analyst, Sentinel)
    nova_premier_model_id: str = field(
        default_factory=lambda: os.environ.get(
            "NOVA_PREMIER_MODEL_ID",
            "us.amazon.nova-premier-v1:0"
        )
    )

    # Amazon Nova Lite — speed/cost optimized (Scout)
    nova_lite_model_id: str = field(
        default_factory=lambda: os.environ.get(
            "NOVA_LITE_MODEL_ID",
            "us.amazon.nova-lite-v1:0"
        )
    )

    # ── Knowledge Base ─────────────────────────────────────────────────
    knowledge_base_id: str = field(
        default_factory=lambda: os.environ.get("KNOWLEDGE_BASE_ID", "")
    )

    # ── S3 ─────────────────────────────────────────────────────────────
    ground_truth_bucket: str = field(
        default_factory=lambda: os.environ.get("GROUND_TRUTH_BUCKET", "")
    )
    report_prefix: str = field(
        default_factory=lambda: os.environ.get("REPORT_PREFIX", "reports/")
    )

    # ── Lambda Function Names ──────────────────────────────────────────
    fetch_news_function: str = field(
        default_factory=lambda: os.environ.get("FETCH_NEWS_FUNCTION", "aegis-fetch-news")
    )
    fetch_rss_function: str = field(
        default_factory=lambda: os.environ.get("FETCH_RSS_FUNCTION", "aegis-fetch-rss")
    )
    fetch_github_function: str = field(
        default_factory=lambda: os.environ.get("FETCH_GITHUB_FUNCTION", "aegis-fetch-github")
    )
    write_report_function: str = field(
        default_factory=lambda: os.environ.get("WRITE_REPORT_FUNCTION", "aegis-write-report")
    )

    # ── Guardrails ─────────────────────────────────────────────────────
    guardrail_id: str = field(
        default_factory=lambda: os.environ.get("GUARDRAIL_ID", "")
    )
    guardrail_version: str = field(
        default_factory=lambda: os.environ.get("GUARDRAIL_VERSION", "DRAFT")
    )

    # ── Operational Settings ───────────────────────────────────────────
    max_iterations: int = field(
        default_factory=lambda: int(os.environ.get("MAX_ITERATIONS", "10"))
    )
    confidence_threshold: float = field(
        default_factory=lambda: float(os.environ.get("CONFIDENCE_THRESHOLD", "0.7"))
    )
    log_level: str = field(
        default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO")
    )


# Singleton configuration instance
config = AegisConfig()

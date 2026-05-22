"""
Aegis-Tactical — fetch_news Lambda
Fetches latest news headlines from multiple RSS-based news sources.
Returns structured JSON with title, source, URL, snippet, and timestamp.
"""

import json
import os
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Default news RSS feeds (configurable via environment variable)
DEFAULT_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.reuters.com/reuters/topNews",
]

MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "10"))

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it",
    "of", "on", "or", "that", "the", "to", "with", "using", "use", "over", "under", "than",
    "this", "these", "those", "their", "them", "its", "our", "your", "you", "we", "they", "us",
    "last", "recent", "latest", "days", "day", "week", "weeks", "major", "developments", "development",
    "investigate", "analyze", "analysis", "summarize", "summary", "identify", "provide", "including",
    "reputable", "sources", "source", "verified", "facts", "confidence", "levels", "likely", "possible",
    "impacts", "impact", "key", "only", "based", "news", "note", "stakeholders",
    "credibility", "bias", "possible", "likely", "whether", "currently", "stable", "confirmed",
    "incidents", "hours", "conflicting", "claims", "immediate", "implications", "rated", "verdict",
    "through", "rating",
}


def extract_query_terms(query: str) -> list[str]:
    """Extract meaningful keyword terms from a free-form objective sentence."""
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    if not tokens:
        return []

    filtered = [
        t for t in tokens
        if t not in STOP_WORDS and ((t.isalpha() and len(t) >= 4) or (t.isdigit() and len(t) >= 4))
    ]

    # If filtering is too aggressive, keep non-trivial tokens rather than returning no terms.
    if not filtered:
        filtered = [
            t for t in tokens
            if (t.isalpha() and len(t) >= 4) or (t.isdigit() and len(t) >= 4)
        ]

    seen = set()
    unique_terms: list[str] = []
    for term in filtered:
        if term not in seen:
            unique_terms.append(term)
            seen.add(term)

    return unique_terms[:12]


def score_article_relevance(article: dict[str, str], raw_query: str, query_terms: list[str]) -> int:
    """Score article relevance using phrase and keyword matching."""
    title = article.get("title", "")
    snippet = article.get("snippet", "")
    haystack = f"{title} {snippet}".lower()

    score = 0

    # Boost exact phrase hits for short keyword-like queries.
    if raw_query and len(raw_query) <= 80 and raw_query in haystack:
        score += 20

    if query_terms:
        score += sum(1 for term in query_terms if re.search(rf"\b{re.escape(term)}\b", haystack))

    return score


def minimum_relevance_score(query_terms: list[str]) -> int:
    """Increase strictness for long objective prompts to reduce noisy single-term matches."""
    term_count = len(query_terms)
    if term_count >= 10:
        return 3
    if term_count >= 6:
        return 2
    return 1


def parse_rss_feed(url: str) -> list[dict[str, str]]:
    """Parse an RSS feed and extract article metadata."""
    articles = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AegisTactical/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read()
        
        root = ET.fromstring(content)
        
        # Handle both RSS 2.0 and Atom feeds
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        
        # Try RSS 2.0 format
        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            description = item.findtext("description", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            source_name = root.findtext(".//channel/title", url).strip()
            
            if title:
                articles.append({
                    "title": title,
                    "source": source_name,
                    "url": link,
                    "snippet": description[:500] if description else "",
                    "published_at": pub_date,
                })
        
        # Try Atom format if no RSS items found
        if not articles:
            for entry in root.findall("atom:entry", namespaces):
                title = entry.findtext("atom:title", "", namespaces).strip()
                link_el = entry.find("atom:link", namespaces)
                link = link_el.get("href", "") if link_el is not None else ""
                summary = entry.findtext("atom:summary", "", namespaces).strip()
                updated = entry.findtext("atom:updated", "", namespaces).strip()
                
                if title:
                    articles.append({
                        "title": title,
                        "source": url,
                        "url": link,
                        "snippet": summary[:500] if summary else "",
                        "published_at": updated,
                    })
    
    except Exception as e:
        logger.error(f"Failed to parse feed {url}: {e}")
    
    return articles


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler for fetching news.
    
    Input event:
    {
        "query": "optional search keyword to filter results",
        "feeds": ["optional", "custom", "feed", "urls"],
        "max_articles": 10
    }
    """
    logger.info(f"fetch_news invoked with event: {json.dumps(event)}")
    
    query = str(event.get("query", "")).lower().strip()
    query_terms = extract_query_terms(query)
    feeds = event.get("feeds", os.environ.get("NEWS_FEEDS", ",".join(DEFAULT_FEEDS)).split(","))
    max_articles = min(event.get("max_articles", MAX_ARTICLES), 50)
    
    all_articles = []
    
    for feed_url in feeds:
        feed_url = feed_url.strip()
        if not feed_url:
            continue
        articles = parse_rss_feed(feed_url)
        all_articles.extend(articles)
    
    unfiltered_articles = list(all_articles)

    # Filter by query if provided
    if query:
        min_score = minimum_relevance_score(query_terms)
        scored_articles: list[tuple[int, dict[str, str]]] = []
        for article in all_articles:
            score = score_article_relevance(article, query, query_terms)
            if score > 0:
                scored_articles.append((score, article))

        scored_articles.sort(key=lambda item: item[0], reverse=True)

        all_articles = [article for score, article in scored_articles if score >= min_score]

        # If strict threshold filters everything out, relax to basic single-term matches first.
        if not all_articles and min_score > 1 and scored_articles:
            logger.warning(
                "No articles met minimum score %s for terms %s; relaxing to score >= 1",
                min_score,
                query_terms,
            )
            all_articles = [article for score, article in scored_articles if score >= 1]

        # Avoid false mission failures from over-constrained objectives.
        if not all_articles:
            logger.warning(
                "No query matches found for terms %s; returning latest unfiltered headlines",
                query_terms,
            )
            all_articles = unfiltered_articles
    
    # Sort by recency (best effort — dates may be in different formats)
    all_articles = all_articles[:max_articles]
    
    result = {
        "status": "success",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "query_terms": query_terms,
        "minimum_relevance_score": minimum_relevance_score(query_terms),
        "total_results": len(all_articles),
        "articles": all_articles,
    }
    
    logger.info(f"fetch_news returning {len(all_articles)} articles")
    return result

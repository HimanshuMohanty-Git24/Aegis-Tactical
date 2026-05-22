"""
Aegis-Tactical — fetch_rss Lambda
Generic RSS/Atom feed parser with configurable feed URLs.
Returns the latest N entries from specified feeds.
"""

import json
import os
import logging
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_ENTRIES = int(os.environ.get("MAX_ENTRIES", "20"))


def parse_feed(url: str) -> dict[str, Any]:
    """Parse an RSS or Atom feed and return structured data."""
    entries = []
    feed_title = url
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AegisTactical/1.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read()
        
        root = ET.fromstring(content)
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        
        # ── RSS 2.0 ──
        channel = root.find(".//channel")
        if channel is not None:
            feed_title = channel.findtext("title", url).strip()
            feed_description = channel.findtext("description", "").strip()
            
            for item in root.findall(".//item"):
                entry = {
                    "title": item.findtext("title", "").strip(),
                    "link": item.findtext("link", "").strip(),
                    "description": item.findtext("description", "").strip()[:1000],
                    "published": item.findtext("pubDate", "").strip(),
                    "author": item.findtext("author", "").strip() or item.findtext("dc:creator", "").strip(),
                    "categories": [
                        cat.text.strip()
                        for cat in item.findall("category")
                        if cat.text
                    ],
                }
                entries.append(entry)
        
        # ── Atom ──
        if not entries:
            feed_title_el = root.find("atom:title", namespaces)
            if feed_title_el is not None and feed_title_el.text:
                feed_title = feed_title_el.text.strip()
            
            for entry_el in root.findall("atom:entry", namespaces):
                link_el = entry_el.find("atom:link", namespaces)
                entry = {
                    "title": entry_el.findtext("atom:title", "", namespaces).strip(),
                    "link": link_el.get("href", "") if link_el is not None else "",
                    "description": entry_el.findtext("atom:summary", "", namespaces).strip()[:1000],
                    "published": entry_el.findtext("atom:updated", "", namespaces).strip(),
                    "author": entry_el.findtext("atom:author/atom:name", "", namespaces).strip(),
                    "categories": [
                        cat.get("term", "")
                        for cat in entry_el.findall("atom:category", namespaces)
                    ],
                }
                entries.append(entry)
    
    except Exception as e:
        logger.error(f"Failed to fetch/parse feed {url}: {e}")
        return {
            "feed_url": url,
            "feed_title": feed_title,
            "error": str(e),
            "entries": [],
        }
    
    return {
        "feed_url": url,
        "feed_title": feed_title,
        "entry_count": len(entries),
        "entries": entries,
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler for parsing RSS/Atom feeds.
    
    Input event:
    {
        "feeds": ["https://example.com/feed.xml", "https://other.com/rss"],
        "max_entries_per_feed": 20
    }
    """
    logger.info(f"fetch_rss invoked with event: {json.dumps(event)}")
    
    feeds = event.get("feeds", [])
    if isinstance(feeds, str):
        feeds = [feeds]
    
    max_entries = min(event.get("max_entries_per_feed", MAX_ENTRIES), 100)
    
    if not feeds:
        return {
            "status": "error",
            "message": "No feed URLs provided. Pass a 'feeds' array in the event.",
        }
    
    results = []
    for feed_url in feeds:
        feed_url = feed_url.strip()
        if not feed_url:
            continue
        
        feed_data = parse_feed(feed_url)
        # Limit entries per feed
        if "entries" in feed_data:
            feed_data["entries"] = feed_data["entries"][:max_entries]
            feed_data["entry_count"] = len(feed_data["entries"])
        results.append(feed_data)
    
    return {
        "status": "success",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "feeds_processed": len(results),
        "results": results,
    }

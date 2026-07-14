"""News gathering via Google News RSS (free, keyless).

Per holding: direct-mention query. Per sector: one shared query. Plus one
query per macro asset. Articles are deduped by normalized title and trimmed
to a bounded snippet so downstream LLM calls stay small.
"""

import hashlib
import html
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

import feedparser

from .config import Config

RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

MACRO_QUERIES = {
    "Gold": "gold price futures",
    "Silver": "silver price futures",
    "10Y Treasury yield": "treasury yields bond market",
    "Bitcoin": "bitcoin price",
}


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def _fetch_feed(query: str, max_items: int, max_age_hours: int, snippet_chars: int) -> list[dict[str, Any]]:
    url = RSS_URL.format(query=quote_plus(query))
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    items = []
    for entry in feed.entries[: max_items * 3]:
        published = None
        if getattr(entry, "published_parsed", None):
            published = datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=timezone.utc)
        if published and published < cutoff:
            continue
        title = _strip_html(entry.get("title", ""))
        if not title:
            continue
        items.append({
            "title": title[:200],
            "snippet": _strip_html(entry.get("summary", ""))[:snippet_chars],
            "source": (entry.get("source") or {}).get("title", ""),
            "link": entry.get("link", ""),
            "published": published.isoformat() if published else None,
        })
        if len(items) >= max_items:
            break
    return items


def _dedupe(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for a in articles:
        key = hashlib.sha1(re.sub(r"\W+", "", a["title"].lower()).encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            a["id"] = key[:12]
            out.append(a)
    return out


def collect_news(cfg: Config) -> dict[str, Any]:
    n = cfg["news"]
    fetch = lambda q: _fetch_feed(q, n["max_per_query"], n["max_age_hours"], n["snippet_chars"])

    per_ticker: dict[str, list] = {}
    for h in cfg.holdings:
        arts = fetch(f'"{h.company}" OR "{h.ticker} stock"')
        per_ticker[h.ticker] = _dedupe(arts)
        print(f"  {h.ticker}: {len(per_ticker[h.ticker])} articles")

    per_sector: dict[str, list] = {}
    for sector in cfg.sectors:
        per_sector[sector] = _dedupe(fetch(f"{sector} sector stocks news"))
        print(f"  sector {sector}: {len(per_sector[sector])} articles")

    macro: dict[str, list] = {}
    for asset in cfg["macro_assets"]:
        q = MACRO_QUERIES.get(asset["name"], asset["name"])
        macro[asset["name"]] = _dedupe(fetch(q))
        print(f"  macro {asset['name']}: {len(macro[asset['name']])} articles")

    market_wide = _dedupe(fetch("stock market today major moves"))

    return {
        "per_ticker": per_ticker,
        "per_sector": per_sector,
        "macro": macro,
        "market_wide": market_wide,
    }

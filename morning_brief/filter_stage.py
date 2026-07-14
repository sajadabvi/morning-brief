"""Stage: council-filter every gathered article down to material ones."""

from typing import Any

from .config import Config
from .llm import council_filter
from .news import MACRO_QUERIES


def filter_all(cfg: Config, news: dict[str, Any]) -> dict[str, Any]:
    max_keep = int(cfg["news"]["max_articles_per_ticker"])

    per_ticker = {}
    for h in cfg.holdings:
        subject = f"{h.company} ({h.ticker})"
        arts = news["per_ticker"].get(h.ticker, [])
        kept = council_filter(cfg, subject, arts)[:max_keep]
        per_ticker[h.ticker] = kept
        print(f"  {h.ticker}: {len(kept)}/{len(arts)} material")

    per_sector = {}
    for sector, arts in news["per_sector"].items():
        subject = f"the {sector} sector"
        kept = council_filter(cfg, subject, arts)[:max_keep]
        per_sector[sector] = kept
        print(f"  sector {sector}: {len(kept)}/{len(arts)} material")

    macro = {}
    for name, arts in news["macro"].items():
        kept = council_filter(cfg, name, arts)[:max_keep]
        macro[name] = kept
        print(f"  macro {name}: {len(kept)}/{len(arts)} material")

    market_wide = council_filter(cfg, "the overall stock market", news["market_wide"])[:max_keep]
    print(f"  market-wide: {len(market_wide)}/{len(news['market_wide'])} material")

    return {
        "per_ticker": per_ticker,
        "per_sector": per_sector,
        "macro": macro,
        "market_wide": market_wide,
    }

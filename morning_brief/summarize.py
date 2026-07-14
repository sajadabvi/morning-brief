"""Stage: per-ticker and per-macro briefs.

Each brief is written from a bounded slice (price line + up to N filtered
articles), so writer-model context stays small regardless of news volume.
The digest stage later sees ONLY these briefs, never raw articles - that is
the aggregation step that keeps the final compose call bounded too.
"""

from typing import Any

from .config import Config
from .llm import ollama_chat

BRIEF_PROMPT = """Write a brief for a morning portfolio digest about {subject}.

Price action: {price_line}

Material news (already filtered for importance):
{articles}

Rules:
- 2-4 sentences, max 90 words, plain factual prose.
- Lead with what matters most today.
- No advice, no filler like "investors should watch".
- If there is genuinely nothing notable, reply exactly: NOTHING NOTABLE

Brief:"""


def _articles_block(articles: list[dict[str, Any]]) -> str:
    if not articles:
        return "(none)"
    return "\n".join(
        f"- [{a['importance']}/5] {a['title']} ({a.get('source','')}) - {a['why']}"
        for a in articles
    )


def _price_line_stock(q: dict[str, Any] | None) -> str:
    if not q:
        return "no quote available"
    flag = " (SIGNIFICANT)" if q["significant"] else ""
    return f"{q['pct_change']:+.2f}% vs prev close, last {q['last']}{flag}"


def price_line_macro(q: dict[str, Any]) -> str:
    if "bp_change" in q:
        flag = " (SIGNIFICANT)" if q["significant"] else ""
        return f"{q['bp_change']:+.1f}bp, now {q['last']:.2f}%{flag}"
    return _price_line_stock(q)


def summarize_all(cfg: Config, market: dict[str, Any], filtered: dict[str, Any]) -> dict[str, Any]:
    writer = cfg["llm"]["writer_model"]

    def write(subject: str, price_line: str, articles: list) -> str:
        prompt = BRIEF_PROMPT.format(
            subject=subject, price_line=price_line, articles=_articles_block(articles)
        )
        try:
            text = ollama_chat(cfg, writer, prompt).strip()
        except Exception as e:
            print(f"  writer failed for {subject}: {e}")
            text = "NOTHING NOTABLE"
        return "" if "NOTHING NOTABLE" in text.upper() else text

    tickers = {}
    for h in cfg.holdings:
        sector_news = filtered["per_sector"].get(h.sector, [])
        articles = filtered["per_ticker"].get(h.ticker, []) + sector_news[:3]
        brief = write(
            f"{h.company} ({h.ticker})",
            _price_line_stock(market["stocks"].get(h.ticker)),
            articles,
        )
        tickers[h.ticker] = brief
        print(f"  {h.ticker}: {'brief written' if brief else 'nothing notable'}")

    macro = {}
    for q in market["macro"]:
        brief = write(q["name"], price_line_macro(q), filtered["macro"].get(q["name"], []))
        macro[q["name"]] = brief
        print(f"  {q['name']}: {'brief written' if brief else 'nothing notable'}")

    return {"tickers": tickers, "macro": macro}

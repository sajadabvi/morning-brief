"""Stage: compose the digest email.

Sections are assembled deterministically from stage outputs; only the
headline and closing paragraphs use the writer model, and its input is the
already-bounded set of significant items and briefs - never raw articles.
"""

from datetime import date
from typing import Any

from .config import Config
from .llm import ollama_chat
from .summarize import price_line_macro

HEADLINE_PROMPT = """You write the opening paragraph of a morning portfolio digest email.

Today's significant items (everything else was filtered out as noise):
{items}

Write ONE short paragraph (max 60 words) with only the most important
takeaways. Plain prose, no greetings, no advice. If the list is empty, say
it's a quiet morning for the portfolio.

Paragraph:"""

CLOSING_PROMPT = """You write the closing "digest" paragraph of a morning portfolio email,
summarizing the same headline-level takeaways in one compact paragraph
(max 50 words). Plain prose, no sign-off.

Headline items:
{items}

Paragraph:"""


def _significant_items(cfg: Config, market: dict, summaries: dict) -> list[str]:
    items = []
    for h in cfg.holdings:
        q = market["stocks"].get(h.ticker)
        if q and q["significant"]:
            items.append(f"{h.ticker} moved {q['pct_change']:+.2f}%")
    for q in market["macro"]:
        if q["significant"]:
            move = f"{q['bp_change']:+.1f}bp" if "bp_change" in q else f"{q['pct_change']:+.2f}%"
            items.append(f"{q['name']} moved {move}")
    # Highest-importance news brief lines (first sentence only, bounded)
    for ticker, brief in summaries["tickers"].items():
        if brief:
            items.append(f"{ticker}: {brief.split('. ')[0][:140]}")
    for name, brief in summaries["macro"].items():
        if brief:
            items.append(f"{name}: {brief.split('. ')[0][:140]}")
    return items[:12]


def _write_para(cfg: Config, prompt_tpl: str, items: list[str]) -> str:
    block = "\n".join(f"- {i}" for i in items) or "(none)"
    try:
        return ollama_chat(cfg, cfg["llm"]["writer_model"], prompt_tpl.format(items=block)).strip()
    except Exception as e:
        print(f"  paragraph writer failed: {e}")
        return "Quiet morning: no items cleared the significance bar." if not items else \
            "Key items this morning: " + "; ".join(items[:4]) + "."


def compose_daily(cfg: Config, market: dict, summaries: dict, events_written: list) -> dict[str, str]:
    items = _significant_items(cfg, market, summaries)
    headline = _write_para(cfg, HEADLINE_PROMPT, items)
    closing = _write_para(cfg, CLOSING_PROMPT, items)

    lines: list[str] = [headline, ""]

    lines.append("== Significant futures/price moves - portfolio ==")
    sig = [
        f"  {h.ticker} ({h.company}): {market['stocks'][h.ticker]['pct_change']:+.2f}% "
        f"(last {market['stocks'][h.ticker]['last']:,.2f})"
        for h in cfg.holdings
        if h.ticker in market["stocks"] and market["stocks"][h.ticker]["significant"]
    ]
    lines += sig or ["  none"]

    for label, names in [
        ("gold/silver", ["Gold", "Silver"]),
        ("bond market", ["10Y Treasury yield"]),
        ("Bitcoin", ["Bitcoin"]),
    ]:
        lines.append(f"\n== Significant {label} moves ==")
        rows = [
            f"  {q['name']}: {price_line_macro(q)}"
            for q in market["macro"]
            if q["name"] in names and q["significant"]
        ]
        lines += rows or ["  none"]
        for name in names:
            brief = summaries["macro"].get(name)
            if brief:
                lines.append(f"  {brief}")

    lines.append("\n== Portfolio news ==")
    any_news = False
    for h in cfg.holdings:
        brief = summaries["tickers"].get(h.ticker)
        if brief:
            any_news = True
            lines.append(f"\n{h.ticker} - {h.company}")
            lines.append(f"  {brief}")
    if not any_news:
        lines.append("  Nothing material across the portfolio today.")

    if events_written:
        lines.append("\n== New calendar events added ==")
        lines += [f"  {ev['date']}: {ev['title']}" for ev in events_written]

    lines += ["", "== Digest ==", closing]

    return {
        "subject": f"{cfg['email']['subject_prefix']} - {date.today():%a %b %-d}",
        "body": "\n".join(lines),
    }


def compose_weekly(cfg: Config, week_events: list[dict[str, str]]) -> dict[str, str]:
    lines = ["Upcoming scheduled events for the portfolio this week:", ""]
    if week_events:
        lines += [f"  {ev['date']}: {ev['title']}" for ev in week_events]
    else:
        lines.append("  No scheduled events found for the coming week.")
    return {
        "subject": f"{cfg['email']['subject_prefix']} - Week ahead ({date.today():%b %-d})",
        "body": "\n".join(lines),
    }

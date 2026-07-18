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


def compose_daily(
    cfg: Config,
    market: dict,
    summaries: dict,
    events_written: list,
    filtered: dict | None = None,
    today_events: list | None = None,
) -> dict[str, str]:
    items = _significant_items(cfg, market, summaries)
    headline = _write_para(cfg, HEADLINE_PROMPT, items)
    closing = _write_para(cfg, CLOSING_PROMPT, items)

    movers = sorted(
        (
            (h, market["stocks"][h.ticker])
            for h in cfg.holdings
            if h.ticker in market["stocks"] and market["stocks"][h.ticker]["significant"]
        ),
        key=lambda hq: -abs(hq[1]["pct_change"]),
    )
    subject = f"{cfg['email']['subject_prefix']} - {date.today():%a %b %-d}"
    if movers:
        subject += ": " + ", ".join(
            f"{h.ticker} {q['pct_change']:+.1f}%" for h, q in movers[:3]
        )

    lines: list[str] = [headline, ""]

    lines.append("== Significant moves - portfolio ==")
    sig = [
        f"  {h.ticker} ({h.company}): {q['pct_change']:+.2f}% "
        f"({q.get('basis', 'last session')}, last {q['last']:,.2f})"
        for h, q in movers
    ]
    lines += sig or ["  none"]

    macro_sig_rows: list[str] = []
    for label, names in [
        ("Gold & silver", ["Gold", "Silver"]),
        ("Bond market", ["10Y Treasury yield"]),
        ("Bitcoin", ["Bitcoin"]),
    ]:
        rows = [
            f"  {q['name']}: {price_line_macro(q)}"
            for q in market["macro"]
            if q["name"] in names and q["significant"]
        ]
        macro_sig_rows += rows
        briefs = [summaries["macro"].get(n) for n in names]
        briefs = [b for b in briefs if b]
        if not rows and not briefs:
            continue
        lines.append(f"\n== {label} ==")
        lines += rows
        lines += [f"  {b}" for b in briefs]

    # Portfolio news, most important first: significant movers by size of
    # move, then by the council's highest article importance, then CSV order.
    def _rank(h) -> tuple:
        q = market["stocks"].get(h.ticker)
        move = abs(q["pct_change"]) if q and q["significant"] else 0.0
        imp = max(
            (a.get("importance", 0) for a in (filtered or {}).get("per_ticker", {}).get(h.ticker, [])),
            default=0,
        )
        return (-move, -imp)

    lines.append("\n== Portfolio news ==")
    newsworthy = [h for h in cfg.holdings if summaries["tickers"].get(h.ticker)]
    for h in sorted(newsworthy, key=_rank):
        lines.append(f"\n{h.ticker} - {h.company}")
        lines.append(f"  {summaries['tickers'][h.ticker]}")
    if not newsworthy:
        lines.append("  Nothing material across the portfolio today.")

    sectors = summaries.get("sectors") or {}
    if sectors:
        lines.append("\n== Sector notes ==")
        for sector, brief in sectors.items():
            lines.append(f"\n{sector}")
            lines.append(f"  {brief}")

    if events_written:
        lines.append("\n== New calendar events added ==")
        lines += [f"  {ev['date']}: {ev['title']}" for ev in events_written]

    today_lines = [f"  {ev['title']}" for ev in (today_events or [])]
    if today_lines:
        lines.append("\n== Today ==")
        lines += today_lines

    lines += ["", "== Digest ==", closing]

    # Short form for Telegram: headline, moves, today, closing - no briefs.
    # (send_telegram prepends the subject line.)
    tg = [headline, ""]
    if sig:
        tg += ["Portfolio movers:"] + sig
    if macro_sig_rows:
        tg += ["Macro movers:"] + macro_sig_rows
    if today_lines:
        tg += ["Today:"] + today_lines
    tg += ["", closing]

    return {
        "subject": subject,
        "body": "\n".join(lines),
        "telegram": "\n".join(tg),
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

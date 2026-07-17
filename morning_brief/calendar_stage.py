"""Stage: extract scheduled events per ticker and write them to macOS Calendar.

Structured source first: yfinance earnings dates. The small local model then
normalizes/extends them (per spec) from recent filtered headlines - one tiny
prompt per ticker. Events are written via AppleScript into the configured
calendar (the synced Google calendar) as all-day events, deduped by the
config marker + title + date against events already in the calendar.
"""

import json
import subprocess
import time
from datetime import date, datetime, timedelta
from typing import Any

import yfinance as yf

from .config import Config
from .llm import ollama_chat, _parse_json

EXTRACT_PROMPT = """Company: {company} ({ticker})

Known upcoming dates from the earnings data feed:
{known}

Recent material headlines:
{headlines}

List this company's key SCHEDULED public events in the next {horizon} days:
earnings calls, quarterly/annual report releases, investor days, product
launch events, shareholder meetings. Only include events with a specific
date you are confident about (from the feed data or explicitly stated in a
headline). Do not guess dates.

Answer with ONLY a JSON object:
{{"events": [{{"date": "YYYY-MM-DD", "title": "<short title>"}}]}}"""


def _yf_earnings_dates(ticker: str, horizon_days: int) -> list[dict[str, str]]:
    try:
        df = yf.Ticker(ticker).get_earnings_dates(limit=8)
        if df is None or df.empty:
            return []
        out = []
        today = date.today()
        limit = today + timedelta(days=horizon_days)
        for ts in df.index:
            d = ts.date()
            if today <= d <= limit:
                out.append({"date": d.isoformat(), "title": "Earnings"})
        return out
    except Exception as e:
        print(f"  earnings dates failed for {ticker}: {e}")
        return []


def extract_events(cfg: Config, filtered: dict[str, Any]) -> list[dict[str, str]]:
    horizon = int(cfg["calendar"]["horizon_days"])
    model = cfg["llm"]["extract_model"]
    events: list[dict[str, str]] = []
    today = date.today()
    limit = today + timedelta(days=horizon)

    for h in cfg.holdings:
        known = _yf_earnings_dates(h.ticker, horizon)
        if known:
            # Structured feed dates are authoritative; skip the LLM call.
            candidates = known
        else:
            headlines = "\n".join(
                f"- {a['title']}" for a in filtered["per_ticker"].get(h.ticker, [])[:6]
            ) or "(none)"
            prompt = EXTRACT_PROMPT.format(
                company=h.company,
                ticker=h.ticker,
                known="(none)",
                headlines=headlines,
                horizon=horizon,
            )
            parsed = None
            try:
                parsed = _parse_json(ollama_chat(cfg, model, prompt))
            except Exception as e:
                print(f"  extract failed for {h.ticker}: {e}")
            candidates = (parsed or {}).get("events", [])

        for ev in candidates:
            try:
                d = date.fromisoformat(str(ev["date"]).strip()[:10])
            except (ValueError, KeyError):
                continue
            if not (today <= d <= limit):
                continue
            title = str(ev.get("title", "Event")).strip()[:60]
            events.append({
                "ticker": h.ticker,
                "date": d.isoformat(),
                "title": f"{h.ticker}: {title}",
            })
        print(f"  {h.ticker}: {len([e for e in events if e['ticker'] == h.ticker])} events")

    # Dedupe within this run
    seen = set()
    unique = []
    for ev in sorted(events, key=lambda e: e["date"]):
        key = (ev["date"], ev["title"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    return unique


def _ensure_calendar_running() -> None:
    # AppleScript's `launch` fails for Calendar.app with error -600 on
    # recent macOS; `open -g` (background, no focus steal) works reliably.
    subprocess.run(["open", "-ga", "Calendar"], check=False, timeout=30)
    time.sleep(4)


def _osascript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def existing_events(cfg: Config) -> list[tuple[str, str]]:
    """(date, title) of our marker-tagged events already in the calendar."""
    cal = cfg["calendar"]["name"]
    marker = cfg["calendar"]["marker"]
    horizon = int(cfg["calendar"]["horizon_days"])
    _ensure_calendar_running()
    script = f'''
    set output to ""
    tell application "Calendar"
        tell calendar "{cal}"
            set theEvents to (every event whose summary begins with "{marker}" and start date is greater than (current date) - 1 * days and start date is less than (current date) + {horizon} * days)
            repeat with ev in theEvents
                set d to start date of ev
                set output to output & (year of d) & "-" & (month of d as integer) & "-" & (day of d) & "|" & summary of ev & "\\n"
            end repeat
        end tell
    end tell
    return output
    '''
    keys = []
    try:
        for line in _osascript(script).splitlines():
            if "|" not in line:
                continue
            dpart, title = line.split("|", 1)
            y, m, d = (int(x) for x in dpart.split("-"))
            keys.append((date(y, m, d).isoformat(), title.strip()))
    except Exception as e:
        print(f"  reading existing events failed: {e}")
    return keys


def write_events(cfg: Config, events: list[dict[str, str]]) -> list[dict[str, str]]:
    cal = cfg["calendar"]["name"]
    marker = cfg["calendar"]["marker"]
    existing = {(d, t.lower()) for d, t in existing_events(cfg)}
    written = []
    for ev in events:
        full_title = f"{marker} {ev['title']}"
        if (ev["date"], full_title.lower()) in existing:
            continue
        d = datetime.fromisoformat(ev["date"])
        script = f'''
        set eventDate to current date
        set year of eventDate to {d.year}
        set month of eventDate to {d.month}
        set day of eventDate to {d.day}
        set time of eventDate to 0
        tell application "Calendar"
            tell calendar "{cal}"
                make new event with properties {{summary:"{full_title}", start date:eventDate, end date:eventDate + 1 * days, allday event:true}}
            end tell
        end tell
        '''
        try:
            _osascript(script)
            written.append(ev)
            print(f"  wrote: {ev['date']} {full_title}")
        except Exception as e:
            print(f"  calendar write failed for {ev['title']}: {e}")
    return written


def upcoming_week_events(cfg: Config) -> list[dict[str, str]]:
    """Marker-tagged events in the next 7 days (for the Monday weekly email)."""
    week = []
    limit = (date.today() + timedelta(days=7)).isoformat()
    today = date.today().isoformat()
    for d, title in sorted(existing_events(cfg)):
        if today <= d <= limit:
            week.append({"date": d, "title": title})
    return week

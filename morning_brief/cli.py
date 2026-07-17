"""Morning Brief CLI.

Commands:
  daily    Full weekday pipeline (skips itself when the market is closed).
  weekly   Monday week-ahead calendar email.
  status   Show today's checkpoint progress.

Each pipeline stage checkpoints to state/runs/<date>/<stage>.json; re-running
`daily` after a crash resumes from the first incomplete stage. `--fresh`
discards today's checkpoints. `--no-email` runs everything but the send
(useful for testing). `--force` runs even when the market is closed.
"""

import argparse
import sys
from datetime import date

import pandas_market_calendars as mcal

from .config import load_config
from .state import RunState, run_stage
from . import market, news, filter_stage, summarize, calendar_stage, digest, emailer


def market_open_today(tz: str) -> bool:
    nyse = mcal.get_calendar("NYSE")
    today = date.today()
    sched = nyse.schedule(start_date=today, end_date=today)
    return not sched.empty


def cmd_daily(args) -> int:
    cfg = load_config()
    if not args.force and not market_open_today(cfg["timezone"]):
        print("Market closed today (weekend/holiday); nothing to do.")
        return 0

    state = RunState(cfg.state_dir, date.today(), cfg.get("keep_runs", 14))
    if args.fresh:
        state.clear()

    market_data = run_stage(state, "1-market", lambda: market.collect_market_data(cfg))
    raw_news = run_stage(state, "2-news", lambda: news.collect_news(cfg))
    filtered = run_stage(state, "3-filter", lambda: filter_stage.filter_all(cfg, raw_news))
    briefs = run_stage(state, "4-summarize", lambda: summarize.summarize_all(cfg, market_data, filtered))
    events = run_stage(state, "5-calendar", lambda: calendar_stage.write_events(
        cfg, calendar_stage.extract_events(cfg, filtered)))
    mail = run_stage(state, "6-digest", lambda: digest.compose_daily(cfg, market_data, briefs, events))

    if args.no_email:
        print("\n--- email preview ---\n" + mail["subject"] + "\n\n" + mail["body"])
        return 0

    run_stage(state, "7-email", lambda: (emailer.send_email(cfg, mail["subject"], mail["body"]), {"sent": True})[1])
    return 0


def cmd_send_pending(args) -> int:
    """Safety net: if today's digest was composed but never emailed, send it.

    Runs as a separate scheduled job after the main pipeline so a transient
    Mail failure (or a crash between compose and send) still results in the
    email going out, exactly once - the 7-email checkpoint guards resends.
    """
    cfg = load_config()
    state = RunState(cfg.state_dir, date.today(), cfg.get("keep_runs", 14))
    if state.has("7-email"):
        print("Already sent today; nothing to do.")
        return 0
    if not state.has("6-digest"):
        print("No composed digest for today (pipeline not finished or not run).")
        return 0
    mail = state.load("6-digest")
    emailer.send_email(cfg, mail["subject"], mail["body"])
    state.save("7-email", {"sent": True, "via": "send-pending"})
    return 0


def cmd_weekly(args) -> int:
    cfg = load_config()
    week = calendar_stage.upcoming_week_events(cfg)
    mail = digest.compose_weekly(cfg, week)
    if args.no_email:
        print(mail["subject"] + "\n\n" + mail["body"])
        return 0
    emailer.send_email(cfg, mail["subject"], mail["body"])
    return 0


def cmd_status(args) -> int:
    cfg = load_config()
    state = RunState(cfg.state_dir, date.today(), cfg.get("keep_runs", 14))
    stages = ["1-market", "2-news", "3-filter", "4-summarize", "5-calendar", "6-digest", "7-email"]
    for s in stages:
        print(f"  {'done   ' if state.has(s) else 'pending'}  {s}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="morning-brief")
    sub = parser.add_subparsers(dest="command", required=True)

    p_daily = sub.add_parser("daily", help="run the full daily pipeline")
    p_daily.add_argument("--fresh", action="store_true", help="discard today's checkpoints first")
    p_daily.add_argument("--no-email", action="store_true", help="print the email instead of sending")
    p_daily.add_argument("--force", action="store_true", help="run even if market is closed")
    p_daily.set_defaults(fn=cmd_daily)

    p_weekly = sub.add_parser("weekly", help="send the Monday week-ahead email")
    p_weekly.add_argument("--no-email", action="store_true")
    p_weekly.set_defaults(fn=cmd_weekly)

    sub.add_parser(
        "send-pending", help="send today's digest if composed but not yet emailed"
    ).set_defaults(fn=cmd_send_pending)

    sub.add_parser("status", help="show today's stage progress").set_defaults(fn=cmd_status)

    args = parser.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()

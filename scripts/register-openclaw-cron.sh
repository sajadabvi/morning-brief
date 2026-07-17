#!/bin/bash
# Register the Morning Brief schedule with OpenClaw's cron.
#
# Daily pipeline: 4:15 AM ET Mon-Fri, started DETACHED (the run takes 2-4h;
# the agent turn only kicks it off) with output logged to state/cron-daily.log.
# The pipeline exits immediately on market holidays.
# Send safety net: 7:45 AM ET Mon-Fri - if the digest was composed but the
# email didn't go out (crash, Mail hiccup), sends it; no-op otherwise.
# Weekly week-ahead email: 7:50 AM ET on Mondays.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TZ_NAME="America/New_York"

openclaw cron add \
  --name "Morning Brief daily" \
  --cron "15 4 * * 1-5" \
  --tz "$TZ_NAME" \
  --session isolated \
  --best-effort-deliver \
  --message "Start the Morning Brief daily pipeline DETACHED and report immediately. Execute exactly this command; it prints 'started' and returns at once (the pipeline runs on its own and logs to state/cron-daily.log): cd $REPO && (PYTHONUNBUFFERED=1 nohup uv run morning-brief daily >> state/cron-daily.log 2>&1 &) && echo started. Report only whether the command printed 'started'."

openclaw cron add \
  --name "Morning Brief send safety net" \
  --cron "45 7 * * 1-5" \
  --tz "$TZ_NAME" \
  --session isolated \
  --best-effort-deliver \
  --message "Run the Morning Brief send safety net. Execute exactly this command and report its output: cd $REPO && PYTHONUNBUFFERED=1 uv run morning-brief send-pending 2>&1 | tee -a state/cron-daily.log"

openclaw cron add \
  --name "Morning Brief weekly calendar" \
  --cron "50 7 * * 1" \
  --tz "$TZ_NAME" \
  --session isolated \
  --best-effort-deliver \
  --message "Send the Morning Brief week-ahead email. Execute this exact command and report only whether it succeeded: cd $REPO && uv run morning-brief weekly"

echo "Registered. Current jobs:"
openclaw cron list

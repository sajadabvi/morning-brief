#!/bin/bash
# Register the Morning Brief schedule with OpenClaw's cron.
# Daily research pipeline: 6:15 AM ET, Mon-Fri (finishes well before the 8:00 send;
# the pipeline itself exits immediately on market holidays).
# Weekly week-ahead email: 7:50 AM ET on Mondays.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TZ_NAME="America/New_York"

openclaw cron add \
  --name "Morning Brief daily" \
  --cron "15 6 * * 1-5" \
  --tz "$TZ_NAME" \
  --session isolated \
  --message "Run the Morning Brief daily pipeline. Execute this exact command and report only whether it succeeded: cd $REPO && uv run morning-brief daily"

openclaw cron add \
  --name "Morning Brief weekly calendar" \
  --cron "50 7 * * 1" \
  --tz "$TZ_NAME" \
  --session isolated \
  --message "Send the Morning Brief week-ahead email. Execute this exact command and report only whether it succeeded: cd $REPO && uv run morning-brief weekly"

echo "Registered. Current jobs:"
openclaw cron list

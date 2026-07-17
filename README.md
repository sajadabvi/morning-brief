# Morning Brief

Automated weekday portfolio research digest, fully on-device:

- **Market data** (yfinance, keyless): portfolio quotes plus Gold, Silver, the
  10Y Treasury yield, and Bitcoin, with configurable significant-move thresholds.
- **News** (Google News RSS, keyless): per-stock direct mentions, sector news,
  macro-asset news, and market-wide headlines.
- **Local LLM council filtering**: every article is judged twice — triaged by a
  small local model (gemma4) and confirmed by a large one (qwen3.5) via Ollama.
  Only unanimous "material" verdicts survive. Signal, not volume.
- **Calendar**: earnings/report dates per holding (yfinance + small-model
  extraction) written as all-day events to the synced Google calendar in
  macOS Calendar, deduped by a `[MB]` title marker.
- **Email**: digest sent through the Gmail account already signed into
  Mail.app — no credentials stored anywhere.

## Schedule (via OpenClaw cron)

| Job | When | What |
|---|---|---|
| Daily digest | 4:15 AM ET Mon–Fri | Full pipeline → email, started detached, logs to `state/cron-daily.log`. Exits immediately on market holidays (NYSE calendar). |
| Send safety net | 7:45 AM ET Mon–Fri | `send-pending`: if the digest was composed but the email failed, resend; the 7-email checkpoint guarantees exactly-once. |
| Week ahead | 7:50 AM ET Mondays | Emails the coming week's calendar events for all holdings. |

Register both jobs: `./scripts/register-openclaw-cron.sh`

## Usage

```bash
uv sync                                # install
uv run morning-brief daily --no-email  # dry run, prints the email
uv run morning-brief daily             # full run incl. send
uv run morning-brief weekly            # Monday week-ahead email
uv run morning-brief status            # today's stage progress
```

`portfolio.csv` (ticker, company, sector) is the source of truth for what gets
tracked — copy `portfolio.csv.example` to get started. It is gitignored so
real holdings never leave the machine. Thresholds, models, calendar/email
targets all live in `config.yaml`.

## Architecture: bounded context by construction

The pipeline is 7 checkpointed stages; each stage's LLM calls see a small,
fixed-size slice — the design never puts "everything" in one prompt, so it
cannot outgrow the local models' context window no matter how much news a
day brings:

```
1-market     quotes + significance flags          (no LLM)
2-news       RSS fetch, dedupe, snippet-trim      (no LLM)
3-filter     council: small-model triage PER      (~500 chars/call, then one
             ARTICLE + large-model batch verdict   bounded batch call/subject)
4-summarize  brief PER TICKER/ASSET, skipped      (≤8 filtered articles/call)
             when quiet
5-calendar   event extraction PER TICKER          (feed dates + 6 headlines/call)
6-digest     headline/closing from briefs only    (never sees raw articles)
7-email      Mail.app AppleScript send            (no LLM)
```

Every stage writes `state/runs/<date>/<stage>.json` on success. A crash,
reboot, or Ollama hiccup mid-run resumes from the first incomplete stage —
no redone work, no re-spent LLM time. Old runs are pruned (keep_runs: 14).
Failures degrade gracefully: a failed quote/feed/judgment drops that one
item, never the run.

## Requirements

- macOS with Ollama running (`qwen3.5:122b`, `gemma4:latest`)
- Mail.app signed in; Calendar.app with the target calendar
- First run: macOS will prompt to allow automation of Calendar and Mail — approve both
- The Mac must be awake at run time (System Settings → Energy, or
  `sudo pmset repeat wakeorpoweron MTWRF 06:10:00`)

"""Send email through Mail.app via AppleScript.

Uses the account already signed in on this Mac - no credentials on disk.
Mail.app is pre-opened with `open -g` (AppleScript `launch` is unreliable
for some apps when they are not running, and `open` proved reliable for
Calendar), and the send is retried because early-morning cold starts and
account sync can make the first attempt slow or flaky.
"""

import subprocess
import time

from .config import Config

ATTEMPTS = 3
RETRY_WAIT = 30
OSA_TIMEOUT = 300


def _attempt_send(script: str) -> None:
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=OSA_TIMEOUT
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"osascript exit {result.returncode}")


def send_email(cfg: Config, subject: str, body: str) -> None:
    to = cfg["email"]["to"]
    recipients = [to] if isinstance(to, str) else list(to)
    # AppleScript string literals: escape backslashes and quotes
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    recipient_lines = "\n            ".join(
        f'make new to recipient at end of to recipients with properties {{address:"{esc(r)}"}}'
        for r in recipients
    )
    script = f'''
    tell application "Mail"
        set msg to make new outgoing message with properties {{subject:"{esc(subject)}", content:"{esc(body)}", visible:false}}
        tell msg
            {recipient_lines}
        end tell
        send msg
    end tell
    '''
    last_err: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        subprocess.run(["open", "-ga", "Mail"], check=False, timeout=30)
        time.sleep(5)
        try:
            _attempt_send(script)
            print(f"  email sent to {', '.join(recipients)}: {subject}")
            return
        except Exception as e:
            last_err = e
            print(f"  send attempt {attempt}/{ATTEMPTS} failed: {e}")
            if attempt < ATTEMPTS:
                time.sleep(RETRY_WAIT)
    raise RuntimeError(f"Mail send failed after {ATTEMPTS} attempts: {last_err}")

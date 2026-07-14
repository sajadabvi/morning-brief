"""Send email through Mail.app via AppleScript.

Uses the account already signed in on this Mac - no credentials on disk.
Mail.app must be configured (it is) and the Mac awake at send time.
"""

import subprocess

from .config import Config


def send_email(cfg: Config, subject: str, body: str) -> None:
    to = cfg["email"]["to"]
    # AppleScript string literals: escape backslashes and quotes
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    tell application "Mail" to launch
    delay 3
    tell application "Mail"
        set msg to make new outgoing message with properties {{subject:"{esc(subject)}", content:"{esc(body)}", visible:false}}
        tell msg
            make new to recipient at end of to recipients with properties {{address:"{esc(to)}"}}
        end tell
        send msg
    end tell
    '''
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Mail send failed: {result.stderr.strip()}")
    print(f"  email sent to {to}: {subject}")

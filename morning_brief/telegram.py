"""Deliver the digest to Telegram via the OpenClaw CLI.

Best-effort by design: Telegram is a convenience copy, so failures are
logged but never fail the pipeline - email remains the primary channel.
Long digests are split at line boundaries to fit Telegram's message limit.
"""

import subprocess

from .config import Config

CHUNK_LIMIT = 3900  # Telegram cap is 4096; leave headroom


def _chunks(text: str) -> list[str]:
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > CHUNK_LIMIT and current:
            parts.append(current)
            current = ""
        current += line
    if current:
        parts.append(current)
    return parts


def send_telegram(cfg: Config, subject: str, body: str) -> bool:
    tg = cfg.get("telegram") or {}
    if not tg.get("enabled"):
        return False
    target = str(tg["target"])
    ok = True
    for i, chunk in enumerate(_chunks(f"{subject}\n\n{body}")):
        try:
            result = subprocess.run(
                ["openclaw", "message", "send", "--channel", "telegram",
                 "--target", target, "-m", chunk],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip()[:200])
        except Exception as e:
            print(f"  telegram chunk {i + 1} failed: {e}")
            ok = False
    if ok:
        print(f"  telegram delivered to {target}")
    return ok

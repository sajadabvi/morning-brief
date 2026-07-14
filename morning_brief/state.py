"""Per-run state store: one directory per run date, one JSON checkpoint per stage.

A stage that already has a checkpoint is skipped on re-run, so a crash or
restart resumes where it left off instead of redoing work (and re-spending
LLM time). `morning-brief daily --fresh` clears today's state first.
"""

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any


class RunState:
    def __init__(self, state_dir: Path, run_date: date, keep_runs: int = 14):
        self.dir = state_dir / "runs" / run_date.isoformat()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._prune(state_dir / "runs", keep_runs)

    def _prune(self, runs_dir: Path, keep: int) -> None:
        runs = sorted(d for d in runs_dir.iterdir() if d.is_dir())
        for old in runs[:-keep]:
            shutil.rmtree(old, ignore_errors=True)

    def path(self, stage: str) -> Path:
        return self.dir / f"{stage}.json"

    def has(self, stage: str) -> bool:
        return self.path(stage).exists()

    def load(self, stage: str) -> Any:
        return json.loads(self.path(stage).read_text())

    def save(self, stage: str, data: Any) -> Any:
        tmp = self.path(stage).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, default=str))
        tmp.rename(self.path(stage))
        return data

    def clear(self) -> None:
        for f in self.dir.glob("*.json"):
            f.unlink()


def run_stage(state: RunState, stage: str, fn):
    """Execute a stage with checkpointing: skip if already done, save on success."""
    if state.has(stage):
        print(f"[{stage}] checkpoint exists, skipping")
        return state.load(stage)
    print(f"[{stage}] running...")
    result = fn()
    state.save(stage, result)
    print(f"[{stage}] done")
    return result

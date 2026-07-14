"""Load config.yaml and portfolio.csv."""

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Holding:
    ticker: str
    company: str
    sector: str


@dataclass
class Config:
    raw: dict[str, Any]
    holdings: list[Holding] = field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    @property
    def state_dir(self) -> Path:
        return ROOT / self.raw.get("state_dir", "state")

    @property
    def sectors(self) -> list[str]:
        seen: dict[str, None] = {}
        for h in self.holdings:
            seen.setdefault(h.sector, None)
        return list(seen)


def load_config(path: str | os.PathLike | None = None) -> Config:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    raw = yaml.safe_load(cfg_path.read_text())

    portfolio_path = ROOT / raw.get("portfolio_csv", "portfolio.csv")
    holdings = []
    with open(portfolio_path, newline="") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            holdings.append(Holding(
                ticker=ticker,
                company=(row.get("company") or ticker).strip(),
                sector=(row.get("sector") or "General").strip(),
            ))
    if not holdings:
        raise SystemExit(f"No holdings found in {portfolio_path}; add rows to portfolio.csv")

    return Config(raw=raw, holdings=holdings)

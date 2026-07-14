"""Market data via yfinance: last price vs previous close, significant-move flags."""

from typing import Any

import yfinance as yf

from .config import Config


def _quote(symbol: str) -> dict[str, Any] | None:
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        last = info.last_price
        prev = info.previous_close
        if last is None or prev in (None, 0):
            return None
        return {
            "symbol": symbol,
            "last": round(float(last), 4),
            "prev_close": round(float(prev), 4),
            "pct_change": round((float(last) - float(prev)) / float(prev) * 100, 2),
        }
    except Exception as e:
        print(f"  quote failed for {symbol}: {e}")
        return None


def collect_market_data(cfg: Config) -> dict[str, Any]:
    stock_threshold = float(cfg["thresholds"]["stock_pct"])

    stocks = {}
    for h in cfg.holdings:
        q = _quote(h.ticker)
        if q:
            q["significant"] = abs(q["pct_change"]) >= stock_threshold
            stocks[h.ticker] = q

    macro = []
    for asset in cfg["macro_assets"]:
        q = _quote(asset["symbol"])
        if not q:
            continue
        q["name"] = asset["name"]
        if asset["kind"] == "bp":
            # yfinance fast_info returns ^TNX as the yield in percent
            # (4.61 => 4.61%), so delta * 100 = basis points
            q["bp_change"] = round((q["last"] - q["prev_close"]) * 100, 1)
            q["significant"] = abs(q["bp_change"]) >= float(asset["threshold"])
        else:
            q["significant"] = abs(q["pct_change"]) >= float(asset["threshold"])
        macro.append(q)

    return {"stocks": stocks, "macro": macro}

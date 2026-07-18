"""Market data via yfinance: last price vs previous close, significant-move flags."""

from typing import Any

import yfinance as yf

from .config import Config


def _quote(symbol: str) -> dict[str, Any] | None:
    """Fast quote: last trade vs previous close (macro assets trade ~24h)."""
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


def _stock_quote(symbol: str) -> dict[str, Any] | None:
    """Equity quote that says WHICH move it reports.

    At 4-7 AM thin names have no pre-market trades, so a naive last-vs-close
    delta silently reports yesterday's session change. Use the fuller quote
    endpoint to label the basis explicitly:
      pre-market    live early trading vs yesterday's close
      intraday      regular session in progress
      after-hours   post-close trading vs today's close
      last session  no current trading; yesterday's full-session change
    """
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception as e:
        print(f"  info quote failed for {symbol}, falling back: {e}")
        info = {}

    state = info.get("marketState", "")
    reg = info.get("regularMarketPrice")
    reg_prev = info.get("regularMarketPreviousClose")
    pre = info.get("preMarketPrice")
    post = info.get("postMarketPrice")

    if state.startswith("PRE") and pre and reg_prev:
        last, base, basis = pre, reg_prev, "pre-market"
    elif state == "REGULAR" and reg and reg_prev:
        last, base, basis = reg, reg_prev, "intraday"
    elif state.startswith("POST") and post and reg:
        last, base, basis = post, reg, "after-hours"
    elif reg and reg_prev:
        last, base, basis = reg, reg_prev, "last session"
    else:
        q = _quote(symbol)
        if q:
            q["basis"] = "last session"
        return q

    return {
        "symbol": symbol,
        "last": round(float(last), 4),
        "prev_close": round(float(base), 4),
        "pct_change": round((float(last) - float(base)) / float(base) * 100, 2),
        "basis": basis,
    }


def collect_market_data(cfg: Config) -> dict[str, Any]:
    stock_threshold = float(cfg["thresholds"]["stock_pct"])

    stocks = {}
    for h in cfg.holdings:
        q = _stock_quote(h.ticker)
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

"""Fundamentals from yfinance (info + quarterly income statement), cached in SQLite for a few days."""
from __future__ import annotations

import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import yfinance as yf

from . import db

MAX_AGE_DAYS = 3
_lock = threading.Lock()


def _f(v):
    try:
        v = float(v)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _growth(cur, prev):
    cur, prev = _f(cur), _f(prev)
    if cur is None or prev is None or prev == 0:
        return None
    if prev < 0:
        return None if cur <= prev else (cur - prev) / abs(prev)   # turnaround from a loss: report only if improved
    return cur / prev - 1


def fetch(symbol: str) -> dict:
    tk = yf.Ticker(symbol)
    out: dict = {"symbol": symbol}
    try:
        info = tk.info or {}
    except Exception:  # noqa: BLE001
        info = {}
    out.update({
        "name": info.get("shortName"),
        "industry": info.get("industry"),
        "yf_sector": info.get("sector"),
        "market_cap": _f(info.get("marketCap")),
        "rev_yoy": _f(info.get("revenueGrowth")),
        "eps_yoy": _f(info.get("earningsQuarterlyGrowth")),
        "margin": _f(info.get("profitMargins")),
        "roe": _f(info.get("returnOnEquity")),
        "trailing_eps": _f(info.get("trailingEps")),
        "forward_eps": _f(info.get("forwardEps")),
        "trailing_pe": _f(info.get("trailingPE")),
        "forward_pe": _f(info.get("forwardPE")),
        "inst_pct": _f(info.get("heldPercentInstitutions")),
        "short_pct": _f(info.get("shortPercentOfFloat")),
    })
    out["fwd_eps_growth"] = _growth(out["forward_eps"], out["trailing_eps"]) if (out["trailing_eps"] or 0) > 0 else None
    # Quarterly statement: last quarters of revenue / diluted EPS -> yoy of the latest quarter, and q/q acceleration.
    try:
        q = tk.quarterly_income_stmt
        quarters = []
        if q is not None and not q.empty:
            cols = sorted(q.columns, reverse=True)[:8]
            for c in cols:
                quarters.append({
                    "period": pd.Timestamp(c).strftime("%Y-%m"),
                    "revenue": _f(q.at["Total Revenue", c]) if "Total Revenue" in q.index else None,
                    "eps": _f(q.at["Diluted EPS", c]) if "Diluted EPS" in q.index else None,
                    "net_income": _f(q.at["Net Income", c]) if "Net Income" in q.index else None,
                })
        out["quarters"] = quarters
        if len(quarters) >= 5:
            g_rev = _growth(quarters[0]["revenue"], quarters[4]["revenue"])
            g_eps = _growth(quarters[0]["eps"], quarters[4]["eps"])
            if g_rev is not None:
                out["rev_yoy"] = g_rev
            if g_eps is not None:
                out["eps_yoy"] = g_eps
            if len(quarters) >= 6:
                out["eps_yoy_prev"] = _growth(quarters[1]["eps"], quarters[5]["eps"])
                out["rev_yoy_prev"] = _growth(quarters[1]["revenue"], quarters[5]["revenue"])
        if len(quarters) >= 2:
            out["eps_qoq"] = _growth(quarters[0]["eps"], quarters[1]["eps"])
            out["rev_qoq"] = _growth(quarters[0]["revenue"], quarters[1]["revenue"])
    except Exception as e:  # noqa: BLE001
        out["quarters"] = []
        out["error"] = str(e)
    # Acceleration: latest yoy growth better than the previous quarter's yoy growth.
    if out.get("eps_yoy") is not None and out.get("eps_yoy_prev") is not None:
        out["eps_accel"] = out["eps_yoy"] > out["eps_yoy_prev"]
    try:
        cal = tk.calendar or {}
        ed = cal.get("Earnings Date")
        if ed:
            d = pd.Timestamp(ed[0] if isinstance(ed, list) else ed)
            out["next_earnings"] = d.strftime("%Y-%m-%d")
            out["days_to_earnings"] = int((d - pd.Timestamp.today().normalize()).days)
    except Exception:  # noqa: BLE001
        pass
    return out


def get(symbol: str, max_age_days: float = MAX_AGE_DAYS, refresh: bool = True) -> dict | None:
    symbol = symbol.upper()
    row = db.get_fundamentals(symbol)
    if row:
        age = (pd.Timestamp.utcnow() - pd.Timestamp(row["updated"])).total_seconds() / 86400
        if age < max_age_days or not refresh:
            return row["data"]
    if not refresh:
        return None
    try:
        data = fetch(symbol)
    except Exception as e:  # noqa: BLE001
        print("fundamentals error", symbol, e)
        return row["data"] if row else None
    db.save_fundamentals(symbol, data)
    return data


def ensure_many(symbols: list[str], progress=None, workers: int = 8) -> None:
    """Refresh stale fundamentals for many symbols in parallel."""
    stale = [s for s in symbols if get(s, refresh=False) is None]
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for _ in ex.map(lambda s: get(s), stale):
            done += 1
            if progress:
                progress(done, len(stale))

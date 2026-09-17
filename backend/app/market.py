"""Market regime: benchmark stage, breadth, and context shared by strategies."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import db, data
from .config import BENCHMARK
from .indicators import to_weekly, sma
from .strategies.weinstein import classify_stages


def benchmark_df() -> pd.DataFrame:
    return data.get_daily(BENCHMARK)


def benchmark_context(spy: pd.DataFrame) -> dict:
    if spy is None or spy.empty or len(spy) < 60:
        return {"benchmark": spy, "benchmark_stage": None, "benchmark_stage2": None}
    w = to_weekly(spy)
    w["ma30"] = sma(w["Close"], 30)
    w["slope"] = w["ma30"] / w["ma30"].shift(4) - 1
    stage = int(classify_stages(w).iloc[-1])
    return {"benchmark": spy, "benchmark_stage": stage, "benchmark_stage2": stage == 2}


def market_summary() -> dict:
    spy = benchmark_df()
    qqq = data.get_daily("QQQ")
    out = {"benchmark": BENCHMARK}
    for name, df in (("SPY", spy), ("QQQ", qqq)):
        if df.empty:
            continue
        c = df["Close"]
        s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
        e21 = c.ewm(span=21, adjust=False).mean()
        ctx = benchmark_context(df)
        last = float(c.iloc[-1])
        out[name] = {
            "close": round(last, 2),
            "chg1d": round(float(c.iloc[-1] / c.iloc[-2] - 1), 4),
            "above50": bool(last > s50.iloc[-1]),
            "above200": bool(last > s200.iloc[-1]),
            "above21ema": bool(last > e21.iloc[-1]),
            "golden": bool(s50.iloc[-1] > s200.iloc[-1]),
            "stage": ctx["benchmark_stage"],
            "off_high": round(float(1 - last / c.rolling(252).max().iloc[-1]), 4),
            "ret1m": round(float(last / c.iloc[-22] - 1), 4) if len(c) > 22 else None,
            "ret3m": round(float(last / c.iloc[-64] - 1), 4) if len(c) > 64 else None,
        }
    # Breadth from cached universe prices (only symbols already in the cache; cheap).
    out["breadth"] = breadth()
    spy_ok = out.get("SPY", {})
    if spy_ok:
        if spy_ok["above50"] and spy_ok["golden"]:
            regime = "bull"
        elif spy_ok["above200"]:
            regime = "neutral"
        else:
            regime = "bear"
        out["regime"] = regime
    return out


def breadth() -> dict:
    rs = db.get_all_rs()
    syms = list(rs.keys())
    if not syms:
        return {"count": 0}
    prices = db.load_all_prices(syms)
    n = a50 = a200 = near_high = 0
    for s, df in prices.items():
        if len(df) < 200:
            continue
        c = df["Close"]
        n += 1
        last = c.iloc[-1]
        a50 += last > c.rolling(50).mean().iloc[-1]
        a200 += last > c.rolling(200).mean().iloc[-1]
        near_high += last >= c.rolling(252).max().iloc[-1] * 0.95
    if n == 0:
        return {"count": 0}
    return {"count": n, "pct_above_50": round(a50 / n, 3), "pct_above_200": round(a200 / n, 3), "pct_near_high": round(near_high / n, 3)}

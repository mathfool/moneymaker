"""Simple event-driven backtest of a strategy's entry/exit/stop series on one symbol.

Rules (identical for every strategy so results are comparable):
  - Enter at the close of the signal bar.  One position at a time, 100% of equity.
  - Initial stop = strategy's stop level on the entry bar.  If a later bar's LOW trades through the stop,
    exit at the stop (or at the open if it gapped below).
  - Otherwise exit at the close of the first bar where the strategy's exit signal fires.
  - Optional partial: none (kept simple; the UI shows R-multiples so you can judge).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .strategies.base import Computed


def run(comp: Computed, symbol: str, lookback_days: int | None = None) -> dict:
    d = comp.df
    if lookback_days:
        d = d.tail(lookback_days)
    entry = comp.entry.reindex(d.index).fillna(False).values
    exit_ = comp.exit.reindex(d.index).fillna(False).values
    stop_s = comp.stop.reindex(d.index).values
    o, h, l, c = d["Open"].values, d["High"].values, d["Low"].values, d["Close"].values
    idx = d.index
    pt = comp.extra.get("profit_trail")
    trail = pt["series"].reindex(d.index).values if pt else None
    trades = []
    in_pos = False
    ep = st = 0.0
    ei = 0
    equity = [1.0]
    eq = 1.0
    for i in range(len(d)):
        if in_pos:
            exit_px = None
            reason = None
            if l[i] <= st:
                exit_px = min(o[i], st) if o[i] < st else st
                reason = "止损"
            elif exit_[i]:
                exit_px = c[i]
                reason = "卖出信号"
            elif trail is not None and c[i] / ep - 1 >= pt["trigger"] and np.isfinite(trail[i]) and c[i] < trail[i]:
                exit_px = c[i]
                reason = pt.get("label", "移动止盈")
            if exit_px is not None:
                ret = exit_px / ep - 1
                risk = (ep - st) / ep if ep > st else 0.05
                trades.append({
                    "entry_date": idx[ei].strftime("%Y-%m-%d"), "exit_date": idx[i].strftime("%Y-%m-%d"),
                    "entry": round(float(ep), 2), "exit": round(float(exit_px), 2), "stop": round(float(st), 2),
                    "ret": round(float(ret), 4), "r": round(float(ret / risk), 2), "bars": i - ei, "reason": reason,
                })
                eq *= 1 + ret
                in_pos = False
        if not in_pos and entry[i] and i < len(d) - 1:
            in_pos = True
            ep = c[i]
            st = stop_s[i] if np.isfinite(stop_s[i]) and stop_s[i] < ep else ep * 0.93
            ei = i
        equity.append(eq * ((c[i] / ep) if in_pos else 1.0))
    open_trade = None
    if in_pos:
        open_trade = {"entry_date": idx[ei].strftime("%Y-%m-%d"), "entry": round(float(ep), 2), "stop": round(float(st), 2),
                      "ret": round(float(c[-1] / ep - 1), 4), "bars": len(d) - 1 - ei}
    return summarize(trades, equity, d, symbol, open_trade)


def summarize(trades: list[dict], equity: list[float], d: pd.DataFrame, symbol: str, open_trade=None) -> dict:
    n = len(trades)
    rets = np.array([t["ret"] for t in trades]) if n else np.array([])
    rs = np.array([t["r"] for t in trades]) if n else np.array([])
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    eq = np.array(equity)
    dd = (eq / np.maximum.accumulate(eq) - 1).min() if len(eq) else 0.0
    bh = float(d["Close"].iloc[-1] / d["Close"].iloc[0] - 1) if len(d) > 1 else 0.0
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    return {
        "symbol": symbol,
        "start": d.index[0].strftime("%Y-%m-%d"), "end": d.index[-1].strftime("%Y-%m-%d"),
        "trades": n,
        "win_rate": round(float(len(wins) / n), 3) if n else None,
        "avg_win": round(float(wins.mean()), 4) if len(wins) else None,
        "avg_loss": round(float(losses.mean()), 4) if len(losses) else None,
        "avg_r": round(float(rs.mean()), 2) if n else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else (None if gross_win == 0 else 99.0),
        "total_return": round(float(eq[-1] - 1), 4),
        "buy_hold": round(bh, 4),
        "max_drawdown": round(float(dd), 4),
        "avg_bars": round(float(np.mean([t["bars"] for t in trades])), 1) if n else None,
        "trade_list": trades[-30:],
        "open_trade": open_trade,
        "equity": [{"time": t.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for t, v in zip(d.index, equity[1:])][-400:],
    }

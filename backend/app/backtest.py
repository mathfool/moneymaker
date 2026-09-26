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


def run(comp: Computed, symbol: str, lookback_days: int | None = None, partial: bool = False) -> dict:
    """partial=True: 涨到 2R 时卖出 1/3 并把止损提到成本价，剩余 2/3 按原规则离场。"""
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
    st0 = 0.0
    ep = st = 0.0
    ei = 0
    equity = [1.0]
    eq = 1.0
    frac = 1.0            # 仍持有的仓位比例
    realized = 0.0        # 已分批卖出部分贡献的收益（占整笔的比例）
    took_partial = False
    for i in range(len(d)):
        if in_pos:
            exit_px = None
            reason = None
            if partial and not took_partial and ep > st and c[i] >= ep + 2 * (ep - st):
                realized += (1 / 3) * (c[i] / ep - 1)
                frac = 2 / 3
                took_partial = True
                st = ep                              # 剩余仓位止损提到成本价
            if l[i] <= st:
                exit_px = min(o[i], st) if o[i] < st else st
                reason = "止损" if st < ep else "保本止损"
            elif exit_[i]:
                exit_px = c[i]
                reason = "卖出信号"
            elif trail is not None and c[i] / ep - 1 >= pt["trigger"] and np.isfinite(trail[i]) and c[i] < trail[i]:
                exit_px = c[i]
                reason = pt.get("label", "移动止盈")
            if exit_px is not None:
                ret = realized + frac * (exit_px / ep - 1)
                risk = (ep - st0) / ep if ep > st0 else 0.05
                trades.append({
                    "entry_date": idx[ei].strftime("%Y-%m-%d"), "exit_date": idx[i].strftime("%Y-%m-%d"),
                    "entry": round(float(ep), 2), "exit": round(float(exit_px), 2), "stop": round(float(st), 2),
                    "ret": round(float(ret), 4), "r": round(float(ret / risk), 2), "bars": i - ei, "reason": reason,
                    "partial": took_partial,
                })
                eq *= 1 + ret
                in_pos = False
        if not in_pos and entry[i] and i < len(d) - 1:
            in_pos = True
            ep = c[i]
            st = stop_s[i] if np.isfinite(stop_s[i]) and stop_s[i] < ep else ep * 0.93
            st0 = st
            ei = i
            frac, realized, took_partial = 1.0, 0.0, False
        equity.append(eq * ((1 + realized + frac * (c[i] / ep - 1)) if in_pos else 1.0))
    open_trade = None
    if in_pos:
        open_trade = {"entry_date": idx[ei].strftime("%Y-%m-%d"), "entry": round(float(ep), 2), "stop": round(float(st), 2),
                      "ret": round(float(realized + frac * (c[-1] / ep - 1)), 4), "bars": len(d) - 1 - ei, "partial": took_partial}
    out = summarize(trades, equity, d, symbol, open_trade)
    out["partial"] = partial
    return out


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

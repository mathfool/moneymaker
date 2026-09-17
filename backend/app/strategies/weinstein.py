"""Stan Weinstein — Stage Analysis on the weekly chart with the 30-week MA.

Stage 1 基底 / Stage 2 上升 / Stage 3 顶部 / Stage 4 下跌.
Buy: weekly close breaks above the base resistance into Stage 2 with the 30-wk MA turning up and volume expansion.
Sell: weekly close below the 30-week MA (Stage 3/4 transition).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import add_common, to_weekly, sma
from .base import Strategy, Computed, Condition, fmt

FLAT = 0.005  # +/-0.5% over 4 weeks counts as a flat 30-week MA


def classify_stages(w: pd.DataFrame) -> pd.Series:
    """State machine over weekly bars -> Stage 1..4 (0 = not enough data)."""
    ma = w["ma30"].values
    slope = w["slope"].values
    close = w["Close"].values
    stages = np.zeros(len(w), dtype=int)
    cur = 0
    for i in range(len(w)):
        if not np.isfinite(ma[i]) or not np.isfinite(slope[i]):
            continue
        above = close[i] > ma[i]
        rising = slope[i] > FLAT
        falling = slope[i] < -FLAT
        if above and rising:
            nxt = 2
        elif (not above) and falling:
            nxt = 4
        elif cur in (2, 3) and not falling:
            nxt = 3 if not (above and rising) else 2
        elif cur in (4, 1, 0):
            nxt = 1 if not falling else 4
        else:
            nxt = cur
        # Stage 3 collapses into 4 once price is below a falling MA; Stage 1 into 2 on breakout (handled above).
        cur = nxt
        stages[i] = cur
    return pd.Series(stages, index=w.index)


class Weinstein(Strategy):
    key = "weinstein"
    name = "Stan Weinstein"
    style = "阶段分析 · 周线 30 周均线"
    description = (
        "用周线和 30 周均线把股票分为四个阶段。只在 Stage 1 基底放量突破进入 Stage 2 时买入，"
        "周收盘跌破 30 周均线（进入 Stage 3/4）时卖出。相对强度需转正。"
    )
    overlay_colors = {"MA30周": "#e91e63", "SMA200": "#d0021b"}

    def compute(self, df: pd.DataFrame, ctx: dict) -> Computed:
        d = add_common(df)
        w = to_weekly(df)
        w["ma30"] = sma(w["Close"], 30)
        w["slope"] = w["ma30"] / w["ma30"].shift(4) - 1
        w["vol10"] = sma(w["Volume"], 10)
        w["stage"] = classify_stages(w)
        w["res26"] = w["High"].rolling(26).max().shift(1)     # base resistance
        # Mansfield relative strength vs benchmark: ratio / its 52-wk MA - 1
        spy = ctx.get("benchmark")
        if spy is not None and not spy.empty:
            sw = to_weekly(spy)["Close"].reindex(w.index, method="ffill")
            ratio = w["Close"] / sw
            w["mrs"] = ratio / sma(ratio, 52) - 1
        else:
            w["mrs"] = np.nan
        w["breakout"] = (w["Close"] > w["res26"]) & (w["Close"] > w["ma30"]) & (w["slope"] >= -FLAT) \
            & (w["Volume"] > 1.5 * w["vol10"]) & (w["stage"].shift(1).isin([1, 0, 3]) | (w["stage"].shift(1) == 2) & (w["Close"].shift(1) <= w["res26"].shift(1)))
        w["entry"] = w["breakout"] & (w["stage"] == 2)
        w["exit"] = (w["Close"] < w["ma30"]) & (w["stage"].isin([3, 4]))
        w["stop"] = np.minimum(w["ma30"] * 0.97, w["Low"].rolling(4).min())
        # map weekly signals to the last daily bar in each week
        wk = w.reindex(d.index, method="bfill")   # each daily bar gets the week (ending Friday) it belongs to
        week_end = d.index.to_series().groupby(d.index.to_period("W-FRI")).transform("max")
        is_last = d.index == week_end.values
        d["ma30w"] = w["ma30"].reindex(d.index, method="ffill")
        d["stage"] = w["stage"].reindex(d.index, method="ffill")
        d["slope"] = w["slope"].reindex(d.index, method="ffill")
        d["mrs"] = w["mrs"].reindex(d.index, method="ffill")
        d["res26"] = w["res26"].reindex(d.index, method="ffill")
        entry = pd.Series(wk["entry"].fillna(False).values & is_last, index=d.index)
        exit_ = pd.Series(wk["exit"].fillna(False).values & is_last, index=d.index)
        stop = wk["stop"].reindex(d.index).ffill()
        d["entry"], d["exit"], d["stop_lvl"] = entry, exit_, stop
        overlays = {"MA30周": d["ma30w"], "SMA200": d["sma200"]}
        comp = Computed(d, entry, exit_, stop, overlays,
                        entry_label=pd.Series(np.where(entry, "Stage 2 突破", ""), index=d.index),
                        exit_label=pd.Series(np.where(exit_, "跌破30周线", ""), index=d.index))
        comp.extra["weekly"] = w
        return comp

    def conditions(self, comp: Computed, ctx: dict) -> list[Condition]:
        w = comp.extra["weekly"]
        r = w.iloc[-1]
        stage = int(r["stage"])
        return [
            Condition("① 当前阶段 = Stage 2（上升期）", stage == 2, f"Stage {stage or '?'}"),
            Condition("② 周收盘 > 30 周均线", bool(r["Close"] > r["ma30"]), f"C {fmt(r['Close'])} vs MA30 {fmt(r['ma30'])}"),
            Condition("③ 30 周均线向上（4 周斜率 > 0.5%）", bool(r["slope"] > FLAT), f"斜率 {fmt(r['slope'], True)}"),
            Condition("④ 突破基底阻力（26 周高点）", bool(r["Close"] > r["res26"]), f"阻力 {fmt(r['res26'])}"),
            Condition("⑤ 突破周成交量 ≥ 1.5× 10 周均量", bool(r["Volume"] > 1.5 * r["vol10"]), f"本周量/10周均量 = {fmt(r['Volume'] / r['vol10'])}"),
            Condition("⑥ Mansfield 相对强度 > 0", None if not np.isfinite(r["mrs"]) else bool(r["mrs"] > 0), f"RS {fmt(r['mrs'], True)}"),
            Condition("⑦ 大盘（SPY）处于 Stage 2", ctx.get("benchmark_stage2"), f"SPY Stage {ctx.get('benchmark_stage', '?')}"),
        ]

    def state_label(self, comp: Computed, ctx: dict) -> str:
        w = comp.extra["weekly"]
        stage = int(w["stage"].iloc[-1])
        names = {1: "Stage 1 筑底", 2: "Stage 2 上升", 3: "Stage 3 做顶", 4: "Stage 4 下跌", 0: "数据不足"}
        if w["entry"].iloc[-1]:
            return "Stage 2 突破买点"
        return names[stage]

    def levels(self, comp: Computed, ctx: dict) -> dict:
        w = comp.extra["weekly"]
        r = w.iloc[-1]
        return {"resistance": r["res26"], "ma30w": r["ma30"], "stop": r["stop"]}

    def notes(self, comp: Computed, ctx: dict) -> list[str]:
        return ["Weinstein 的买点是周线级别，信号在每周最后一个交易日确认。",
                "理想买点：Stage 1 基底 + 放量突破 + 30 周线走平转升；追加买点为突破后首次回踩。"]

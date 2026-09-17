"""Oliver Kell — the Cycle of Price Action (10/20 EMA + 50 SMA).

Phases: Reversal Extension → Wedge Pop → EMA Crossback → Base n' Break → Exhaustion Extension → Wedge Drop.
Buy on Wedge Pop / EMA Crossback / Base n' Break.  Sell on Exhaustion Extension or Wedge Drop.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import add_common
from .base import Strategy, Computed, Condition, fmt


class OliverKell(Strategy):
    key = "kell"
    name = "Oliver Kell"
    style = "价格行为周期 · 10/20 EMA + 50 SMA"
    description = (
        "把股价围绕 10/20 日 EMA 的运动看成一个循环：反转延伸 → 楔形突破(Wedge Pop) → "
        "回踩均线再站上(EMA Crossback) → 平台突破(Base n' Break) → 顶部延伸(Exhaustion) → 楔形跌破(Wedge Drop)。"
        "在前三个阶段买入，在后两个阶段卖出。"
    )
    overlay_colors = {"EMA10": "#00bcd4", "EMA20": "#ff9800", "SMA50": "#f5a623"}

    def compute(self, df: pd.DataFrame, ctx: dict) -> Computed:
        d = add_common(df)
        c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
        e10, e20, s50 = d["ema10"], d["ema20"], d["sma50"]
        above_both = (c > e10) & (c > e20)
        below_both = (c < e10) & (c < e20)
        days_below = below_both.astype(int).rolling(10).sum()
        days_above = above_both.astype(int).rolling(10).sum()
        d["uptrend"] = (e10 > e20) & (e20 > s50) & (s50 > s50.shift(10))
        # Wedge Pop: first close above both EMAs after spending most of the last 10 bars below them,
        # while the 20 EMA has been flattening (wedge) and the stock is not in a deep downtrend.
        d["wedge_pop"] = above_both & ~above_both.shift(1).fillna(False) & (days_below.shift(1) >= 6) \
            & (c > s50 * 0.97) & (v > d["vol20"])
        # EMA Crossback: in an uptrend, price pulls back to / undercuts the 20 EMA then closes back above the 10 EMA.
        touched = (l.rolling(5).min() <= e20 * 1.01)
        below10 = (c < e10).astype(int).rolling(5).sum().shift(1) >= 2      # spent at least 2 of the last 5 bars under the 10 EMA
        d["crossback"] = d["uptrend"] & touched & below10 & (c > e10) & (c.shift(1) <= e10.shift(1)) \
            & (c > h.shift(1)) & (v > d["vol20"])
        # Base n' Break: tight consolidation (≤ 12% range over 15 bars) above rising EMAs, then breaks the base high.
        base_high = h.rolling(15).max().shift(1)
        base_rng = (h.rolling(15).max() - l.rolling(15).min()) / c
        d["base_rng"], d["base_high"] = base_rng, base_high
        d["base_break"] = d["uptrend"] & (base_rng.shift(1) <= 0.12) & (c > base_high) & (c.shift(1) <= base_high) & (v > 1.3 * d["vol20"])
        # Exhaustion Extension: price stretched far above the 10 EMA (≥ 4 ATR or ≥ 25%) on climactic volume.
        ext = (c - e10) / d["atr14"]
        d["ext_atr"] = ext
        d["exhaustion"] = ((ext >= 4) | ((c / e20 - 1) >= 0.25)) & (v > 1.5 * d["vol20"])
        # Wedge Drop: first close below both EMAs after being above them, with the 10 EMA rolling over.
        d["wedge_drop"] = below_both & ~below_both.shift(1).fillna(False) & (days_above.shift(1) >= 6) & (e10 < e10.shift(2))
        entry = d["wedge_pop"] | d["crossback"] | d["base_break"]
        label = np.where(d["base_break"], "Base n' Break", np.where(d["crossback"], "EMA Crossback", np.where(d["wedge_pop"], "Wedge Pop", "")))
        exit_ = d["wedge_drop"] | d["exhaustion"]
        xlabel = np.where(d["wedge_drop"], "Wedge Drop", np.where(d["exhaustion"], "Exhaustion 顶部延伸", ""))
        stop = np.maximum(np.minimum(l.rolling(3).min(), e20 * 0.98), c * 0.92)
        d["entry"], d["exit"], d["stop_lvl"] = entry, exit_, stop
        overlays = {"EMA10": e10, "EMA20": e20, "SMA50": s50}
        return Computed(d, entry, exit_, pd.Series(stop, index=d.index), overlays,
                        entry_label=pd.Series(label, index=d.index), exit_label=pd.Series(xlabel, index=d.index))

    def phase(self, r) -> str:
        if r["exhaustion"]:
            return "Exhaustion Extension（顶部延伸）"
        if r["wedge_drop"]:
            return "Wedge Drop（楔形跌破）"
        if r["base_break"]:
            return "Base n' Break（平台突破）"
        if r["crossback"]:
            return "EMA Crossback（回踩站回）"
        if r["wedge_pop"]:
            return "Wedge Pop（楔形突破）"
        if r["uptrend"] and r["Close"] > r["ema10"]:
            return "上升趋势 · 均线上方"
        if r["uptrend"]:
            return "上升趋势 · 回踩均线中"
        if r["Close"] < r["ema20"] and r["ema10"] < r["ema20"]:
            return "下跌 / 反转延伸阶段"
        return "楔形整理中"

    def conditions(self, comp: Computed, ctx: dict) -> list[Condition]:
        r = comp.df.iloc[-1]
        return [
            Condition("① 均线多头排列（EMA10 > EMA20 > SMA50，50 上升）", bool(r["uptrend"]),
                      f"EMA10 {fmt(r['ema10'])} / EMA20 {fmt(r['ema20'])} / SMA50 {fmt(r['sma50'])}"),
            Condition("② 价格在 10/20 EMA 上方", bool(r["Close"] > r["ema10"] and r["Close"] > r["ema20"]), f"C {fmt(r['Close'])}"),
            Condition("③ 未过度延伸（距 10 EMA < 4 ATR）", bool(r["ext_atr"] < 4), f"延伸 {fmt(r['ext_atr'], nd=1)} ATR"),
            Condition("④ Wedge Pop：从均线下方首次站回", bool(r["wedge_pop"]), "", weight=1.5),
            Condition("⑤ EMA Crossback：回踩 20 EMA 后收回 10 EMA 上", bool(r["crossback"]), "", weight=1.5),
            Condition("⑥ Base n' Break：紧凑平台放量突破", bool(r["base_break"]), f"平台区间 {fmt(r['base_rng'], True, 0)}，平台高点 {fmt(r['base_high'])}", weight=1.5),
            Condition("⑦ 无卖出信号（非 Wedge Drop / Exhaustion）", bool(not (r["wedge_drop"] or r["exhaustion"])), ""),
        ]

    def state_label(self, comp: Computed, ctx: dict) -> str:
        return self.phase(comp.df.iloc[-1])

    def levels(self, comp: Computed, ctx: dict) -> dict:
        r = comp.df.iloc[-1]
        return {"ema10": r["ema10"], "ema20": r["ema20"], "stop": r["stop_lvl"], "base_high": r["base_high"]}

    def notes(self, comp: Computed, ctx: dict) -> list[str]:
        return ["Kell 在 Wedge Pop 和 EMA Crossback 处建仓，在 Base n' Break 加仓，Exhaustion 时主动卖入强势。",
                "止损：入场 K 线低点或 20 EMA 下方 2%，孰高者。"]

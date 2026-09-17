"""Kristjan Kullamägi (Qullamaggie) — momentum breakouts & episodic pivots.

Setup A  Breakout: a stock that already moved 30%+ in 1-3 months, consolidates 2-8 weeks in a tightening
         flag above the rising 10/20-day MAs (volume dries up), then breaks the flag high on volume.
Setup B  Episodic Pivot (EP): gap-up ≥ 10% on ≥ 3x average volume (earnings / catalyst) after a dull period.
Stop: low of the breakout day (fallback: 1 ATR).  Sell: 1/3-1/2 into strength after 3-5 days,
      trail the rest with the 10-day MA (fast) — here we exit on a close below the 20-day MA.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import add_common
from .base import Strategy, Computed, Condition, fmt, fund_conditions


class Kullamagi(Strategy):
    key = "kullamagi"
    name = "Kristjan Kullamägi"
    style = "动量突破 · 旗形 / Episodic Pivot"
    description = (
        "找 1-3 个月内已经涨过 30%+ 的强势股，等它在 10/20 日均线上方横盘收紧 2-8 周，"
        "放量突破旗形高点时买入，止损放在突破日低点；或在放量跳空 (EP) 当日买入。"
        "3-5 天后卖出 1/3-1/2，剩余用 10/20 日均线跟踪。"
    )
    overlay_colors = {"EMA10": "#00bcd4", "EMA20": "#ff9800", "SMA50": "#f5a623"}

    def compute(self, df: pd.DataFrame, ctx: dict) -> Computed:
        d = add_common(df)
        c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
        # Prior momentum leg: max gain from the lowest close of the 20..80 bar window to the highest close since.
        lo_prior = c.shift(15).rolling(65).min()
        hi_recent = c.rolling(30).max()
        d["prior_move"] = hi_recent / lo_prior - 1
        # Consolidation: last 10 bars range tight vs the 30-bar range; holding above 20 EMA.
        rng10 = (h.rolling(10).max() - l.rolling(10).min()) / c
        rng30 = (h.rolling(30).max() - l.rolling(30).min()) / c
        d["rng10"], d["rng30"] = rng10, rng30
        d["tight"] = rng10 < 0.6 * rng30
        d["depth"] = 1 - l.rolling(20).min() / hi_recent
        d["above_ma"] = (c > d["ema20"]) & (d["ema10"] >= d["ema20"] * 0.98) & (d["ema20"] > d["ema20"].shift(5))
        d["vol_dry"] = v.rolling(5).mean() < d["vol20"]
        d["flag_high"] = h.rolling(20).max().shift(1)
        d["flag_break"] = (c > d["flag_high"]) & (c.shift(1) <= d["flag_high"]) & (v > 1.5 * d["vol20"])
        setup_a = (d["prior_move"] >= 0.30) & (d["depth"] < 0.25) & d["above_ma"] & d["tight"].shift(1).fillna(False)
        entry_a = setup_a & d["flag_break"]
        # Episodic pivot
        gap = d["Open"] / c.shift(1) - 1
        d["gap"] = gap
        d["ep"] = (gap >= 0.10) & (v >= 3 * d["vol50"]) & (c > d["Open"] * 0.98) & (c > c.shift(1) * 1.08)
        entry = entry_a | d["ep"]
        label = np.where(d["ep"], "EP 跳空", np.where(entry_a, "旗形突破", ""))
        stop = np.minimum(l, c - d["atr14"])
        stop = np.maximum(stop, c * 0.90)  # never risk more than 10%
        exit_ = (c < d["ema20"]) & (c.shift(1) < d["ema20"])
        d["entry"], d["exit"], d["stop_lvl"], d["setup_a"] = entry, exit_, stop, setup_a
        overlays = {"EMA10": d["ema10"], "EMA20": d["ema20"], "SMA50": d["sma50"]}
        comp = Computed(d, entry, exit_, pd.Series(stop, index=d.index), overlays,
                        entry_label=pd.Series(label, index=d.index),
                        exit_label=pd.Series(np.where(exit_, "跌破20日线", ""), index=d.index))
        comp.extra["profit_trail"] = {"trigger": 0.10, "series": d["ema10"], "label": "盈利后跌破10EMA"}
        return comp

    def conditions(self, comp: Computed, ctx: dict) -> list[Condition]:
        d = comp.df
        r = d.iloc[-1]
        adr = ((d["High"] / d["Low"] - 1).tail(20).mean())
        return [
            Condition("① 前置涨幅 ≥ 30%（1-3 个月内）", bool(r["prior_move"] >= 0.30), f"涨幅 {fmt(r['prior_move'], True, 0)}"),
            Condition("② 回调深度 < 25%", bool(r["depth"] < 0.25), f"回撤 {fmt(r['depth'], True, 0)}"),
            Condition("③ 价格站在上升的 10/20 日均线上方", bool(r["above_ma"]), f"C {fmt(r['Close'])} / EMA10 {fmt(r['ema10'])} / EMA20 {fmt(r['ema20'])}"),
            Condition("④ 旗形收紧（10 日区间 < 60% 的 30 日区间）", bool(r["tight"]), f"10日 {fmt(r['rng10'], True, 0)} vs 30日 {fmt(r['rng30'], True, 0)}"),
            Condition("⑤ 缩量整理（5 日均量 < 20 日均量）", bool(r["vol_dry"]), f"5日/20日均量 = {fmt(d['Volume'].tail(5).mean() / r['vol20'])}"),
            Condition("⑥ ADR% ≥ 3%（够活跃）", bool(adr >= 0.03), f"20 日 ADR {fmt(adr, True, 1)}"),
            Condition("⑦ 放量突破旗形高点", bool(r["flag_break"]), f"旗形高点 {fmt(r['flag_high'])}，今日量/20日均量 {fmt(r['Volume'] / r['vol20'])}", weight=1.5),
            Condition("⑧ Episodic Pivot（跳空 ≥10% 且量 ≥3×）", bool(r["ep"]), f"跳空 {fmt(r['gap'], True, 1)}，量/50日均量 {fmt(r['Volume'] / r['vol50'])}", weight=0.5),
        ] + fund_conditions(ctx, eps_min=0.20, rev_min=0.20, weight=0.5)

    def state_label(self, comp: Computed, ctx: dict) -> str:
        r = comp.df.iloc[-1]
        if r["ep"]:
            return "Episodic Pivot 买点"
        if r["entry"]:
            return "旗形突破买点"
        if r["setup_a"]:
            return "旗形收紧 · 等待突破"
        if r["prior_move"] >= 0.30 and r["depth"] < 0.25:
            return "强势股 · 整理中"
        return "无动量设置"

    def levels(self, comp: Computed, ctx: dict) -> dict:
        r = comp.df.iloc[-1]
        return {"flag_high": r["flag_high"], "stop": r["stop_lvl"], "ema10": r["ema10"], "ema20": r["ema20"]}

    def notes(self, comp: Computed, ctx: dict) -> list[str]:
        return ["止损：突破日低点。3-5 天后卖 1/3-1/2 锁利，剩余按 10 日线（激进）或 20 日线（保守）跟踪。",
                "Kullamägi 只在市场（QQQ）处于上升趋势时进攻，熊市里空仓等待。"]

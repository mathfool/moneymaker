"""Mark Minervini — SEPA / Trend Template + VCP breakout.

Buy: trend template satisfied + volatility contraction + close breaks the pivot on volume.
Sell: close below the 50-day MA, or the initial stop (below the last contraction low, capped at 8%).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import add_common
from .base import Strategy, Computed, Condition, last, fmt, fund_conditions


class Minervini(Strategy):
    key = "minervini"
    name = "Mark Minervini"
    style = "SEPA · 趋势模板 + VCP 突破"
    description = (
        "只在符合 8 条趋势模板的 Stage 2 股票里找 VCP（波动收缩形态），"
        "在收缩末端放量突破枢轴点时买入，跌破 50 日线或触发 7-8% 止损离场。"
    )
    overlay_colors = {"SMA50": "#f5a623", "SMA150": "#7ed321", "SMA200": "#d0021b"}

    MAX_STOP = 0.08

    def compute(self, df: pd.DataFrame, ctx: dict) -> Computed:
        d = add_common(df)
        c = d["Close"]
        d["sma200_up"] = d["sma200"] > d["sma200"].shift(21)
        d["tt"] = (
            (c > d["sma50"]) & (d["sma50"] > d["sma150"]) & (d["sma150"] > d["sma200"])
            & d["sma200_up"] & (c >= d["lo52"] * 1.30) & (c >= d["hi52"] * 0.75)
        )
        # --- VCP proxy, measured on the bars BEFORE today so the breakout bar doesn't widen the range.
        # Leg A = last 10 bars, Leg B = the 20 bars before that. Contraction = A noticeably tighter than B.
        adr = (d["High"] / d["Low"] - 1).rolling(20).mean()
        d["adr20"] = adr
        rng_a = ((d["High"].rolling(10).max() - d["Low"].rolling(10).min()) / c).shift(1)
        rng_b = ((d["High"].rolling(20).max() - d["Low"].rolling(20).min()) / c).shift(11)
        rng_c = ((d["High"].rolling(20).max() - d["Low"].rolling(20).min()) / c).shift(31)
        d["rng1"], d["rng2"], d["rng3"] = rng_a, rng_b, rng_c
        base_hi = d["High"].rolling(60).max().shift(1)
        base_lo = d["Low"].rolling(60).min().shift(1)
        d["depth"] = 1 - base_lo / base_hi
        d["vcp"] = (rng_a < 0.75 * rng_b) & (d["depth"] <= 0.35)
        d["tight"] = rng_a <= np.maximum(0.08, 3.0 * adr)          # last 10 bars inside ~3 average daily ranges
        d["vol_dry"] = d["Volume"].shift(1).rolling(5).mean() < d["vol50"]
        # Pivot = highest high of the last 20 bars, excluding today.
        d["pivot"] = d["High"].rolling(20).max().shift(1)
        d["base_low"] = d["Low"].rolling(10).min().shift(1)
        d["breakout"] = (c > d["pivot"]) & (d["Volume"] > 1.3 * d["vol50"]) & (c.shift(1) <= d["pivot"]) \
            & (c > d["Open"]) & ((c - d["Low"]) / (d["High"] - d["Low"] + 1e-9) >= 0.5)
        entry = d["tt"] & d["breakout"] & (d["vcp"] | d["tight"])
        stop = np.maximum(d["base_low"], c * (1 - self.MAX_STOP))
        exit_ = (c < d["sma50"]) & (c.shift(1) < d["sma50"])
        d["entry"], d["exit"], d["stop_lvl"] = entry, exit_, stop
        overlays = {"SMA50": d["sma50"], "SMA150": d["sma150"], "SMA200": d["sma200"]}
        comp = Computed(d, entry, exit_, stop, overlays,
                        entry_label=pd.Series(np.where(entry, "VCP突破", ""), index=d.index),
                        exit_label=pd.Series(np.where(exit_, "跌破50日线", ""), index=d.index))
        comp.extra["profit_trail"] = {"trigger": 0.20, "series": d["ema10"], "label": "盈利后跌破10EMA"}
        return comp

    def conditions(self, comp: Computed, ctx: dict) -> list[Condition]:
        d = comp.df
        r = d.iloc[-1]
        rs = ctx.get("rs_rank")
        c = r["Close"]
        conds = [
            Condition("① 价格 > 50日 > 150日 > 200日均线",
                      bool(c > r["sma50"] > r["sma150"] > r["sma200"]),
                      f"C {fmt(c)} / 50: {fmt(r['sma50'])} / 150: {fmt(r['sma150'])} / 200: {fmt(r['sma200'])}"),
            Condition("② 200日均线至少上升 1 个月", bool(r["sma200_up"]),
                      f"200日线较21日前 {fmt(r['sma200'] / d['sma200'].iloc[-22] - 1, True) if len(d) > 22 and np.isfinite(d['sma200'].iloc[-22]) else 'n/a'}"),
            Condition("③ 距 52 周低点 ≥ 30%", bool(c >= r["lo52"] * 1.3), f"高于低点 {fmt(c / r['lo52'] - 1, True)}"),
            Condition("④ 距 52 周高点 ≤ 25%", bool(c >= r["hi52"] * 0.75), f"低于高点 {fmt(1 - c / r['hi52'], True)}"),
            Condition("⑤ RS 相对强度排名 ≥ 70", None if rs is None else bool(rs >= 70), f"RS = {rs if rs is not None else '未扫描'}"),
            Condition("⑥ VCP 波动收缩（近 10 日区间 < 75% 前 20 日区间，基底深度 ≤ 35%）", bool(r["vcp"]),
                      f"区间: {fmt(r['rng3'], True, 1)} → {fmt(r['rng2'], True, 1)} → {fmt(r['rng1'], True, 1)}，深度 {fmt(r['depth'], True, 0)}"),
            Condition("⑦ 收紧到位（10 日区间 ≤ 3 个 ADR）", bool(r["tight"]),
                      f"10日区间 {fmt(r['rng1'], True, 1)} vs 3×ADR {fmt(3 * r['adr20'], True, 1)}"),
            Condition("⑧ 成交量萎缩（突破前 5 日均量 < 50 日均量）", bool(r["vol_dry"]),
                      f"5日均量/50日均量 = {fmt(d['Volume'].iloc[-6:-1].mean() / r['vol50'])}"),
            Condition("⑨ 放量突破枢轴点（量 ≥ 1.3× 且收在上半段）", bool(r["breakout"]),
                      f"枢轴 {fmt(r['pivot'])}，今日量/50日均量 = {fmt(r['Volume'] / r['vol50'])}", weight=1.5),
        ]
        conds += fund_conditions(ctx, eps_min=0.25, rev_min=0.10, want_accel=True)
        return conds

    def state_label(self, comp: Computed, ctx: dict) -> str:
        r = comp.df.iloc[-1]
        if r["entry"]:
            return "VCP 突破买点"
        if r["tt"] and (r["vcp"] or r["tight"]):
            return "趋势模板 ✓ · VCP 收紧中"
        if r["tt"]:
            return "趋势模板 ✓"
        if r["Close"] > r["sma200"]:
            return "200日线上方，未达模板"
        return "趋势模板不符"

    def levels(self, comp: Computed, ctx: dict) -> dict:
        r = comp.df.iloc[-1]
        return {"pivot": r["pivot"], "stop": r["stop_lvl"], "sma50": r["sma50"]}

    def notes(self, comp: Computed, ctx: dict) -> list[str]:
        return ["止损：突破失败跌回基底低点，最大 7-8%。", "获利：涨幅达 2-3 倍风险后分批减仓，剩余跟随 50 日线。"]

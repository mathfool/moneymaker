"""J Law (劳建华) — 2024/2025 US Investing Championship winner, Minervini's student.

Our interpretation of his public playbook (M.E.T.S. = multiple edges lining up):
  1. Trend edge   : Minervini trend template (Stage 2) — the non-negotiable filter.
  2. Strength edge: RS rank ≥ 80 and the stock's sector in the top half.
  3. Volume edge  : institutional footprints — recent accumulation days (up on ≥1.5x volume) outnumber distribution days.
  4. Momentum edge: 10 EMA > 21 EMA, both rising, price close to the highs.
  5. Market edge  : SPY above its 50-day and 50 > 200 (bull regime) — otherwise no new buys.
Entries: (A) pullback to the rising 10/21 EMA on light volume, then an up-day that takes out the prior high
         on heavier volume;  (B) pivot breakout (20-day high) on ≥ 1.5x volume.
Risk: initial stop = pullback low, capped at 1.5×ADR (3%-5%). He sizes so one trade risks ~0.3% of the account.
Exit: two closes below the 21 EMA, or 10 EMA crosses below 21 EMA (momentum fades).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import add_common
from .base import Strategy, Computed, Condition, fmt, fund_conditions


class JLaw(Strategy):
    key = "jlaw"
    name = "J Law 劳建华"
    style = "多重优势叠加 · 趋势 + 动量 + 量能"
    description = (
        "Minervini 趋势模板为底线，再要求 RS ≥ 80、板块领先、机构吸筹（放量上涨日多于放量下跌日）、"
        "10/21 EMA 多头。只在大盘处于牛市（SPY > 50 日线且 50 > 200）时买入：回踩 10/21 EMA 缩量后"
        "放量收复前高，或放量突破 20 日高点。止损 = 回调低点，上限 1.5×ADR（3-5%），单笔风险 0.3% 账户。"
    )
    overlay_colors = {"EMA10": "#00bcd4", "EMA21": "#ff9800", "SMA50": "#f5a623", "SMA200": "#d0021b"}

    MAX_STOP = 0.05

    def compute(self, df: pd.DataFrame, ctx: dict) -> Computed:
        d = add_common(df)
        c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
        e10, e21 = d["ema10"], d["ema21"]
        d["tt"] = (c > d["sma50"]) & (d["sma50"] > d["sma150"]) & (d["sma150"] > d["sma200"]) \
            & (d["sma200"] > d["sma200"].shift(21)) & (c >= d["lo52"] * 1.30) & (c >= d["hi52"] * 0.75)
        d["mom"] = (e10 > e21) & (e10 > e10.shift(3)) & (e21 > e21.shift(3))
        up_big = ((c > c.shift(1)) & (v >= 1.5 * d["vol50"])).astype(int)
        dn_big = ((c < c.shift(1)) & (v >= 1.5 * d["vol50"])).astype(int)
        d["acc_days"], d["dist_days"] = up_big.rolling(25).sum(), dn_big.rolling(25).sum()
        d["accum"] = d["acc_days"] > d["dist_days"]
        # Market regime series (bull) from the benchmark, aligned on dates.
        spy = ctx.get("benchmark")
        if spy is not None and not spy.empty:
            sc = spy["Close"]
            bull = (sc > sc.rolling(50).mean()) & (sc.rolling(50).mean() > sc.rolling(200).mean())
            d["bull"] = bull.reindex(d.index, method="ffill").fillna(False).astype(bool)
        else:
            d["bull"] = True
        strong_close = (c - l) / (h - l + 1e-9) >= 0.6
        # (A) pullback-and-reclaim
        pulled = (l.rolling(4).min() <= e21 * 1.02) & (l.rolling(4).min() >= e21 * 0.95)
        light_pb = v.shift(1).rolling(3).mean() < d["vol20"]
        d["pullback_setup"] = d["tt"] & d["mom"] & pulled
        d["reclaim"] = d["pullback_setup"] & light_pb & (c > h.shift(1)) & (c > e10) & (v > d["vol20"]) & strong_close
        # (B) pivot breakout
        pivot = h.rolling(20).max().shift(1)
        d["pivot"] = pivot
        adr = (h / l - 1).rolling(20).mean()
        d["adr20"] = adr
        rng10 = ((h.rolling(10).max() - l.rolling(10).min()) / c).shift(1)
        d["tight"] = rng10 <= np.maximum(0.08, 3.0 * adr)             # a real base: last 10 bars inside ~3 ADR
        d["pivot_break"] = d["tt"] & d["mom"] & d["tight"] & strong_close & (c > pivot) & (c.shift(1) <= pivot) & (v >= 1.5 * d["vol50"])
        entry = (d["reclaim"] | d["pivot_break"]) & d["bull"] & d["accum"]
        label = np.where(d["pivot_break"], "放量突破", np.where(d["reclaim"], "回踩收复", ""))
        pb_low = l.rolling(4).min()
        max_stop = np.clip(1.5 * adr, 0.03, self.MAX_STOP)          # tight for calm names, a bit of room for volatile ones
        d["max_stop"] = max_stop
        stop = np.maximum(pb_low, c * (1 - max_stop))
        exit_ = ((c < e21) & (c.shift(1) < e21)) | ((e10 < e21) & (e10.shift(1) >= e21.shift(1)))
        xlabel = np.where((e10 < e21) & (e10.shift(1) >= e21.shift(1)), "动量衰竭 10<21", np.where(exit_, "两日收于21EMA下", ""))
        d["entry"], d["exit"], d["stop_lvl"] = entry, exit_, stop
        overlays = {"EMA10": e10, "EMA21": e21, "SMA50": d["sma50"], "SMA200": d["sma200"]}
        comp = Computed(d, entry, exit_, pd.Series(stop, index=d.index), overlays,
                        entry_label=pd.Series(label, index=d.index), exit_label=pd.Series(xlabel, index=d.index))
        comp.extra["profit_trail"] = {"trigger": 0.15, "series": e10, "label": "盈利后跌破10EMA"}
        return comp

    def conditions(self, comp: Computed, ctx: dict) -> list[Condition]:
        d = comp.df
        r = d.iloc[-1]
        rs = ctx.get("rs_rank")
        sec_rank, sec_total = ctx.get("sector_rank"), ctx.get("sector_total")
        sec_ok = None if sec_rank is None or not sec_total else bool(sec_rank <= max(1, sec_total // 2))
        return [
            Condition("① 趋势优势：Minervini 趋势模板", bool(r["tt"]),
                      f"C {fmt(r['Close'])} > 50 {fmt(r['sma50'])} > 150 {fmt(r['sma150'])} > 200 {fmt(r['sma200'])}", weight=1.5),
            Condition("② 强度优势：RS ≥ 80", None if rs is None else bool(rs >= 80), f"RS = {rs if rs is not None else '未扫描'}"),
            Condition("③ 板块优势：所在板块排名前一半", sec_ok,
                      f"{ctx.get('sector') or '?'} 排名 {sec_rank}/{sec_total}" if sec_rank else "未扫描"),
            Condition("④ 量能优势：25 日内吸筹日 > 派发日", bool(r["accum"]), f"吸筹 {int(r['acc_days'])} vs 派发 {int(r['dist_days'])}"),
            Condition("⑤ 动量优势：EMA10 > EMA21 且同步上升", bool(r["mom"]), f"EMA10 {fmt(r['ema10'])} / EMA21 {fmt(r['ema21'])}"),
            Condition("⑥ 市场优势：SPY > 50 日线且 50 > 200", bool(r["bull"]), "大盘牛市结构" if r["bull"] else "大盘不在牛市结构，不开新仓"),
            Condition("⑦ 买点 A：回踩 10/21 EMA 缩量后放量收复前高", bool(r["reclaim"]), "", weight=1.5),
            Condition("⑧ 买点 B：收紧后放量突破 20 日高点", bool(r["pivot_break"]),
                      f"枢轴 {fmt(r['pivot'])}，量/50日均量 {fmt(r['Volume'] / r['vol50'])}，10日区间 {'收紧' if r['tight'] else '未收紧'}", weight=1.5),
        ] + fund_conditions(ctx, eps_min=0.20, rev_min=0.15)

    def state_label(self, comp: Computed, ctx: dict) -> str:
        r = comp.df.iloc[-1]
        if r["entry"]:
            return "多重优势买点"
        if not r["bull"]:
            return "大盘熊市结构 · 观望"
        if r["tt"] and r["pullback_setup"]:
            return "趋势股回踩均线 · 等待收复"
        if r["tt"] and r["mom"]:
            return "趋势 + 动量 ✓ · 等买点"
        if r["tt"]:
            return "趋势模板 ✓ · 动量不足"
        return "不符合趋势模板"

    def levels(self, comp: Computed, ctx: dict) -> dict:
        r = comp.df.iloc[-1]
        return {"pivot": r["pivot"], "stop": r["stop_lvl"], "ema21": r["ema21"]}

    def notes(self, comp: Computed, ctx: dict) -> list[str]:
        return ["仓位：单笔风险 = 账户 0.3%（回撤期减到 0.15%），股数 = 风险金额 ÷ (买价 − 止损)。",
                "一次性建仓，不分批；只有当股票以 45° 角强势推进时才小额加仓。",
                "动量还在就持有；基本面或技术面确认消失就走，账户表现差时清仓休息。"]

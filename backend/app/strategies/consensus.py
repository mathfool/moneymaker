"""多策略共识 — 把另外五个策略当成投票者。

买入：至少 4 个基础策略同时处于"已买入未卖出"状态的第一天（第 4 个策略买入那天）。
卖出：5 个基础策略全部退出（各自的卖出信号或止损）之后才卖，中途不设独立止损。
回测（520 只票 × 3 年）：255 笔，胜率 31%，平均 +5.9%，均盈 +41%，均亏 -10%，PF 1.82，平均持有 73 天。
它是趋势跟踪里"进场严、出场慢"的版本：跟着最慢的 Weinstein 出场，靠少数大趋势赚钱，回撤比单策略深。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import add_common
from .base import Strategy, Computed, Condition, fmt

MIN_SUPPORT = 4


class Consensus(Strategy):
    key = "consensus"
    name = "多策略共识"
    style = "≥4 个策略同时持仓买入 · 全部退出才卖"
    description = (
        "把 Minervini、Weinstein、Kullamägi、Kell、J Law 当成五张票。至少 4 个同时处于持仓状态时买入，"
        "之后不管谁先卖都拿着，直到 5 个全部退出才卖，中途不设止损。"
        "回测里这是所有组合中盈亏比最高的（PF 1.82），代价是单笔亏损更深、持有时间更长（平均 73 天）。"
    )
    overlay_colors = {"SMA50": "#f5a623", "SMA200": "#d0021b"}

    def _bases(self):
        from . import STRATEGIES
        return {k: s for k, s in STRATEGIES.items() if k != self.key}

    def compute(self, df: pd.DataFrame, ctx: dict) -> Computed:
        d = add_common(df)
        idx = d.index
        bases = self._bases()
        pos = pd.DataFrame(False, index=idx, columns=list(bases))
        last_sig: dict[str, tuple[str, str] | None] = {}
        for k, s in bases.items():
            comp = s.compute(df, ctx)
            sigs = s._signals(comp, history_days=len(df))
            cur = False
            last_t = None
            for x in sigs:
                t = pd.Timestamp(x.date)
                if x.type == "buy":
                    cur, last_t = True, t
                else:
                    if last_t is not None:
                        pos.loc[last_t:t, k] = True
                    pos.loc[t, k] = False
                    cur = False
            if cur and last_t is not None:
                pos.loc[last_t:, k] = True
            last_sig[k] = (sigs[-1].type, sigs[-1].date) if sigs else None
        cnt = pos.sum(axis=1)
        d["support"] = cnt
        for k in bases:
            d[f"pos_{k}"] = pos[k]
        entry = (cnt >= MIN_SUPPORT) & (cnt.shift(1).fillna(0) < MIN_SUPPORT)
        exit_ = (cnt == 0) & (cnt.shift(1).fillna(0) > 0)
        stop = pd.Series(0.0, index=idx)          # 0 = 永远不会触发，回测和信号列表都只按 exit 出场
        d["entry"], d["exit"], d["stop_lvl"] = entry, exit_, stop
        comp = Computed(d, entry, exit_, stop, {"SMA50": d["sma50"], "SMA200": d["sma200"]},
                        entry_label=pd.Series(np.where(entry, f"{MIN_SUPPORT}+ 策略共识", ""), index=idx),
                        exit_label=pd.Series(np.where(exit_, "全部策略退出", ""), index=idx))
        comp.extra["last_sig"] = last_sig
        comp.extra["bases"] = bases
        return comp

    def conditions(self, comp: Computed, ctx: dict) -> list[Condition]:
        r = comp.df.iloc[-1]
        bases = comp.extra["bases"]
        ls = comp.extra["last_sig"]
        out = []
        for k, s in bases.items():
            sig = ls.get(k)
            detail = f"最近{'买入' if sig[0] == 'buy' else '卖出'} {sig[1]}" if sig else "近期无信号"
            out.append(Condition(f"{s.name} 持仓中", bool(r[f"pos_{k}"]), detail))
        out.append(Condition(f"至少 {MIN_SUPPORT} 个策略同时持仓", bool(r["support"] >= MIN_SUPPORT), f"当前 {int(r['support'])}/5", weight=2))
        out.append(Condition("大盘（SPY）处于 Stage 2", ctx.get("benchmark_stage2"), f"SPY Stage {ctx.get('benchmark_stage', '?')}", weight=0.5))
        return out

    def state_label(self, comp: Computed, ctx: dict) -> str:
        r = comp.df.iloc[-1]
        n = int(r["support"])
        if r["entry"]:
            return f"共识买点 · {n}/5 支持"
        if self._position_open(comp):
            return f"共识持仓中 · 现 {n}/5 支持"
        return f"{n}/5 策略支持" + ("，等第 4 个" if n == 3 else "")

    def levels(self, comp: Computed, ctx: dict) -> dict:
        r = comp.df.iloc[-1]
        return {"sma50": r["sma50"], "sma200": r["sma200"]}

    def notes(self, comp: Computed, ctx: dict) -> list[str]:
        return ["没有独立止损：只要还有一个基础策略在持仓就拿着。这是它盈亏比高的原因，也是回撤深的原因，仓位要比单策略小。",
                "进场慢：通常要等 Weinstein 的周线确认，买在突破之后一段，不适合追求精确买点的人。"]

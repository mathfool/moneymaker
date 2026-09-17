"""Common contract for every trader strategy.

A strategy computes, vectorized over the whole daily history:
  - `entry`  : bool Series, True on bars that generate a BUY signal
  - `exit`   : bool Series, True on bars that generate a SELL signal
  - `stop`   : float Series, the initial protective stop to use if bought on that bar
  - `overlays`: dict name -> Series drawn on the chart (moving averages, etc.)
  - per-bar `state` labels used for the current-condition checklist
and then summarises the LAST bar into a checklist of conditions the UI shows.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class Condition:
    name: str
    passed: bool | None          # None = unknown / not applicable
    detail: str = ""
    weight: float = 1.0


@dataclass
class Signal:
    date: str
    type: str                    # buy | sell | info
    label: str
    price: float


@dataclass
class Computed:
    df: pd.DataFrame
    entry: pd.Series
    exit: pd.Series
    stop: pd.Series
    overlays: dict[str, pd.Series] = field(default_factory=dict)
    entry_label: pd.Series | None = None      # optional per-bar label for buy signals
    exit_label: pd.Series | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyResult:
    strategy: str
    symbol: str
    state: str                   # short human label for the current situation
    score: float                 # 0..100 setup quality
    signal: str                  # "buy" | "sell" | "hold" | "none"  (as of the last bar)
    conditions: list[Condition]
    signals: list[Signal]
    levels: dict[str, float | None]
    notes: list[str]
    overlays: dict[str, list[dict]]
    last_signal: Signal | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class Strategy:
    key: str = "base"
    name: str = "Base"
    description: str = ""
    style: str = ""
    overlay_colors: dict[str, str] = {}

    # --- subclasses implement -------------------------------------------
    def compute(self, df: pd.DataFrame, ctx: dict) -> Computed:
        raise NotImplementedError

    def conditions(self, comp: Computed, ctx: dict) -> list[Condition]:
        raise NotImplementedError

    def state_label(self, comp: Computed, ctx: dict) -> str:
        return ""

    def levels(self, comp: Computed, ctx: dict) -> dict[str, float | None]:
        return {}

    def notes(self, comp: Computed, ctx: dict) -> list[str]:
        return []

    # --- shared ----------------------------------------------------------
    def evaluate(self, df: pd.DataFrame, ctx: dict, symbol: str = "", history_days: int = 400) -> StrategyResult:
        comp = self.compute(df, ctx)
        conds = self.conditions(comp, ctx)
        score = self._score(conds)
        signals = self._signals(comp, history_days)
        last = signals[-1] if signals else None
        last_date = comp.df.index[-1].strftime("%Y-%m-%d")
        if last and last.date == last_date:
            signal = last.type
        else:
            signal = "hold" if (last and last.type == "buy" and self._position_open(comp)) else "none"
        overlays = {}
        for k, s in comp.overlays.items():
            s = s.dropna().tail(history_days)
            overlays[k] = [{"time": t.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for t, v in s.items()]
        return StrategyResult(
            strategy=self.key,
            symbol=symbol,
            state=self.state_label(comp, ctx),
            score=score,
            signal=signal,
            conditions=conds,
            signals=signals,
            levels={k: (None if v is None or not np.isfinite(v) else round(float(v), 2)) for k, v in self.levels(comp, ctx).items()},
            notes=self.notes(comp, ctx),
            overlays=overlays,
            last_signal=last,
        )

    def _position_open(self, comp: Computed) -> bool:
        """After the last buy signal, has an exit (signal or stop) fired?"""
        sigs = self._signals(comp, history_days=len(comp.df))
        return bool(sigs) and sigs[-1].type == "buy"

    @staticmethod
    def _score(conds: list[Condition]) -> float:
        tot = sum(c.weight for c in conds if c.passed is not None)
        if tot == 0:
            return 0.0
        got = sum(c.weight for c in conds if c.passed)
        return round(100 * got / tot, 1)

    def _signals(self, comp: Computed, history_days: int) -> list[Signal]:
        """Turn entry/exit/stop series into a chronological, position-aware signal list.

        Once a buy fires, further buys are ignored until the position is closed, either by the strategy's
        exit signal or by price trading through the initial stop (the same rules the backtest uses).
        Profit trailing (extra["profit_trail"]) is applied too, so chart markers match backtest trades.
        """
        df = comp.df
        out: list[Signal] = []
        in_pos = False
        entry = comp.entry.fillna(False).values
        exit_ = comp.exit.fillna(False).values
        stop_s = comp.stop.reindex(df.index).values
        lows, opens, closes = df["Low"].values, df["Open"].values, df["Close"].values
        pt = comp.extra.get("profit_trail")
        trail = pt["series"].reindex(df.index).values if pt else None
        idx = df.index
        elabel = comp.entry_label.values if comp.entry_label is not None else None
        xlabel = comp.exit_label.values if comp.exit_label is not None else None
        start = max(0, len(df) - history_days)
        ep = st = 0.0
        for i in range(len(df)):
            if in_pos:
                px = label = None
                if lows[i] <= st:
                    px, label = (min(opens[i], st) if opens[i] < st else st), "止损"
                elif exit_[i]:
                    px, label = closes[i], (str(xlabel[i]) if xlabel is not None and xlabel[i] else "卖出")
                elif trail is not None and closes[i] / ep - 1 >= pt["trigger"] and np.isfinite(trail[i]) and closes[i] < trail[i]:
                    px, label = closes[i], pt.get("label", "移动止盈")
                if px is not None:
                    in_pos = False
                    if i >= start:
                        out.append(Signal(idx[i].strftime("%Y-%m-%d"), "sell", label, round(float(px), 2)))
                    continue
            if entry[i] and not in_pos:
                in_pos = True
                ep = closes[i]
                st = stop_s[i] if np.isfinite(stop_s[i]) and stop_s[i] < ep else ep * 0.93
                if i >= start:
                    out.append(Signal(idx[i].strftime("%Y-%m-%d"), "buy", str(elabel[i]) if elabel is not None and elabel[i] else "买入", round(float(ep), 2)))
        return out


def last(s: pd.Series, default=np.nan) -> float:
    try:
        v = s.iloc[-1]
        return default if v is None or (isinstance(v, float) and np.isnan(v)) else v
    except Exception:  # noqa: BLE001
        return default


def fund_conditions(ctx: dict, eps_min: float, rev_min: float, weight: float = 1.0, want_accel: bool = False) -> list[Condition]:
    """Shared growth checks. Unknown data -> passed=None so it doesn't count against the score."""
    f = ctx.get("fund") or {}
    eps, rev = f.get("eps_yoy"), f.get("rev_yoy")
    out = [
        Condition(f"基本面：最新季度 EPS 同比 ≥ {eps_min:.0%}", None if eps is None else bool(eps >= eps_min),
                  f"EPS 同比 {fmt(eps, True, 0)}" + (f"，上季 {fmt(f.get('eps_yoy_prev'), True, 0)}" if f.get("eps_yoy_prev") is not None else ""), weight),
        Condition(f"基本面：最新季度营收同比 ≥ {rev_min:.0%}", None if rev is None else bool(rev >= rev_min),
                  f"营收同比 {fmt(rev, True, 0)}" + (f"，上季 {fmt(f.get('rev_yoy_prev'), True, 0)}" if f.get("rev_yoy_prev") is not None else ""), weight),
    ]
    if want_accel:
        acc = f.get("eps_accel")
        out.append(Condition("基本面：EPS 增速加速（本季同比 > 上季同比）", None if acc is None else bool(acc), "", weight * 0.5))
    return out


def fmt(v, pct=False, nd=2) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    return f"{v * 100:.{nd}f}%" if pct else f"{v:.{nd}f}"

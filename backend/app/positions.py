"""用户实际持仓：data/positions.json。每笔 {symbol, shares, cost, date, strategy, note}。"""
from __future__ import annotations

import json

import pandas as pd

from . import db, data, market, scanner, universe
from .config import DATA_DIR
from .strategies import STRATEGIES

PATH = DATA_DIR / "positions.json"


def load() -> list[dict]:
    if PATH.exists():
        try:
            return json.loads(PATH.read_text())
        except Exception:  # noqa: BLE001
            pass
    return []


def save(items: list[dict]) -> None:
    PATH.write_text(json.dumps(items, indent=1, ensure_ascii=False))


def upsert(p: dict) -> list[dict]:
    items = [x for x in load() if x["symbol"] != p["symbol"].upper()]
    items.insert(0, {
        "symbol": p["symbol"].upper(), "shares": float(p["shares"]), "cost": float(p["cost"]),
        "date": p.get("date") or pd.Timestamp.today().strftime("%Y-%m-%d"),
        "strategy": p.get("strategy") if p.get("strategy") in STRATEGIES else "consensus",
        "note": p.get("note") or "",
    })
    save(items)
    return items


def remove(symbol: str) -> list[dict]:
    items = [x for x in load() if x["symbol"] != symbol.upper()]
    save(items)
    return items


def advice_for(pos: dict, df: pd.DataFrame, ctx: dict) -> dict:
    """用该持仓指定的策略评估：规则现在要你怎么做。"""
    strat = STRATEGIES[pos["strategy"]]
    res = strat.evaluate(df, ctx, pos["symbol"], history_days=400)
    entry = pd.Timestamp(pos["date"])
    close = float(df["Close"].iloc[-1])
    since = [s for s in res.signals if pd.Timestamp(s.date) >= entry - pd.Timedelta(days=1)]
    last_sell = next((s for s in reversed(since) if s.type == "sell"), None)
    last_buy = next((s for s in reversed(since) if s.type == "buy"), None)
    stop = res.levels.get("stop")
    if last_sell and (not last_buy or last_sell.date > last_buy.date):
        action, reason = "离场", f"{strat.name} 在 {last_sell.date} 已发出卖出（{last_sell.label} @ {last_sell.price}），规则要求离场"
    elif res.signal == "sell":
        action, reason = "离场", f"今天触发卖出：{res.last_signal.label if res.last_signal else ''}"
    elif res.signal in ("buy", "hold") or (last_buy and not last_sell):
        action = "持有"
        reason = f"{strat.name} 持仓中，{res.state}" + (f"；止损 {stop}（距 {(stop / close - 1) * 100:+.1f}%）" if stop else "")
    else:
        action = "无确认"
        reason = f"{strat.name} 自 {pos['date']} 起没有给过买入，当前状态：{res.state}" + (f"；参考止损 {stop}" if stop else "")
    return {"action": action, "reason": reason, "state": res.state, "signal": res.signal, "stop": stop, "score": res.score,
            "strategy_name": strat.name}


def enriched() -> list[dict]:
    items = load()
    if not items:
        return []
    syms = [p["symbol"] for p in items]
    data.ensure_prices(syms + ["SPY"])
    prices = db.load_all_prices(syms)
    spy = db.load_prices("SPY")
    base = market.benchmark_context(spy)
    base["_universe"] = universe.load_universe()
    base["_sector_ranks"] = db.get_sector_ranks()
    out = []
    for p in items:
        df = prices.get(p["symbol"])
        row = dict(p)
        if df is None or df.empty:
            row.update({"error": "no data"})
            out.append(row)
            continue
        close = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
        value = close * p["shares"]
        pnl = (close - p["cost"]) * p["shares"]
        row.update({
            "close": round(close, 2), "chg1d": round(close / prev - 1, 4), "value": round(value, 2),
            "pnl": round(pnl, 2), "pnl_pct": round(close / p["cost"] - 1, 4),
            "days": int((pd.Timestamp.today().normalize() - pd.Timestamp(p["date"])).days),
        })
        try:
            row["advice"] = advice_for(p, df, scanner.build_ctx(p["symbol"], base))
            rs = db.get_rs(p["symbol"])
            row["rs"] = rs["rs_rank"] if rs else None
        except Exception as e:  # noqa: BLE001
            row["advice"] = {"action": "?", "reason": str(e)}
        out.append(row)
    return out

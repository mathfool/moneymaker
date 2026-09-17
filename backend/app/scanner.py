"""Universe scan: refresh prices, compute RS / sector ranks, evaluate every strategy on every symbol."""
from __future__ import annotations

import threading
import traceback
import time

import pandas as pd

from . import db, data, universe, fundamentals
from .indicators import rs_score, pct_rank
from .market import benchmark_context
from .strategies import STRATEGIES

status = {"running": False, "phase": "idle", "done": 0, "total": 0, "started": None, "finished": None, "error": None}
_thread: threading.Thread | None = None


def build_ctx(symbol: str, base_ctx: dict) -> dict:
    ctx = dict(base_ctx)
    ctx["fund"] = fundamentals.get(symbol, refresh=base_ctx.get("_fetch_fund", False))
    rs = db.get_rs(symbol)
    sectors = base_ctx.get("_sector_ranks") or db.get_sector_ranks()
    if rs:
        ctx["rs_rank"] = rs["rs_rank"]
        ctx["sector"] = rs["sector"]
        sr = sectors.get(rs["sector"])
        ctx["sector_rank"] = sr["rank"] if sr else None
        ctx["sector_total"] = len(sectors) or None
    else:
        ctx["rs_rank"] = None
        ctx["sector"] = sector_of(symbol, base_ctx.get("_universe", {}))
        ctx["sector_rank"] = None
        ctx["sector_total"] = len(sectors) or None
    return ctx


YF_TO_GICS = {
    "Technology": "Information Technology", "Healthcare": "Health Care", "Financial Services": "Financials",
    "Consumer Cyclical": "Consumer Discretionary", "Consumer Defensive": "Consumer Staples", "Basic Materials": "Materials",
    "Communication Services": "Communication Services", "Industrials": "Industrials", "Energy": "Energy",
    "Real Estate": "Real Estate", "Utilities": "Utilities",
}


def sector_of(symbol: str, uni: dict[str, dict]) -> str:
    sec = uni.get(symbol, {}).get("sector") or "Unknown"
    if sec in ("Unknown", "nan", ""):
        f = fundamentals.get(symbol, refresh=False) or {}
        sec = YF_TO_GICS.get(f.get("yf_sector") or "", f.get("yf_sector") or "Unknown")
    return sec


def compute_rs(prices: dict[str, pd.DataFrame], uni: dict[str, dict]) -> None:
    scores = {s: rs_score(df["Close"]) for s, df in prices.items() if len(df) >= 60}
    ranks = pct_rank(scores)
    rows = [(s, float(scores[s]), ranks[s], sector_of(s, uni)) for s in ranks]
    db.save_rs(rows)
    # sector rank by mean rs score
    by_sec: dict[str, list[float]] = {}
    for s, sc, _, sec in rows:
        by_sec.setdefault(sec, []).append(sc)
    sec_scores = {sec: sum(v) / len(v) for sec, v in by_sec.items() if sec and sec != "Unknown"}
    ordered = sorted(sec_scores.items(), key=lambda kv: kv[1], reverse=True)
    db.save_sector_rank([(sec, float(sc), i + 1) for i, (sec, sc) in enumerate(ordered)])


def run_scan(extra_symbols: list[str] | None = None) -> None:
    global status
    status.update(running=True, phase="universe", done=0, total=0, started=time.time(), finished=None, error=None)
    try:
        uni = universe.load_universe()
        syms = list(uni.keys())
        for s in extra_symbols or []:
            if s not in uni:
                syms.append(s)
        syms = list(dict.fromkeys(syms + ["SPY", "QQQ"]))
        status.update(phase="prices", total=len(syms))

        def prog(done, total):
            status.update(done=done, total=total)

        data.ensure_prices(syms, progress=prog)
        status.update(phase="fundamentals", done=0, total=len(syms))
        fundamentals.ensure_many([s for s in syms if s not in ("SPY", "QQQ")], progress=prog)
        status.update(phase="rs")
        prices = db.load_all_prices(syms)
        compute_rs({s: d for s, d in prices.items() if s not in ("SPY", "QQQ")}, uni)
        spy = prices.get("SPY")
        base_ctx = benchmark_context(spy)
        base_ctx["_sector_ranks"] = db.get_sector_ranks()
        base_ctx["_universe"] = uni
        status.update(phase="strategies", done=0, total=len(prices))
        results: dict[str, dict[str, dict]] = {k: {} for k in STRATEGIES}
        for i, (s, df) in enumerate(prices.items()):
            if s in ("SPY", "QQQ") or len(df) < 120:
                continue
            ctx = build_ctx(s, base_ctx)
            close = float(df["Close"].iloc[-1])
            chg = float(df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1)
            for key, strat in STRATEGIES.items():
                try:
                    r = strat.evaluate(df, ctx, s, history_days=260)
                except Exception as e:  # noqa: BLE001
                    print("eval error", key, s, e)
                    continue
                ls = r.last_signal
                results[key][s] = {
                    "state": r.state, "score": r.score, "signal": r.signal,
                    "last_signal": {"date": ls.date, "type": ls.type, "label": ls.label, "price": ls.price} if ls else None,
                    "close": round(close, 2), "chg1d": round(chg, 4),
                    "rs": ctx.get("rs_rank"), "sector": ctx.get("sector"),
                    "passed": sum(1 for c in r.conditions if c.passed), "total": len(r.conditions),
                    "buy_signals_1y": sum(1 for x in r.signals if x.type == "buy"),
                    "industry": (ctx.get("fund") or {}).get("industry"),
                    "eps_yoy": (ctx.get("fund") or {}).get("eps_yoy"), "rev_yoy": (ctx.get("fund") or {}).get("rev_yoy"),
                    "market_cap": (ctx.get("fund") or {}).get("market_cap"), "days_to_earnings": (ctx.get("fund") or {}).get("days_to_earnings"),
                }
            status.update(done=i + 1)
        for key, res in results.items():
            db.save_scan(key, res)
        status.update(phase="done")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        status.update(error=str(e), phase="error")
    finally:
        status.update(running=False, finished=time.time())


def start_scan(extra_symbols: list[str] | None = None) -> bool:
    global _thread
    if status["running"]:
        return False
    _thread = threading.Thread(target=run_scan, args=(extra_symbols,), daemon=True)
    _thread.start()
    return True

from __future__ import annotations

import math
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from . import db, data, universe, watchlist, scanner, backtest, market, fundamentals
from .strategies import STRATEGIES, get_strategy

app = FastAPI(title="moneymaker", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _clean(o):
    """Replace NaN/inf with None so JSON encoding never fails."""
    if isinstance(o, float):
        return None if not math.isfinite(o) else o
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


@app.get("/api/strategies")
def strategies():
    return [{"key": s.key, "name": s.name, "style": s.style, "description": s.description, "colors": s.overlay_colors}
            for s in STRATEGIES.values()]


@app.get("/api/market")
def market_summary():
    return _clean(market.market_summary())


@app.get("/api/watchlist")
def get_watchlist(strategy: str = Query("minervini")):
    syms = watchlist.load()
    return _clean(_rows_for(syms, strategy))


def _rows_for(syms: list[str], strategy: str) -> list[dict]:
    """Quick rows for the sidebar. Uses cached scan results when fresh, else evaluates on the fly."""
    strat = get_strategy(strategy)
    data.ensure_prices(syms + ["SPY"])
    cached = {r["symbol"]: r for r in db.load_scan(strategy)}
    prices = db.load_all_prices(syms)
    spy = prices.get("SPY") if "SPY" in prices else db.load_prices("SPY")
    base_ctx = market.benchmark_context(spy)
    base_ctx["_sector_ranks"] = db.get_sector_ranks()
    base_ctx["_universe"] = universe.load_universe()
    rows = []
    for s in syms:
        df = prices.get(s)
        if df is None or df.empty:
            rows.append({"symbol": s, "error": "no data"})
            continue
        last_date = df.index[-1].strftime("%Y-%m-%d")
        c = cached.get(s)
        if c and c.get("updated") and c["updated"][:10] >= last_date and c.get("close") == round(float(df["Close"].iloc[-1]), 2):
            rows.append(c)
            continue
        try:
            r = strat.evaluate(df, scanner.build_ctx(s, base_ctx), s, history_days=260)
        except Exception as e:  # noqa: BLE001
            rows.append({"symbol": s, "error": str(e)})
            continue
        ls = r.last_signal
        rows.append({
            "symbol": s, "state": r.state, "score": r.score, "signal": r.signal,
            "last_signal": {"date": ls.date, "type": ls.type, "label": ls.label, "price": ls.price} if ls else None,
            "close": round(float(df["Close"].iloc[-1]), 2), "chg1d": round(float(df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1), 4),
            "rs": base_ctx.get("rs_rank"), "sector": None,
            "passed": sum(1 for x in r.conditions if x.passed), "total": len(r.conditions),
        })
        rs = db.get_rs(s)
        if rs:
            rows[-1]["rs"], rows[-1]["sector"] = rs["rs_rank"], rs["sector"]
        f = (scanner.build_ctx(s, base_ctx).get("fund")) or {}
        rows[-1].update({"eps_yoy": f.get("eps_yoy"), "rev_yoy": f.get("rev_yoy"), "market_cap": f.get("market_cap"), "days_to_earnings": f.get("days_to_earnings")})
    return rows


@app.post("/api/watchlist/{symbol}")
def add_watch(symbol: str):
    info = data.lookup(symbol)
    if not info:
        raise HTTPException(404, f"找不到 {symbol.upper()} 的行情数据")
    return {"watchlist": watchlist.add(symbol), "info": info}


@app.delete("/api/watchlist/{symbol}")
def del_watch(symbol: str):
    return {"watchlist": watchlist.remove(symbol)}


@app.get("/api/stock/{symbol}")
def stock(symbol: str, strategy: str = Query("minervini"), days: int = Query(400)):
    symbol = symbol.upper()
    strat = get_strategy(strategy)
    df = data.get_daily(symbol)
    if df.empty:
        raise HTTPException(404, f"找不到 {symbol} 的行情数据")
    spy = data.get_daily("SPY")
    base_ctx = market.benchmark_context(spy)
    base_ctx["_universe"] = universe.load_universe()
    base_ctx["_fetch_fund"] = True
    ctx = scanner.build_ctx(symbol, base_ctx)
    res = strat.evaluate(df, ctx, symbol, history_days=days)
    tail = df.tail(days)
    candles = [
        {"time": t.strftime("%Y-%m-%d"), "open": round(float(r.Open), 4), "high": round(float(r.High), 4),
         "low": round(float(r.Low), 4), "close": round(float(r.Close), 4), "volume": float(r.Volume)}
        for t, r in zip(tail.index, tail.itertuples())
    ]
    # all-strategy summary chips
    summary = []
    for k, s in STRATEGIES.items():
        try:
            rr = s.evaluate(df, ctx, symbol, history_days=1) if k != strategy else res
            summary.append({"key": k, "name": s.name, "state": rr.state, "score": rr.score, "signal": rr.signal})
        except Exception as e:  # noqa: BLE001
            summary.append({"key": k, "name": s.name, "state": f"error: {e}", "score": 0, "signal": "none"})
    uni = base_ctx["_universe"].get(symbol, {})
    return _clean({
        "symbol": symbol, "candles": candles, "result": res.to_dict(), "summary": summary,
        "rs": ctx.get("rs_rank"), "sector": ctx.get("sector") or uni.get("sector"),
        "sector_rank": ctx.get("sector_rank"), "sector_total": ctx.get("sector_total"),
        "market": {"stage": base_ctx.get("benchmark_stage")},
        "fundamentals": ctx.get("fund"),
    })


@app.get("/api/backtest/{symbol}")
def bt(symbol: str, strategy: str = Query("minervini"), days: int = Query(750)):
    symbol = symbol.upper()
    strat = get_strategy(strategy)
    df = data.get_daily(symbol)
    if df.empty:
        raise HTTPException(404, "no data")
    spy = data.get_daily("SPY")
    base_ctx = market.benchmark_context(spy)
    base_ctx["_universe"] = universe.load_universe()
    comp = strat.compute(df, scanner.build_ctx(symbol, base_ctx))
    return _clean(backtest.run(comp, symbol, lookback_days=days))


@app.get("/api/backtest_all/{symbol}")
def bt_all(symbol: str, days: int = Query(750)):
    return {k: bt(symbol, k, days) for k in STRATEGIES}


@app.get("/api/scan")
def scan(strategy: str = Query("minervini"), min_score: float = Query(0), limit: int = Query(200)):
    rows = db.load_scan(strategy)
    rows = [r for r in rows if r.get("score", 0) >= min_score]
    rows.sort(key=lambda r: (r.get("signal") == "buy", r.get("score", 0), r.get("rs") or 0), reverse=True)
    return _clean({"rows": rows[:limit], "total": len(rows), "status": scanner.status})


@app.get("/api/sectors")
def sectors():
    """Sector strength ranking (mean RS score of members) plus member counts."""
    ranks = db.get_sector_ranks()
    counts: dict[str, int] = {}
    for v in db.get_all_rs().values():
        counts[v["sector"]] = counts.get(v["sector"], 0) + 1
    out = [{"sector": sec, "rank": r["rank"], "rs_score": round(r["rs_score"], 3), "count": counts.get(sec, 0)} for sec, r in ranks.items()]
    for sec, n in counts.items():
        if sec not in ranks:
            out.append({"sector": sec, "rank": None, "rs_score": None, "count": n})
    out.sort(key=lambda x: (x["rank"] is None, x["rank"] or 0))
    return out


@app.get("/api/consensus")
def consensus(min_support: int = Query(3), mode: str = Query("buyhold"), score_min: float = Query(70)):
    """Stocks that several strategies support at once. mode=buyhold: signal is buy/hold; mode=score: score >= score_min."""
    per: dict[str, dict] = {}
    for key in STRATEGIES:
        for r in db.load_scan(key):
            row = per.setdefault(r["symbol"], {"symbol": r["symbol"], "close": r.get("close"), "chg1d": r.get("chg1d"), "rs": r.get("rs"),
                                               "sector": r.get("sector"), "industry": r.get("industry"), "eps_yoy": r.get("eps_yoy"), "rev_yoy": r.get("rev_yoy"),
                                               "days_to_earnings": r.get("days_to_earnings"), "strategies": {}, "updated": r.get("updated")})
            supports = (r.get("signal") in ("buy", "hold")) if mode == "buyhold" else (r.get("score", 0) >= score_min)
            row["strategies"][key] = {"signal": r.get("signal"), "score": r.get("score"), "state": r.get("state"),
                                      "last_signal": r.get("last_signal"), "supports": supports}
    rows = []
    for row in per.values():
        row["support"] = sum(1 for v in row["strategies"].values() if v["supports"])
        row["fresh_buys"] = sum(1 for v in row["strategies"].values() if v["signal"] == "buy")
        row["score"] = round(sum(v["score"] or 0 for v in row["strategies"].values()) / max(1, len(row["strategies"])), 1)
        if row["support"] >= min_support:
            rows.append(row)
    rows.sort(key=lambda r: (r["support"], r["fresh_buys"], r["score"], r["rs"] or 0), reverse=True)
    return _clean({"rows": rows, "total": len(rows), "status": scanner.status})


@app.post("/api/scan/run")
def scan_run():
    started = scanner.start_scan(watchlist.load())
    return {"started": started, "status": scanner.status}


@app.get("/api/scan/status")
def scan_status():
    return scanner.status


@app.get("/api/universe")
def get_universe():
    return universe.load_universe()


@app.get("/api/search")
def search(q: str = Query(...)):
    q = q.upper().strip()
    uni = universe.load_universe()
    hits = [s for s in uni if s.startswith(q)][:15]
    return hits


# ---- serve the built frontend if present -----------------------------------
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.exists() and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")

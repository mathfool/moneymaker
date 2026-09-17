"""Quick aggregate backtest across a basket of symbols: python tools/eval.py [strategy ...]"""
import sys, statistics as st
sys.path.insert(0, ".")
from app import db, data, universe, market, scanner, backtest
from app.strategies import STRATEGIES

SYMS = ["NVDA", "AAPL", "MSFT", "TSLA", "AMD", "META", "PLTR", "AVGO", "NFLX", "COST", "CRWD", "APP", "HOOD", "VRT",
        "LLY", "JPM", "XOM", "KO", "MU", "ANET", "GE", "AXON", "NFLX", "ORCL", "SMCI", "COIN", "UBER", "SHOP", "NOW", "PG"]


def main(keys):
    syms = list(dict.fromkeys(SYMS))
    data.ensure_prices(syms + ["SPY"])
    prices = db.load_all_prices(syms)
    spy = db.load_prices("SPY")
    base = market.benchmark_context(spy)
    base["_universe"] = universe.load_universe()
    base["_sector_ranks"] = db.get_sector_ranks()
    for k in keys:
        s = STRATEGIES[k]
        rows = []
        for sym in syms:
            if sym not in prices:
                continue
            comp = s.compute(prices[sym], scanner.build_ctx(sym, base))
            rows.append(backtest.run(comp, sym, lookback_days=750))
        allt = [t for r in rows for t in r["trade_list"]]
        wins = [t for t in allt if t["ret"] > 0]
        losses = [t for t in allt if t["ret"] <= 0]
        n = len(allt)
        pf = sum(t["ret"] for t in wins) / max(1e-9, -sum(t["ret"] for t in losses))
        reasons = {}
        for t in allt:
            reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
        print(f"== {k:10s} trades={n:4d} win={len(wins)/max(1,n):.0%} avgR={st.mean([t['r'] for t in allt]) if allt else 0:+.2f} "
              f"avg={st.mean([t['ret'] for t in allt])*100 if allt else 0:+.1f}% avgWin={st.mean([t['ret'] for t in wins])*100 if wins else 0:+.1f}% "
              f"avgLoss={st.mean([t['ret'] for t in losses])*100 if losses else 0:+.1f}% PF={pf:.2f} "
              f"median_stock_ret={st.median([r['total_return'] for r in rows])*100:+.0f}% exits={reasons}")
        if "-v" in sys.argv:
            print("   ", " ".join(f"{r['symbol']}:{r['trades']}t/{r['total_return']*100:+.0f}%" for r in rows))


if __name__ == "__main__":
    keys = [a for a in sys.argv[1:] if a in STRATEGIES] or list(STRATEGIES)
    main(keys)

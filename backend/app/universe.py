"""Stock universe: S&P 500 + Nasdaq-100 constituents (cached to JSON)."""
import io
import json
import time

import pandas as pd
import requests

from .config import UNIVERSE_CACHE

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) moneymaker/0.1"}

# Fallback when Wikipedia is unreachable.
FALLBACK = {
    "AAPL": "Information Technology", "MSFT": "Information Technology", "NVDA": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services", "META": "Communication Services",
    "TSLA": "Consumer Discretionary", "AVGO": "Information Technology", "AMD": "Information Technology",
    "NFLX": "Communication Services", "COST": "Consumer Staples", "PLTR": "Information Technology",
    "CRWD": "Information Technology", "PANW": "Information Technology", "ANET": "Information Technology",
    "LLY": "Health Care", "UNH": "Health Care", "JPM": "Financials", "V": "Financials", "MA": "Financials",
    "XOM": "Energy", "CVX": "Energy", "HD": "Consumer Discretionary", "CAT": "Industrials", "GE": "Industrials",
    "ORCL": "Information Technology", "APP": "Information Technology", "VRT": "Industrials", "AXON": "Industrials",
    "HOOD": "Financials", "COIN": "Financials", "MSTR": "Information Technology", "SMCI": "Information Technology",
    "TSM": "Information Technology", "ASML": "Information Technology", "MU": "Information Technology",
}


def _fetch_sp500() -> dict[str, str]:
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=HEADERS, timeout=30)
    r.raise_for_status()
    t = pd.read_html(io.StringIO(r.text))[0]
    return {str(s).replace(".", "-").strip(): str(sec) for s, sec in zip(t["Symbol"], t["GICS Sector"])}


def _fetch_ndx() -> dict[str, str]:
    tables = []
    for url in ("https://www.slickcharts.com/nasdaq100", "https://stockanalysis.com/list/nasdaq-100-stocks/"):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            tables += pd.read_html(io.StringIO(r.text))
        except Exception as e:  # noqa: BLE001
            print("ndx fetch failed", url, e)
    for t in tables:
        cols = {str(c).lower(): c for c in t.columns}
        tick = next((cols[c] for c in cols if c in ("ticker", "symbol")), None)
        sec = next((cols[c] for c in cols if "sector" in c), None)
        if tick is not None and len(t) > 50:
            return {
                str(s).replace(".", "-").strip(): (str(t[sec][i]) if sec is not None else "Unknown")
                for i, s in enumerate(t[tick])
            }
    return {}


def load_universe(refresh: bool = False) -> dict[str, dict]:
    """Returns {symbol: {sector, indexes: [..]}}"""
    if UNIVERSE_CACHE.exists() and not refresh:
        age_days = (time.time() - UNIVERSE_CACHE.stat().st_mtime) / 86400
        if age_days < 7:
            return json.loads(UNIVERSE_CACHE.read_text())
    uni: dict[str, dict] = {}
    try:
        for s, sec in _fetch_sp500().items():
            uni[s] = {"sector": sec, "indexes": ["SPX"]}
    except Exception as e:  # noqa: BLE001
        print("S&P 500 fetch failed:", e)
    try:
        for s, sec in _fetch_ndx().items():
            if s in uni:
                uni[s]["indexes"].append("NDX")
            else:
                uni[s] = {"sector": sec, "indexes": ["NDX"]}
    except Exception as e:  # noqa: BLE001
        print("Nasdaq-100 fetch failed:", e)
    if len(uni) < 50:
        uni = {s: {"sector": sec, "indexes": ["FALLBACK"]} for s, sec in FALLBACK.items()}
    UNIVERSE_CACHE.write_text(json.dumps(uni, indent=1))
    return uni

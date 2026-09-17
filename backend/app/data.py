"""Price data: yfinance download with SQLite cache."""
import threading
import time

import pandas as pd
import yfinance as yf

from . import db
from .config import HISTORY_PERIOD, PRICE_MAX_AGE_HOURS

_fetch_lock = threading.Lock()


def _download_batch(symbols: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if not symbols:
        return out
    for attempt in range(3):
        try:
            raw = yf.download(
                symbols, period=HISTORY_PERIOD, auto_adjust=True, progress=False,
                threads=len(symbols) > 1, group_by="ticker",
            )
            break
        except Exception as e:  # noqa: BLE001
            print("yfinance error:", e)
            time.sleep(2 * (attempt + 1))
    else:
        return out
    if raw is None or raw.empty:
        return out
    if len(symbols) == 1:
        df = raw.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df = df[symbols[0]] if symbols[0] in df.columns.get_level_values(0) else df.droplevel(0, axis=1)
        out[symbols[0]] = df
        return out
    for s in symbols:
        if s in raw.columns.get_level_values(0):
            df = raw[s].dropna(subset=["Close"])
            if not df.empty:
                out[s] = df
    return out


def ensure_prices(symbols: list[str], max_age_hours: float = PRICE_MAX_AGE_HOURS, progress=None) -> None:
    """Make sure the cache has fresh data for every symbol. Downloads what is stale."""
    symbols = [s.upper() for s in dict.fromkeys(symbols)]
    meta = db.get_meta(symbols)
    now = pd.Timestamp.utcnow()
    stale = []
    for s in symbols:
        m = meta.get(s)
        if not m or not m.get("last_fetch"):
            stale.append(s)
            continue
        age = (now - pd.Timestamp(m["last_fetch"])).total_seconds() / 3600
        if age > max_age_hours:
            stale.append(s)
    if not stale:
        return
    with _fetch_lock:
        batch = 60
        for i in range(0, len(stale), batch):
            chunk = stale[i : i + batch]
            got = _download_batch(chunk)
            for s, df in got.items():
                db.upsert_prices(s, df)
            # Mark symbols that returned nothing so we don't retry every request.
            missing = [s for s in chunk if s not in got]
            for s in missing:
                one = _download_batch([s])
                if s in one:
                    db.upsert_prices(s, one[s])
            if progress:
                progress(min(i + batch, len(stale)), len(stale))


def get_daily(symbol: str, refresh: bool = True) -> pd.DataFrame:
    symbol = symbol.upper()
    if refresh:
        ensure_prices([symbol])
    return db.load_prices(symbol)


def lookup(symbol: str) -> dict | None:
    """Basic info for a symbol (used when adding to watchlist)."""
    symbol = symbol.upper()
    df = get_daily(symbol)
    if df.empty:
        return None
    try:
        info = yf.Ticker(symbol).fast_info
        name = None
        try:
            name = yf.Ticker(symbol).info.get("shortName")
        except Exception:  # noqa: BLE001
            pass
        return {"symbol": symbol, "name": name, "market_cap": getattr(info, "market_cap", None)}
    except Exception:  # noqa: BLE001
        return {"symbol": symbol, "name": None, "market_cap": None}

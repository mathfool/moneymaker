import json
import sqlite3
import threading
from contextlib import contextmanager

import pandas as pd

from .config import DB_PATH

_lock = threading.RLock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


_conn = _connect()


@contextmanager
def cursor():
    with _lock:
        cur = _conn.cursor()
        try:
            yield cur
            _conn.commit()
        finally:
            cur.close()


def init_db() -> None:
    with cursor() as cur:
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS prices (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL, volume REAL,
                PRIMARY KEY (symbol, date)
            );
            CREATE TABLE IF NOT EXISTS meta (
                symbol TEXT PRIMARY KEY,
                last_fetch TEXT,
                last_date TEXT
            );
            CREATE TABLE IF NOT EXISTS rs_rank (
                symbol TEXT PRIMARY KEY,
                rs_score REAL,
                rs_rank INTEGER,
                sector TEXT,
                updated TEXT
            );
            CREATE TABLE IF NOT EXISTS sector_rank (
                sector TEXT PRIMARY KEY,
                rs_score REAL,
                rank INTEGER,
                updated TEXT
            );
            CREATE TABLE IF NOT EXISTS fundamentals (
                symbol TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated TEXT
            );
            CREATE TABLE IF NOT EXISTS news (
                symbol TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated TEXT
            );
            CREATE TABLE IF NOT EXISTS scan_results (
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated TEXT,
                PRIMARY KEY (symbol, strategy)
            );
            """
        )


def upsert_prices(symbol: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if df.empty:
        return
    rows = [
        (symbol, idx.strftime("%Y-%m-%d"), float(o), float(h), float(l), float(c), float(v if v == v else 0))
        for idx, o, h, l, c, v in zip(df.index, df["Open"], df["High"], df["Low"], df["Close"], df["Volume"])
    ]
    with cursor() as cur:
        cur.executemany(
            "INSERT OR REPLACE INTO prices(symbol,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)", rows
        )
        cur.execute(
            "INSERT OR REPLACE INTO meta(symbol,last_fetch,last_date) VALUES (?,?,?)",
            (symbol, pd.Timestamp.utcnow().isoformat(), rows[-1][1]),
        )


def load_prices(symbol: str) -> pd.DataFrame:
    with _lock:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM prices WHERE symbol=? ORDER BY date",
            _conn,
            params=(symbol,),
        )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df


def load_all_prices(symbols: list[str]) -> dict[str, pd.DataFrame]:
    if not symbols:
        return {}
    out: dict[str, pd.DataFrame] = {}
    with _lock:
        q = "SELECT symbol, date, open, high, low, close, volume FROM prices WHERE symbol IN (%s) ORDER BY symbol, date" % (
            ",".join("?" * len(symbols))
        )
        df = pd.read_sql_query(q, _conn, params=symbols)
    if df.empty:
        return out
    df["date"] = pd.to_datetime(df["date"])
    for sym, g in df.groupby("symbol"):
        g = g.drop(columns="symbol").set_index("date")
        g.columns = ["Open", "High", "Low", "Close", "Volume"]
        out[sym] = g
    return out


def get_meta(symbols: list[str]) -> dict[str, dict]:
    if not symbols:
        return {}
    with cursor() as cur:
        q = "SELECT symbol,last_fetch,last_date FROM meta WHERE symbol IN (%s)" % ",".join("?" * len(symbols))
        return {s: {"last_fetch": lf, "last_date": ld} for s, lf, ld in cur.execute(q, symbols).fetchall()}


def save_rs(rows: list[tuple]) -> None:
    now = pd.Timestamp.utcnow().isoformat()
    with cursor() as cur:
        cur.executemany(
            "INSERT OR REPLACE INTO rs_rank(symbol,rs_score,rs_rank,sector,updated) VALUES (?,?,?,?,?)",
            [(s, sc, rk, sec, now) for s, sc, rk, sec in rows],
        )


def save_sector_rank(rows: list[tuple]) -> None:
    now = pd.Timestamp.utcnow().isoformat()
    with cursor() as cur:
        cur.execute("DELETE FROM sector_rank")
        cur.executemany(
            "INSERT OR REPLACE INTO sector_rank(sector,rs_score,rank,updated) VALUES (?,?,?,?)",
            [(sec, sc, rk, now) for sec, sc, rk in rows],
        )


def get_rs(symbol: str) -> dict | None:
    with cursor() as cur:
        row = cur.execute("SELECT rs_score, rs_rank, sector, updated FROM rs_rank WHERE symbol=?", (symbol,)).fetchone()
    if not row:
        return None
    return {"rs_score": row[0], "rs_rank": row[1], "sector": row[2], "updated": row[3]}


def get_all_rs() -> dict[str, dict]:
    with cursor() as cur:
        rows = cur.execute("SELECT symbol, rs_score, rs_rank, sector FROM rs_rank").fetchall()
    return {s: {"rs_score": sc, "rs_rank": rk, "sector": sec} for s, sc, rk, sec in rows}


def get_sector_ranks() -> dict[str, dict]:
    with cursor() as cur:
        rows = cur.execute("SELECT sector, rs_score, rank FROM sector_rank").fetchall()
    return {sec: {"rs_score": sc, "rank": rk} for sec, sc, rk in rows}


def save_fundamentals(symbol: str, data: dict) -> None:
    with cursor() as cur:
        cur.execute("INSERT OR REPLACE INTO fundamentals(symbol,payload,updated) VALUES (?,?,?)",
                    (symbol, json.dumps(data), pd.Timestamp.utcnow().isoformat()))


def get_fundamentals(symbol: str) -> dict | None:
    with cursor() as cur:
        row = cur.execute("SELECT payload, updated FROM fundamentals WHERE symbol=?", (symbol,)).fetchone()
    return {"data": json.loads(row[0]), "updated": row[1]} if row else None


def save_news(symbol: str, items: list[dict]) -> None:
    with cursor() as cur:
        cur.execute("INSERT OR REPLACE INTO news(symbol,payload,updated) VALUES (?,?,?)",
                    (symbol, json.dumps(items), pd.Timestamp.utcnow().isoformat()))


def get_news(symbol: str) -> dict | None:
    with cursor() as cur:
        row = cur.execute("SELECT payload, updated FROM news WHERE symbol=?", (symbol,)).fetchone()
    return {"items": json.loads(row[0]), "updated": row[1]} if row else None


def save_scan(strategy: str, results: dict[str, dict]) -> None:
    now = pd.Timestamp.utcnow().isoformat()
    with cursor() as cur:
        cur.executemany(
            "INSERT OR REPLACE INTO scan_results(symbol,strategy,payload,updated) VALUES (?,?,?,?)",
            [(s, strategy, json.dumps(p), now) for s, p in results.items()],
        )


def load_scan(strategy: str) -> list[dict]:
    with cursor() as cur:
        rows = cur.execute("SELECT symbol, payload, updated FROM scan_results WHERE strategy=?", (strategy,)).fetchall()
    out = []
    for s, p, u in rows:
        d = json.loads(p)
        d["symbol"] = s
        d["updated"] = u
        out.append(d)
    return out


init_db()

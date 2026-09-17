"""Technical indicators shared by all strategies. All functions are vectorized on a daily OHLCV DataFrame."""
import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def slope_pct(s: pd.Series, n: int) -> pd.Series:
    """Percent change of a series over n bars (used for MA slope)."""
    return s / s.shift(n) - 1


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    w = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    return w.dropna(subset=["Close"])


def rs_score(close: pd.Series) -> float | None:
    """IBD-style relative strength raw score: 2*3m + 6m + 9m + 12m returns."""
    if len(close) < 60:
        return None
    c = close.values

    def ret(days: int) -> float:
        if len(c) <= days:
            return c[-1] / c[0] - 1
        return c[-1] / c[-1 - days] - 1

    return 2 * ret(63) + ret(126) + ret(189) + ret(252)


def pct_rank(values: dict[str, float]) -> dict[str, int]:
    """Percentile rank 1..99 for each key."""
    items = [(k, v) for k, v in values.items() if v is not None and np.isfinite(v)]
    if not items:
        return {}
    s = pd.Series({k: v for k, v in items})
    r = s.rank(pct=True)
    return {k: int(max(1, min(99, round(v * 99)))) for k, v in r.items()}


def add_common(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the moving averages and helpers every strategy shares."""
    d = df.copy()
    c = d["Close"]
    d["sma10"] = sma(c, 10)
    d["sma20"] = sma(c, 20)
    d["sma50"] = sma(c, 50)
    d["sma150"] = sma(c, 150)
    d["sma200"] = sma(c, 200)
    d["ema10"] = ema(c, 10)
    d["ema20"] = ema(c, 20)
    d["ema21"] = ema(c, 21)
    d["ema50"] = ema(c, 50)
    d["atr14"] = atr(d, 14)
    d["vol50"] = sma(d["Volume"], 50)
    d["vol20"] = sma(d["Volume"], 20)
    d["hi52"] = d["High"].rolling(252, min_periods=60).max()
    d["lo52"] = d["Low"].rolling(252, min_periods=60).min()
    d["ret1"] = c.pct_change()
    return d

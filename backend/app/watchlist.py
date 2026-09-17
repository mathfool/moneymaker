import json

from .config import WATCHLIST_PATH, DEFAULT_WATCHLIST


def load() -> list[str]:
    if WATCHLIST_PATH.exists():
        try:
            return json.loads(WATCHLIST_PATH.read_text())
        except Exception:  # noqa: BLE001
            pass
    save(DEFAULT_WATCHLIST)
    return list(DEFAULT_WATCHLIST)


def save(items: list[str]) -> None:
    WATCHLIST_PATH.write_text(json.dumps(items, indent=1))


def add(symbol: str) -> list[str]:
    items = load()
    symbol = symbol.upper()
    if symbol not in items:
        items.insert(0, symbol)
        save(items)
    return items


def remove(symbol: str) -> list[str]:
    items = [s for s in load() if s != symbol.upper()]
    save(items)
    return items

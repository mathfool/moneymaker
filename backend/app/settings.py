"""全局设置：data/settings.json"""
import json

from .config import DATA_DIR

PATH = DATA_DIR / "settings.json"
DEFAULTS = {"market_filter": False, "market_filter_rule": "spy_above_50"}


def load() -> dict:
    d = dict(DEFAULTS)
    if PATH.exists():
        try:
            d.update(json.loads(PATH.read_text()))
        except Exception:  # noqa: BLE001
            pass
    return d


def update(patch: dict) -> dict:
    d = load()
    d.update({k: v for k, v in patch.items() if k in DEFAULTS})
    PATH.write_text(json.dumps(d, indent=1))
    return d

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "market.sqlite"
WATCHLIST_PATH = DATA_DIR / "watchlist.json"
UNIVERSE_CACHE = DATA_DIR / "universe.json"

HISTORY_PERIOD = "3y"        # how much daily history to keep per symbol
PRICE_MAX_AGE_HOURS = 6      # re-download if older than this
BENCHMARK = "SPY"
DEFAULT_WATCHLIST = ["NVDA", "AAPL", "MSFT", "TSLA", "AMD", "META", "PLTR", "AVGO", "NFLX", "COST"]

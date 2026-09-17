from .base import StrategyResult, Condition, Signal
from .minervini import Minervini
from .weinstein import Weinstein
from .kullamagi import Kullamagi
from .kell import OliverKell
from .jlaw import JLaw

STRATEGIES = {s.key: s for s in (Minervini(), Weinstein(), Kullamagi(), OliverKell(), JLaw())}


def get_strategy(key: str):
    if key not in STRATEGIES:
        raise KeyError(key)
    return STRATEGIES[key]

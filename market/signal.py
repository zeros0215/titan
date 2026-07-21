from enum import Enum


class MarketSignal(str, Enum):

    BULL = "BULL"

    SIDEWAYS = "SIDEWAYS"

    BEAR = "BEAR"
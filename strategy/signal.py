"""
Trading Signal
"""

from enum import Enum


class Signal(str, Enum):

    BUY = "BUY"

    HOLD = "HOLD"

    SELL = "SELL"
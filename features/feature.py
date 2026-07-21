"""
TITAN Feature Object
"""

from dataclasses import dataclass


@dataclass(slots=True)
class Feature:

    #
    # Price
    #
    close: float

    #
    # Moving Average
    #
    ma5: float
    ma20: float
    ma60: float
    ma120: float
    ma240: float

    #
    # Volume
    #
    volume: int
    volume_ma20: float
    volume_ratio: float

    #
    # Trading Value
    #
    trading_value: float
    trading_value_ma20: float

    #
    # Momentum
    #
    momentum5: float
    momentum20: float

    #
    # Volatility
    #
    atr14: float

    #
    # Breakout
    #
    highest20: float
    lowest20: float

    #
    # 52 Week
    #
    high52: float
    low52: float
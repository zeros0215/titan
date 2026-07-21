"""
TITAN Domain Enums
"""

from enum import Enum


class MarketType(str, Enum):
    """시장 구분"""

    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"
    ETF = "ETF"
    ETN = "ETN"


class Grade(str, Enum):
    """종목 등급"""

    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class SignalType(str, Enum):
    """Signal 종류"""

    TREND = "TREND"
    MOMENTUM = "MOMENTUM"
    VOLUME = "VOLUME"
    BREAKOUT = "BREAKOUT"
    RISK = "RISK"
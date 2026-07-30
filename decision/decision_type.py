from enum import Enum


class DecisionType(str, Enum):
    """
    최종 투자 의사결정
    """

    BUY = "BUY"

    WATCH = "WATCH"

    PASS = "PASS"
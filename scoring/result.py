"""
TITAN Score Result
"""

from dataclasses import dataclass


@dataclass(slots=True)
class ScoreResult:


    #
    # Detail Score
    #
    trend_score: int

    volume_score: int

    trading_score: int

    momentum_score: int

    breakout_score: int

    risk_penalty: int



    #
    # Raw Score
    #
    raw_score: int



    #
    # Normalized Score
    #
    normalized_score: int



    #
    # Grade
    #
    grade: str



    def __str__(self):

        return (

            "\n"

            f"Trend       : {self.trend_score}\n"

            f"Volume      : {self.volume_score}\n"

            f"Trading     : {self.trading_score}\n"

            f"Momentum    : {self.momentum_score}\n"

            f"Breakout    : {self.breakout_score}\n"

            f"Risk        : -{self.risk_penalty}\n"

            "-------------------------\n"

            f"RAW         : {self.raw_score}\n"

            f"SCORE       : {self.normalized_score}/100\n"

            f"GRADE       : {self.grade}"

        )
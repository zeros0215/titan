"""
TITAN Indicator Bundle

모든 Indicator 계산 결과를 하나의 객체로 묶는다.
Analyzer와 ScoreEngine은 이 객체만 사용한다.
"""

from dataclasses import dataclass

from indicators.breakout import BreakoutResult
from indicators.momentum import MomentumResult
from indicators.moving_average import MovingAverageResult
from indicators.risk import RiskResult
from indicators.volume import VolumeResult


@dataclass(slots=True)
class IndicatorBundle:
    """
    모든 Indicator 계산 결과
    """

    moving_average: MovingAverageResult

    momentum: MomentumResult

    volume: VolumeResult

    breakout: BreakoutResult

    risk: RiskResult

    rsi: float
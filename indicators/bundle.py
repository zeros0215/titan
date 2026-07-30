"""
TITAN Indicator Bundle
"""

from dataclasses import dataclass

from indicators.breakout_result import BreakoutResult
from indicators.momentum_result import MomentumResult
from indicators.moving_average_result import MovingAverageResult
from indicators.risk_result import RiskResult
from indicators.volume_result import VolumeResult


@dataclass(slots=True, frozen=True)
class IndicatorBundle:
    """
    모든 Indicator 계산 결과
    """

    moving_average: MovingAverageResult

    momentum: MomentumResult

    volume: VolumeResult

    breakout: BreakoutResult

    risk: RiskResult
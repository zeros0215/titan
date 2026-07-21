"""
Investment Features

Indicator를 투자 판단용 Feature로 변환한 결과
"""

from dataclasses import dataclass


@dataclass(slots=True)
class FeatureBundle:

    #
    # 0.0 ~ 1.0
    #
    trend_strength: float

    volume_strength: float

    momentum_strength: float

    breakout_strength: float

    risk_strength: float
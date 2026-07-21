from dataclasses import dataclass


@dataclass(slots=True)
class FeatureBundle:

    #
    # Trend
    #
    trend_strength: float

    #
    # Volume
    #
    volume_strength: float

    #
    # Momentum
    #
    momentum_strength: float

    #
    # Breakout
    #
    breakout_strength: float

    #
    # Risk
    #
    risk_strength: float
from dataclasses import dataclass

from .market_trend import MarketTrend


@dataclass(slots=True, frozen=True)
class MarketContext:

    kospi_trend: MarketTrend

    kosdaq_trend: MarketTrend

    market_strength: float

    sector_strength: float

    theme_strength: float

    foreign_flow: float

    institution_flow: float

    score: int = 0

    kospi_short_trend: MarketTrend | None = None

    kosdaq_short_trend: MarketTrend | None = None

    short_market_strength: float | None = None

from domain.candle_series import CandleSeries
from market.context.market_context import MarketContext
from market.context.market_strength import MarketStrengthCalculator
from market.context.market_trend import MarketTrend


class MarketContextBuilder:
    """Builds a market context from the OHLCV universe available to V1."""

    def __init__(self, lookback_days: int = 20) -> None:
        if lookback_days <= 0:
            raise ValueError("lookback_days must be greater than zero")
        self.lookback_days = lookback_days
        self.strength_calculator = MarketStrengthCalculator()

    def build(self, series_list: list[CandleSeries]) -> MarketContext:
        kospi = self._summarize(series_list, "KOSPI")
        kosdaq = self._summarize(series_list, "KOSDAQ")
        all_market = self._summarize(series_list)
        kospi_short = self._summarize(series_list, "KOSPI", 5)
        kosdaq_short = self._summarize(series_list, "KOSDAQ", 5)
        all_market_short = self._summarize(series_list, lookback_days=5)

        return MarketContext(
            kospi_trend=kospi[0],
            kosdaq_trend=kosdaq[0],
            market_strength=all_market[1],
            # These require sector/theme/flow providers, which V1 does not
            # yet collect. Keep them explicit rather than inventing signals.
            sector_strength=0.0,
            theme_strength=0.0,
            foreign_flow=0.0,
            institution_flow=0.0,
            score=self.strength_calculator.calculate_score(all_market[1]),
            kospi_short_trend=kospi_short[0],
            kosdaq_short_trend=kosdaq_short[0],
            short_market_strength=all_market_short[1],
        )

    def _summarize(
        self,
        series_list: list[CandleSeries],
        market: str | None = None,
        lookback_days: int | None = None,
    ) -> tuple[MarketTrend, float]:
        horizon = lookback_days or self.lookback_days
        returns = [
            self._return_rate(series, horizon)
            for series in series_list
            if self._matches_market(series, market)
            and len(series) > horizon
        ]
        if not returns:
            return MarketTrend.SIDEWAYS, 0.0

        advancing = sum(value > 0 for value in returns)
        declining = sum(value < 0 for value in returns)
        strength = self.strength_calculator.calculate_strength(
            advancing,
            declining,
        )
        average_return_percent = sum(returns) / len(returns) * 100
        trend = self.strength_calculator.determine_trend(
            average_return_percent,
        )
        return trend, strength

    def _return_rate(self, series: CandleSeries, lookback_days: int) -> float:
        start = series.closes[-lookback_days - 1]
        return series.latest.close / start - 1 if start else 0.0

    @staticmethod
    def _matches_market(
        series: CandleSeries,
        expected_market: str | None,
    ) -> bool:
        if expected_market is None:
            return True
        market = series.stock.market
        value = getattr(market, "value", market)
        return str(value).upper() == expected_market

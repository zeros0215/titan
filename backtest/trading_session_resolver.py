from datetime import datetime

from domain.candle_series import CandleSeries


class TradingSessionResolver:
    """Resolves holding horizons from observed market-session dates."""

    @staticmethod
    def resolve(
        series_by_code: dict[str, CandleSeries],
        selected_at: datetime,
        holding_days: list[int] | tuple[int, ...],
        as_of: datetime,
    ) -> dict[int, datetime]:
        horizons = sorted(set(holding_days))
        if not horizons or any(days <= 0 for days in horizons):
            raise ValueError("holding_days must contain positive values")
        sessions = sorted({
            candle.date
            for series in series_by_code.values()
            for candle in series.candles
            if selected_at < candle.date <= as_of
        })
        if len(sessions) < horizons[-1]:
            raise ValueError(
                f"insufficient market sessions: required {horizons[-1]}, "
                f"available {len(sessions)}"
            )
        return {days: sessions[days - 1] for days in horizons}

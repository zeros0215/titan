from dataclasses import dataclass
from datetime import datetime

from backtest.model.selection import Selection
from domain.candle_series import CandleSeries


@dataclass(slots=True, frozen=True)
class PriceResolution:
    selection_prices: dict[str, float]
    evaluation_prices: dict[str, float]


class CandlePriceResolver:
    """Resolves dated close prices without using candles after the target date."""

    def resolve(
        self,
        selections: list[Selection],
        series_by_code: dict[str, CandleSeries],
        evaluation_date: datetime,
        trade_time: str | None = None,
        sell_time: str | None = None,
    ) -> PriceResolution:
        selection_prices: dict[str, float] = {}
        evaluation_prices: dict[str, float] = {}

        for selection in selections:
            series = series_by_code.get(selection.code)
            if series is None:
                continue

            selection_price = self._resolve_buy_price(
                series,
                selection.selected_date,
                trade_time=trade_time,
            )
            evaluation_price = self._resolve_sell_price(
                series,
                evaluation_date,
                sell_time=sell_time,
            )
            if selection_price is not None:
                selection_prices[selection.code] = selection_price
            if evaluation_price is not None:
                evaluation_prices[selection.code] = evaluation_price

        return PriceResolution(selection_prices, evaluation_prices)

    @staticmethod
    def _resolve_buy_price(
        series: CandleSeries,
        target_date: datetime,
        trade_time: str | None = None,
    ) -> float | None:
        if trade_time is None:
            next_session = min(
                (
                    candle
                    for candle in series.candles
                    if candle.date > target_date
                ),
                key=lambda candle: candle.date,
                default=None,
            )
            return next_session.open if next_session is not None else None

        # Intraday execution requires intraday candles. Daily candles must not
        # pretend to provide an exact 10:00 (or other clock-time) price.
        raise ValueError(
            "trade_time requires intraday candles; daily OHLCV supports "
            "next-session open only"
        )

    @staticmethod
    def _resolve_sell_price(
        series: CandleSeries,
        target_date: datetime,
        sell_time: str | None = None,
    ) -> float | None:
        if sell_time is None:
            return CandlePriceResolver._close_on_or_before(series, target_date)

        eligible = [
            candle
            for candle in series.candles
            if candle.date <= target_date
        ]
        if not eligible:
            return None
        sell_target = CandlePriceResolver._closest_candle_at_or_after(
            eligible,
            target_date,
            sell_time,
        )
        if sell_target is not None:
            return sell_target.close
        return CandlePriceResolver._close_on_or_before(series, target_date)

    @staticmethod
    def _resolve_price(
        series: CandleSeries,
        target_date: datetime,
        trade_time: str | None = None,
        sell_time: str | None = None,
    ) -> float | None:
        if trade_time is None and sell_time is None:
            return CandlePriceResolver._close_on_or_before(series, target_date)

        eligible = [
            candle
            for candle in series.candles
            if candle.date <= target_date
        ]
        if not eligible:
            return None

        if trade_time is not None:
            next_session = CandlePriceResolver._next_session_candle(
                series,
                target_date,
                trade_time,
            )
            if next_session is not None:
                return next_session.close

        if sell_time is not None:
            sell_target = CandlePriceResolver._closest_candle_at_or_before(
                eligible,
                target_date,
                sell_time,
            )
            if sell_target is not None:
                return sell_target.close

        return max(eligible, key=lambda candle: candle.date).close

    @staticmethod
    def _close_on_or_before(
        series: CandleSeries,
        target_date: datetime,
    ) -> float | None:
        eligible = [
            candle
            for candle in series.candles
            if candle.date <= target_date
        ]
        return max(eligible, key=lambda candle: candle.date).close if eligible else None

    @staticmethod
    def _closest_candle_at_or_before(
        eligible: list,
        target_date: datetime,
        time_str: str,
    ):
        target_time = datetime.strptime(time_str, "%H:%M").time()
        target_dt = target_date.replace(hour=target_time.hour, minute=target_time.minute)
        for candle in reversed(eligible):
            candle_dt = candle.date
            if candle_dt <= target_dt:
                return candle
        return None

    @staticmethod
    def _closest_candle_at_or_after(
        eligible: list,
        target_date: datetime,
        time_str: str,
    ):
        target_time = datetime.strptime(time_str, "%H:%M").time()
        target_dt = target_date.replace(hour=target_time.hour, minute=target_time.minute)
        for candle in eligible:
            candle_dt = candle.date
            if candle_dt >= target_dt:
                return candle
        return None

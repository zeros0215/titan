from domain.candle_series import CandleSeries
from indicators.calculators.base_calculator import BaseCalculator
from indicators.volume_result import VolumeResult


class VolumeCalculator(BaseCalculator):

    def calculate(self, series: CandleSeries) -> VolumeResult:

        if len(series) < 20:
            raise ValueError("Need at least 20 candles.")

        latest = series.latest

        avg_volume = sum(series.volumes[-20:]) / 20

        avg_trading = sum(series.trading_values[-20:]) / 20

        ratio = (
            latest.volume / avg_volume
            if avg_volume > 0
            else 0
        )

        return VolumeResult(
            average_volume_20=avg_volume,
            current_volume=latest.volume,
            volume_ratio=ratio,
            average_trading_value_20=avg_trading,
            current_trading_value=latest.trading_value
        )
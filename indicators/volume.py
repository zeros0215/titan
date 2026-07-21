"""
Volume Indicator
"""

from dataclasses import dataclass

from domain.candle_series import CandleSeries



@dataclass(slots=True)
class VolumeResult:

    volume_ratio: float

    trading_value_ratio: float



def calculate(
    series: CandleSeries
) -> VolumeResult:


    volumes = series.volumes

    trading_values = series.trading_values


    if len(volumes) < 20:
        raise ValueError(
            "Need at least 20 candles"
        )


    volume_ma20 = (
        sum(volumes[-20:]) / 20
    )


    volume_ratio = (
        volumes[-1]
        /
        volume_ma20
    )


    trading_ma20 = (
        sum(trading_values[-20:])
        /
        20
    )


    trading_value_ratio = (
        trading_values[-1]
        /
        trading_ma20
    )


    return VolumeResult(

        volume_ratio=volume_ratio,

        trading_value_ratio=trading_value_ratio

    )
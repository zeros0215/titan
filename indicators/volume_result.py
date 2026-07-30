from dataclasses import dataclass


@dataclass(frozen=True)
class VolumeResult:
    """
    거래량 분석 결과
    """

    average_volume_20: float

    current_volume: float

    volume_ratio: float

    average_trading_value_20: float

    current_trading_value: float
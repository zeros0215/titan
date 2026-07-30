from domain.candle_series import CandleSeries

from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from feature.extractors.base_extractor import BaseFeatureExtractor

from indicators.bundle import IndicatorBundle


class VolumeFeatureExtractor(BaseFeatureExtractor):

    @staticmethod
    def normalize_strength(
        value: float,
        maximum: float,
    ) -> float:
        if maximum <= 0:
            return 0.0

        return min(abs(value) / maximum, 1.0)

    def extract(
        self,
        series: CandleSeries,
        indicators: IndicatorBundle,
        features: FeatureSet,
    ) -> None:

        volume = indicators.volume

        #
        # Volume Explosion
        #

        enabled = volume.volume_ratio >= 2.0

        self.add_feature(
            features=features,
            feature_type=FeatureType.VOLUME_EXPLOSION,
            enabled=enabled,
            strength=self.normalize_strength(
                volume.volume_ratio,
                3.0,
            ),
            value=volume.volume_ratio,
            positive_reason="거래량 급증",
            negative_reason="거래량 부족",
        )

        #
        # Trading Value
        #

        enabled = (
            volume.current_trading_value >=
            10_000_000_000
        )

        self.add_feature(
            features=features,
            feature_type=FeatureType.HIGH_TRADING_VALUE,
            enabled=enabled,
            strength=self.normalize_strength(
                volume.current_trading_value,
                50_000_000_000,
            ),
            value=volume.current_trading_value,
            positive_reason="거래대금 충분",
            negative_reason="거래대금 부족",
        )

        #
        # Volume Continuation
        #

        enabled = (
            volume.current_volume >
            volume.average_volume_20
        )

        self.add_feature(
            features=features,
            feature_type=FeatureType.VOLUME_CONTINUATION,
            enabled=enabled,
            strength=self.normalize_strength(
                volume.volume_ratio,
                2.0,
            ),
            value=volume.current_volume,
            positive_reason="평균 거래량 이상 유지",
            negative_reason="평균 거래량 이하",
        )

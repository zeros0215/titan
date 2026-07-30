from domain.candle_series import CandleSeries

from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from feature.extractors.base_extractor import BaseFeatureExtractor

from indicators.bundle import IndicatorBundle


class MomentumFeatureExtractor(BaseFeatureExtractor):

    def extract(
        self,
        series: CandleSeries,
        indicators: IndicatorBundle,
        features: FeatureSet,
    ) -> None:

        momentum = indicators.momentum

        #
        # 5 Day Momentum
        #

        enabled = momentum.momentum_5 >= 5.0

        self._add_feature(
            features=features,
            feature_type=FeatureType.HIGH_MOMENTUM_5D,
            enabled=enabled,
            strength=self._normalize_strength(
                momentum.momentum_5,
                10.0,
            ),
            value=momentum.momentum_5,
            positive_reason="5일 상승 모멘텀 우수",
            negative_reason="5일 상승 모멘텀 부족",
        )

        #
        # 20 Day Momentum
        #

        enabled = momentum.momentum_20 >= 15.0

        self._add_feature(
            features=features,
            feature_type=FeatureType.HIGH_MOMENTUM_20D,
            enabled=enabled,
            strength=self._normalize_strength(
                momentum.momentum_20,
                20.0,
            ),
            value=momentum.momentum_20,
            positive_reason="20일 상승 추세 유지",
            negative_reason="20일 상승 추세 부족",
        )

        #
        # Acceleration
        #

        enabled = momentum.acceleration > 0

        self._add_feature(
            features=features,
            feature_type=FeatureType.ACCELERATION,
            enabled=enabled,
            strength=self._normalize_strength(
                momentum.acceleration,
                10.0,
            ),
            value=momentum.acceleration,
            positive_reason="상승 가속도 증가",
            negative_reason="상승 가속도 부족",
        )

    @staticmethod
    def _normalize_strength(
        value: float,
        maximum: float,
    ) -> float:
        """
        strength를 0.0 ~ 1.0 범위로 정규화한다.
        """

        if maximum <= 0:
            return 0.0

        return min(abs(value) / maximum, 1.0)

    @staticmethod
    def _add_feature(
        features: FeatureSet,
        feature_type: FeatureType,
        enabled: bool,
        strength: float,
        value: float,
        positive_reason: str,
        negative_reason: str,
    ) -> None:

        features.add(
            Feature(
                type=feature_type,
                enabled=enabled,
                strength=strength,
                value=value,
                reason=(
                    positive_reason
                    if enabled
                    else negative_reason
                ),
            )
        )
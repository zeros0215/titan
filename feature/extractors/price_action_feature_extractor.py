from domain.candle_series import CandleSeries

from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from feature.extractors.base_extractor import BaseFeatureExtractor

from indicators.bundle import IndicatorBundle


class PriceActionFeatureExtractor(BaseFeatureExtractor):

    def extract(
        self,
        series: CandleSeries,
        indicators: IndicatorBundle,
        features: FeatureSet
    ):

        breakout = indicators.breakout

        #
        # NEW HIGH
        #

        enabled = breakout.position60 >= 1.0

        strength = (
            1.0
            if enabled
            else breakout.position60
        )

        self._add_feature(
            features=features,
            feature_type=FeatureType.NEW_HIGH,
            enabled=enabled,
            strength=strength,
            value=breakout.position60,
            positive_reason="60일 신고가 돌파",
            negative_reason="60일 신고가 미도달"
        )

        #
        # BREAKOUT 60
        #

        enabled = breakout.position60 >= 0.98

        strength = min(
            max(
                (breakout.position60 - 0.98) / 0.02,
                0.0
            ),
            1.0
        )

        self._add_feature(
            features=features,
            feature_type=FeatureType.BREAKOUT_60,
            enabled=enabled,
            strength=strength,
            value=breakout.position60,
            positive_reason="60일 고점 근접",
            negative_reason="60일 고점과 거리 있음"
        )

        #
        # BREAKOUT 20
        #

        enabled = breakout.position20 >= 1.0

        strength = (
            1.0
            if enabled
            else breakout.position20
        )

        self._add_feature(
            features=features,
            feature_type=FeatureType.BREAKOUT_20,
            enabled=enabled,
            strength=strength,
            value=breakout.position20,
            positive_reason="20일 신고가 돌파",
            negative_reason="20일 신고가 미도달"
        )

    @staticmethod
    def _add_feature(
        features: FeatureSet,
        feature_type: FeatureType,
        enabled: bool,
        strength: float,
        value: float,
        positive_reason: str,
        negative_reason: str
    ):

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
                )
            )
        )
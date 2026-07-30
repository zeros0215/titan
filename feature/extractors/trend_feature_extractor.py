from domain.candle_series import CandleSeries

from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from feature.extractors.base_extractor import BaseFeatureExtractor

from indicators.bundle import IndicatorBundle


class TrendFeatureExtractor(BaseFeatureExtractor):

    def extract(
        self,
        series: CandleSeries,
        indicators: IndicatorBundle,
        features: FeatureSet
    ):

        latest = series.latest
        ma = indicators.moving_average

        #
        # PRICE > MA20
        #

        enabled = latest.close > ma.ma20

        strength = (
            min(abs(latest.close - ma.ma20) / ma.ma20, 1.0)
            if ma.ma20 > 0 else 0.0
        )

        self._add_feature(
            features=features,
            feature_type=FeatureType.PRICE_ABOVE_MA20,
            enabled=enabled,
            strength=strength,
            value=latest.close,
            positive_reason="현재가가 MA20 위에 위치",
            negative_reason="현재가가 MA20 아래 위치"
        )

        #
        # PRICE > MA60
        #

        enabled = latest.close > ma.ma60

        strength = (
            min(abs(latest.close - ma.ma60) / ma.ma60, 1.0)
            if ma.ma60 > 0 else 0.0
        )

        self._add_feature(
            features=features,
            feature_type=FeatureType.PRICE_ABOVE_MA60,
            enabled=enabled,
            strength=strength,
            value=latest.close,
            positive_reason="현재가가 MA60 위에 위치",
            negative_reason="현재가가 MA60 아래 위치"
        )

        #
        # MA5 > MA20
        #

        enabled = ma.ma5 > ma.ma20

        strength = (
            min(abs(ma.ma5 - ma.ma20) / ma.ma20, 1.0)
            if ma.ma20 > 0 else 0.0
        )

        self._add_feature(
            features=features,
            feature_type=FeatureType.MA5_ABOVE_MA20,
            enabled=enabled,
            strength=strength,
            value=ma.ma5,
            positive_reason="단기 이동평균이 중기 이동평균 위에 위치",
            negative_reason="단기 이동평균이 중기 이동평균 아래 위치"
        )

        #
        # MA20 > MA60
        #

        enabled = ma.ma20 > ma.ma60

        strength = (
            min(abs(ma.ma20 - ma.ma60) / ma.ma60, 1.0)
            if ma.ma60 > 0 else 0.0
        )

        self._add_feature(
            features=features,
            feature_type=FeatureType.MA20_ABOVE_MA60,
            enabled=enabled,
            strength=strength,
            value=ma.ma20,
            positive_reason="중기 추세가 장기 추세보다 강함",
            negative_reason="중기 추세가 장기 추세보다 약함"
        )

        #
        # Golden Cross
        #

        enabled = (
            ma.prev_ma5 <= ma.prev_ma20
            and ma.ma5 > ma.ma20
        )

        self._add_feature(
            features=features,
            feature_type=FeatureType.GOLDEN_CROSS,
            enabled=enabled,
            strength=1.0 if enabled else 0.0,
            value=ma.ma5 - ma.ma20,
            positive_reason="골든크로스 발생",
            negative_reason="골든크로스 미발생"
        )

        #
        # Dead Cross
        #

        enabled = (
            ma.prev_ma5 >= ma.prev_ma20
            and ma.ma5 < ma.ma20
        )

        self._add_feature(
            features=features,
            feature_type=FeatureType.DEAD_CROSS,
            enabled=enabled,
            strength=1.0 if enabled else 0.0,
            value=ma.ma20 - ma.ma5,
            positive_reason="데드크로스 발생",
            negative_reason="데드크로스 미발생"
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
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

        # Research-only, point-in-time pullback signal. A breakout must have
        # occurred in one of the prior five sessions; today's close must hold
        # near that breakout close and above the current five-session average.
        breakouts = []
        for index in range(max(20, len(series) - 6), len(series) - 1):
            prior_high = max(series.highs[index - 20:index])
            if prior_high > 0 and series.closes[index] >= prior_high:
                average_volume = sum(
                    series.volumes[index - 20:index]
                ) / 20
                breakouts.append((
                    index,
                    series.closes[index],
                    average_volume > 0
                    and series.volumes[index] >= 1.5 * average_volume,
                ))
        breakout_index, reference, volume_confirmed = (
            breakouts[-1] if breakouts else (-1, 0.0, False)
        )
        ratio = series.closes[-1] / reference if reference > 0 else 0.0
        enabled = (
            reference > 0
            and 0.97 <= ratio <= 1.02
            and series.closes[-1] >= indicators.moving_average.ma5
        )
        self._add_feature(
            features=features,
            feature_type=FeatureType.RECENT_BREAKOUT_PULLBACK,
            enabled=enabled,
            strength=1.0 if enabled else 0.0,
            value=ratio,
            positive_reason="recent breakout pullback held",
            negative_reason="recent breakout pullback condition not met",
        )

        after_breakout = (
            series.closes[breakout_index + 1:-1]
            if breakout_index >= 0 else []
        )
        confirmed = (
            enabled
            and bool(after_breakout)
            and min(after_breakout) <= reference * 0.99
            and series.closes[-1] > series.closes[-2]
        )
        self._add_feature(
            features=features,
            feature_type=FeatureType.CONFIRMED_BREAKOUT_PULLBACK,
            enabled=confirmed,
            strength=1.0 if confirmed else 0.0,
            value=ratio,
            positive_reason="breakout, pullback, and rebound confirmed",
            negative_reason="pullback and rebound not confirmed",
        )
        self._add_feature(
            features=features,
            feature_type=FeatureType.VOLUME_CONFIRMED_BREAKOUT_PULLBACK,
            enabled=confirmed and volume_confirmed,
            strength=1.0 if confirmed and volume_confirmed else 0.0,
            value=ratio,
            positive_reason="volume breakout, pullback, and rebound confirmed",
            negative_reason="volume-confirmed pullback condition not met",
        )

        prior20 = max(series.highs[-21:-1])
        previous_prior20 = max(series.highs[-22:-2])
        average_prior_volume = sum(series.volumes[-21:-1]) / 20
        first_volume_breakout = (
            prior20 > 0
            and series.closes[-1] >= prior20
            and series.closes[-2] < previous_prior20
            and average_prior_volume > 0
            and series.volumes[-1] >= 1.5 * average_prior_volume
        )
        self._add_feature(
            features=features,
            feature_type=FeatureType.FIRST_VOLUME_BREAKOUT_20,
            enabled=first_volume_breakout,
            strength=1.0 if first_volume_breakout else 0.0,
            value=series.closes[-1] / prior20 if prior20 > 0 else 0.0,
            positive_reason="first 20-session breakout with volume confirmation",
            negative_reason="first volume-confirmed breakout condition not met",
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

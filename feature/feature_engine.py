from domain.candle_series import CandleSeries

from feature.extractors.momentum_feature_extractor import MomentumFeatureExtractor
from feature.extractors.trend_feature_extractor import TrendFeatureExtractor
from feature.extractors.volume_feature_extractor import VolumeFeatureExtractor
from feature.extractors.price_action_feature_extractor import PriceActionFeatureExtractor
from feature.extractors.risk_feature_extractor import RiskFeatureExtractor

from feature.feature_set import FeatureSet

from indicators.bundle import IndicatorBundle


class FeatureEngine:

    def __init__(self) -> None:

        self.extractors = [

            TrendFeatureExtractor(),

            MomentumFeatureExtractor(),

            VolumeFeatureExtractor(),

            PriceActionFeatureExtractor(),

            RiskFeatureExtractor(),

        ]

    def extract(
        self,
        series: CandleSeries,
        indicators: IndicatorBundle,
    ) -> FeatureSet:

        features = FeatureSet()

        for extractor in self.extractors:

            extractor.extract(
                series,
                indicators,
                features,
            )

        return features

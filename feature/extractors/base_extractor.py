from abc import ABC
from abc import abstractmethod

from domain.candle_series import CandleSeries

from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType

from indicators.bundle import IndicatorBundle


class BaseFeatureExtractor(ABC):

    @abstractmethod
    def extract(
        self,
        series: CandleSeries,
        indicators: IndicatorBundle,
        features: FeatureSet
    ):
        pass

    def add_feature(
        self,
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
                reason=positive_reason if enabled else negative_reason
            )
        )
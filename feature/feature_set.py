from typing import Iterator

from feature.feature import Feature
from feature.feature_type import FeatureType


class FeatureSet:

    def __init__(self) -> None:
        self._features: dict[FeatureType, Feature] = {}

    def add(self, feature: Feature) -> None:
        self._features[feature.type] = feature

    def get(
        self,
        feature_type: FeatureType,
    ) -> Feature | None:
        return self._features.get(feature_type)

    def contains(
        self,
        feature_type: FeatureType,
    ) -> bool:

        feature = self.get(feature_type)

        return feature is not None and feature.enabled

    def all(self) -> list[Feature]:
        return list(self._features.values())

    def enabled(self) -> list[Feature]:
        return [
            feature
            for feature in self._features.values()
            if feature.enabled
        ]

    def disabled(self) -> list[Feature]:
        return [
            feature
            for feature in self._features.values()
            if not feature.enabled
        ]

    def __len__(self) -> int:
        return len(self._features)

    def __iter__(self) -> Iterator[Feature]:
        return iter(self._features.values())
from dataclasses import dataclass

from feature.feature_type import FeatureType


@dataclass(slots=True, frozen=True)
class Feature:
    """
    하나의 투자 신호(Feature)

    enabled : 조건 만족 여부
    strength : 0.0 ~ 1.0
    value : 실제 계산값
    reason : 사람이 이해할 수 있는 설명
    """

    type: FeatureType

    enabled: bool

    strength: float

    value: float

    reason: str = ""

    @staticmethod
    def create_enabled(
        feature_type: FeatureType,
        strength: float,
        value: float,
        reason: str = "",
    ) -> "Feature":

        return Feature(
            type=feature_type,
            enabled=True,
            strength=strength,
            value=value,
            reason=reason,
        )

    @staticmethod
    def create_disabled(
        feature_type: FeatureType,
        reason: str = "",
    ) -> "Feature":

        return Feature(
            type=feature_type,
            enabled=False,
            strength=0.0,
            value=0.0,
            reason=reason,
        )

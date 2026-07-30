from abc import ABC, abstractmethod

from feature.feature_set import FeatureSet


class BasePolicy(ABC):
    """
    모든 Score Policy의 기본 클래스
    """

    _FEATURE_SCORES: dict = {}
    MAX_SCORE: int | None = None

    @classmethod
    def max_score(cls) -> int:
        """
        Policy의 최대 점수
        """
        return cls.MAX_SCORE if cls.MAX_SCORE is not None else sum(cls._FEATURE_SCORES.values())

    @abstractmethod
    def calculate(
        self,
        features: FeatureSet,
    ) -> int:
        """
        FeatureSet을 기반으로 점수를 계산한다.
        """
        raise NotImplementedError

from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType

from scoring.policies.base_policy import BasePolicy
from scoring.policy_utils import PolicyUtils
from config.selection_criteria import (
    PRICE_ACTION_FEATURE_SCORES,
    PRICE_ACTION_MAX_SCORE,
)


class PriceActionPolicy(BasePolicy):
    """
    Price Action 기반 점수 계산

    Breakout을 포함한 모든 Price Action Feature를 평가한다.
    """

    _FEATURE_SCORES = PRICE_ACTION_FEATURE_SCORES
    MAX_SCORE = PRICE_ACTION_MAX_SCORE

    def calculate(
        self,
        features: FeatureSet,
    ) -> int:

        scores = []

        for feature_type, max_score in self._FEATURE_SCORES.items():

            if not features.contains(feature_type):
                continue

            scores.append(PolicyUtils.feature_score(features.get(feature_type), max_score))

        # Price action signals are highly correlated; use the strongest one.
        return min(max(scores, default=0), self.max_score())

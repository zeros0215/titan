from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType

from scoring.policies.base_policy import BasePolicy
from scoring.policy_utils import PolicyUtils
from config.selection_criteria import RISK_FEATURE_SCORES, RISK_MAX_SCORE


class RiskPolicy(BasePolicy):
    """
    리스크(Risk) 점수 계산
    """

    _FEATURE_SCORES = RISK_FEATURE_SCORES
    MAX_SCORE = RISK_MAX_SCORE

    def calculate(
        self,
        features: FeatureSet,
    ) -> int:

        score = 0

        for feature_type, max_score in self._FEATURE_SCORES.items():

            if not features.contains(feature_type):
                continue

            score += PolicyUtils.feature_score(
                features.get(feature_type),
                max_score,
            )

        return min(score, self.max_score())

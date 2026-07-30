from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType

from scoring.policies.base_policy import BasePolicy
from scoring.policy_utils import PolicyUtils
from config.selection_criteria import VOLUME_FEATURE_SCORES, VOLUME_MAX_SCORE


class VolumePolicy(BasePolicy):
    """
    거래량(Volume) 점수 계산
    """

    _FEATURE_SCORES = VOLUME_FEATURE_SCORES
    MAX_SCORE = VOLUME_MAX_SCORE

    def calculate(
        self,
        features: FeatureSet
    ) -> int:

        score = 0

        for feature_type, max_score in self._FEATURE_SCORES.items():

            if not features.contains(feature_type):
                continue

            score += PolicyUtils.feature_score(
                features.get(feature_type),
                max_score
            )

        return min(score, self.max_score())

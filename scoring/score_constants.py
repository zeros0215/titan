from scoring.policies.context_policy import ContextPolicy
from scoring.policies.momentum_policy import MomentumPolicy
from scoring.policies.price_action_policy import PriceActionPolicy
from scoring.policies.risk_policy import RiskPolicy
from scoring.policies.trend_policy import TrendPolicy
from scoring.policies.volume_policy import VolumePolicy


class ScoreConstants:
    """
    Score 관련 공통 상수
    """

    MAX_SCORE = (
        TrendPolicy.max_score()
        + MomentumPolicy.max_score()
        + VolumePolicy.max_score()
        + PriceActionPolicy.max_score()
        + RiskPolicy.max_score()
        + ContextPolicy.max_score()
    )
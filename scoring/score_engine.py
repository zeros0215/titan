from feature.feature_set import FeatureSet
from market.context.market_context import MarketContext

from scoring.score_result import ScoreResult

from scoring.policies.context_policy import ContextPolicy
from scoring.policies.momentum_policy import MomentumPolicy
from scoring.policies.price_action_policy import PriceActionPolicy
from scoring.policies.risk_policy import RiskPolicy
from scoring.policies.trend_policy import TrendPolicy
from scoring.policies.volume_policy import VolumePolicy


class ScoreEngine:
    """
    FeatureSet을 정책별로 평가하여 최종 점수를 계산한다.
    """

    def __init__(self) -> None:
        self.trend_policy = TrendPolicy()
        self.momentum_policy = MomentumPolicy()
        self.volume_policy = VolumePolicy()
        self.price_action_policy = PriceActionPolicy()
        self.risk_policy = RiskPolicy()
        self.context_policy = ContextPolicy()

    def calculate(
        self,
        features: FeatureSet,
        context: MarketContext | None = None,
    ) -> ScoreResult:

        trend_score = self.trend_policy.calculate(features)

        momentum_score = self.momentum_policy.calculate(features)

        volume_score = self.volume_policy.calculate(features)

        price_action_score = self.price_action_policy.calculate(features)

        risk_score = self.risk_policy.calculate(features)

        context_score = self.context_policy.calculate(context)

        return ScoreResult(
            trend_score=trend_score,
            momentum_score=momentum_score,
            volume_score=volume_score,
            price_action_score=price_action_score,
            risk_score=risk_score,
            context_score=context_score,
        )
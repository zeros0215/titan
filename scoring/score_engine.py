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

    def __init__(self, criteria=None) -> None:
        self.trend_policy = TrendPolicy()
        self.momentum_policy = MomentumPolicy()
        self.volume_policy = VolumePolicy()
        self.price_action_policy = PriceActionPolicy()
        self.risk_policy = RiskPolicy()
        self.context_policy = ContextPolicy()
        self.criteria = criteria

    def calculate(
        self,
        features: FeatureSet,
        context: MarketContext | None = None,
    ) -> ScoreResult:

        trend_score = self._weighted(
            self.trend_policy.calculate(features), 30, "trend_weight"
        )

        momentum_score = self._weighted(
            self.momentum_policy.calculate(features), 15, "momentum_weight"
        )

        volume_score = self._weighted(
            self.volume_policy.calculate(features), 15, "volume_weight"
        )

        price_action_score = self._weighted(
            self.price_action_policy.calculate(features), 15,
            "price_action_weight",
        )

        risk_score = self._weighted(
            self.risk_policy.calculate(features), 15, "risk_weight"
        )

        context_score = self._weighted(
            self.context_policy.calculate(context), 10, "context_weight"
        )

        return ScoreResult(
            trend_score=trend_score,
            momentum_score=momentum_score,
            volume_score=volume_score,
            price_action_score=price_action_score,
            risk_score=risk_score,
            context_score=context_score,
        )

    def _weighted(self, score: int, baseline: int, attribute: str) -> int:
        if self.criteria is None:
            return score
        weight = int(getattr(self.criteria, attribute, baseline))
        return min(weight, round(score * weight / baseline))

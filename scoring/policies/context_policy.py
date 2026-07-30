from market.context.market_context import MarketContext

from scoring.policies.base_policy import BasePolicy
from config.selection_criteria import CONTEXT_MAX_SCORE


class ContextPolicy(BasePolicy):
    """
    시장 상황(Context)을 점수화한다.

    최대 점수 : 20점
    """

    _FEATURE_SCORES = {
        "market": 10,
        "sector": 0,
        "theme": 0,
        "foreign": 0,
        "institution": 0,
    }
    MAX_SCORE = CONTEXT_MAX_SCORE

    def calculate(
        self,
        context: MarketContext | None,
    ) -> int:

        if context is None:
            return 0

        score = 0

        score += self._market_strength(context.market_strength)
        score += self._sector_strength(context.sector_strength)
        score += self._theme_strength(context.theme_strength)
        score += self._foreign_flow(context.foreign_flow)
        score += self._institution_flow(context.institution_flow)

        return min(score, self.max_score())

    def _market_strength(
        self,
        value: float,
    ) -> int:

        if value >= 0.8:
            return self._FEATURE_SCORES["market"]

        if value >= 0.6:
            return 7

        if value >= 0.5:
            return 3

        return 0

    def _sector_strength(
        self,
        value: float,
    ) -> int:

        if value >= 2:
            return self._FEATURE_SCORES["sector"]

        if value >= 1:
            return 2

        return 0

    def _theme_strength(
        self,
        value: float,
    ) -> int:

        if value >= 2:
            return self._FEATURE_SCORES["theme"]

        if value >= 1:
            return 2

        return 0

    def _foreign_flow(
        self,
        value: float,
    ) -> int:

        if value > 0:
            return self._FEATURE_SCORES["foreign"]

        return 0

    def _institution_flow(
        self,
        value: float,
    ) -> int:

        if value > 0:
            return self._FEATURE_SCORES["institution"]

        return 0

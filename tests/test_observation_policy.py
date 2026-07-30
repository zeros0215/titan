from datetime import datetime
from types import SimpleNamespace
import unittest

from config.observation_policy import ObservationPolicy
from scoring.score_result import ScoreResult


class ObservationPolicyTest(unittest.TestCase):
    def test_selects_only_bounded_70s_by_score_then_liquidity(self) -> None:
        analyses = [
            self._analysis("A", 79, 100),
            self._analysis("B", 79, 200),
            self._analysis("C", 75, 500),
            self._analysis("D", 80, 1_000),
            self._analysis("E", 69, 1_000),
        ]

        observations = ObservationPolicy(daily_limit=2).select(
            analyses,
            datetime(2026, 1, 2),
        )

        self.assertEqual([item.code for item in observations], ["B", "A"])
        self.assertEqual([item.rank for item in observations], [1, 2])

    @staticmethod
    def _analysis(code: str, score: int, trading_value: float):
        return SimpleNamespace(
            code=code,
            score=ScoreResult(trend_score=score),
            indicators=SimpleNamespace(
                volume=SimpleNamespace(current_trading_value=trading_value)
            ),
        )


if __name__ == "__main__":
    unittest.main()

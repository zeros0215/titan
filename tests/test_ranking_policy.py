from types import SimpleNamespace
import unittest

from decision.decision_type import DecisionType
from ranking.ranking_engine import RankingEngine


class RankingPolicyTest(unittest.TestCase):
    def test_orders_by_score_trading_value_then_code(self) -> None:
        analyses = [
            self._analysis("000003", 80, 30),
            self._analysis("000002", 80, 50),
            self._analysis("000001", 80, 50),
            self._analysis("000004", 85, 10),
        ]

        result = RankingEngine().rank(analyses)

        self.assertEqual(
            [item.analysis.code for item in result.items],
            ["000004", "000001", "000002", "000003"],
        )

    @staticmethod
    def _analysis(code, score, trading_value):
        return SimpleNamespace(
            code=code,
            decision=SimpleNamespace(decision=DecisionType.BUY),
            score=SimpleNamespace(normalized_score=score),
            indicators=SimpleNamespace(
                volume=SimpleNamespace(
                    current_trading_value=trading_value
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()

from datetime import datetime, timedelta
import unittest

from analysis.analysis_result import AnalysisResult
from backtest.engine.backtest_engine import BacktestEngine
from backtest.engine.selection_engine import SelectionEngine
from backtest.transaction_cost import TransactionCostPolicy
from ranking.ranking_item import RankingItem
from ranking.ranking_result import RankingResult
from scoring.score_result import ScoreResult


class BacktestEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.selection_date = datetime(2026, 1, 2)
        self.evaluation_date = self.selection_date + timedelta(days=20)

    def test_recreates_selections_with_returns(self) -> None:
        ranking = RankingResult([
            RankingItem(rank=1, analysis=self._analysis("000001", "Alpha")),
            RankingItem(rank=2, analysis=self._analysis("000002", "Beta")),
        ])

        selections = SelectionEngine().select(
            ranking,
            selected_date=self.selection_date,
            top_n=2,
        )
        result = BacktestEngine().run(
            selections=selections,
            evaluation_date=self.evaluation_date,
            holding_days=20,
            selection_prices={"000001": 100.0, "000002": 200.0},
            evaluation_prices={"000001": 110.0, "000002": 180.0},
        )

        self.assertEqual(result.total_count, 2)
        self.assertEqual(result.missing_price_count, 0)
        self.assertEqual(result.results[0].code, "000001")
        self.assertEqual(result.results[0].selection.selected_date, self.selection_date)
        self.assertAlmostEqual(result.results[0].return_rate, 0.10)
        self.assertAlmostEqual(result.results[1].return_rate, -0.10)

    def test_records_candidates_without_complete_price_data(self) -> None:
        ranking = RankingResult([
            RankingItem(rank=1, analysis=self._analysis("000001", "Alpha")),
            RankingItem(rank=2, analysis=self._analysis("000002", "Beta")),
        ])

        selections = SelectionEngine().select(ranking, self.selection_date)
        result = BacktestEngine().run(
            selections=selections,
            evaluation_date=self.evaluation_date,
            holding_days=20,
            selection_prices={"000001": 100.0},
            evaluation_prices={"000001": 110.0, "000002": 180.0},
        )

        self.assertEqual(result.total_count, 1)
        self.assertEqual(result.missing_price_codes, ["000002"])

    def test_calculates_net_and_excess_returns(self) -> None:
        ranking = RankingResult([
            RankingItem(rank=1, analysis=self._analysis("000001", "Alpha")),
        ])
        engine = BacktestEngine(
            transaction_cost_policy=TransactionCostPolicy(
                buy_fee_rate=0.001,
                sell_fee_rate=0.001,
                sell_tax_rate=0.002,
                entry_slippage_rate=0.001,
                exit_slippage_rate=0.001,
            )
        )

        result = engine.run(
            selections=SelectionEngine().select(ranking, self.selection_date),
            evaluation_date=self.evaluation_date,
            holding_days=20,
            selection_prices={"000001": 100.0},
            evaluation_prices={"000001": 110.0},
            benchmark_returns={"000001": 0.03},
        )

        item = result.results[0]
        expected_net = (110.0 * 0.996 - 100.0 * 1.002) / (100.0 * 1.002)
        self.assertAlmostEqual(item.return_rate, 0.10)
        self.assertAlmostEqual(item.net_return_rate, expected_net)
        self.assertAlmostEqual(item.benchmark_return_rate, 0.03)
        self.assertAlmostEqual(item.excess_return_rate, expected_net - 0.03)

    def test_rejects_invalid_selection_price(self) -> None:
        ranking = RankingResult([
            RankingItem(rank=1, analysis=self._analysis("000001", "Alpha")),
        ])

        with self.assertRaises(ValueError):
            BacktestEngine().run(
                selections=SelectionEngine().select(
                    ranking,
                    self.selection_date,
                ),
                evaluation_date=self.evaluation_date,
                holding_days=20,
                selection_prices={"000001": 0.0},
                evaluation_prices={"000001": 110.0},
            )

    @staticmethod
    def _analysis(code: str, name: str) -> AnalysisResult:
        return AnalysisResult(
            code=code,
            name=name,
            indicators=None,
            features=None,
            score=ScoreResult(),
        )


if __name__ == "__main__":
    unittest.main()

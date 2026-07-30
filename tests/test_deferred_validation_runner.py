from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from analysis.analysis_result import AnalysisResult
from backtest.engine.backtest_engine import BacktestEngine
from backtest.model.selection import Selection
from decision.decision_result import DecisionResult
from decision.decision_type import DecisionType
from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.enums import MarketType
from domain.stock import Stock
from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from prediction.prediction_grade import PredictionGrade
from prediction.prediction_result import PredictionResult
from report.report_generator import ReportGenerator
from repository.selection_repository import SelectionRepository
from repository.candle_repository import CandleRepository
from repository.validation_repository import ValidationRepository
from runner.deferred_validation_runner import DeferredValidationRunner
from scoring.score_result import ScoreResult
from validation.validator import Validator


class DeferredValidationRunnerTest(unittest.TestCase):
    def test_validates_a_saved_selection_with_later_market_prices(self) -> None:
        selected_at = datetime(2026, 1, 2)
        evaluation_date = selected_at + timedelta(days=20)
        with TemporaryDirectory() as directory:
            repository = SelectionRepository(Path(directory))
            selection = self._selection(selected_at)
            repository.save([selection])
            candle_repository = CandleRepository(Path(directory) / "market")
            validation_repository = ValidationRepository(Path(directory) / "validations")
            candle_repository.save(CandleSeries(
                Stock("000001", "Alpha", MarketType.KOSPI),
                [Candle(selected_at, 100.0, 100.0, 100.0, 100.0, 1_000)],
            ))
            runner = DeferredValidationRunner(
                selection_repository=repository,
                market_provider=_Provider(selected_at, evaluation_date),
                backtest_engine=BacktestEngine(),
                validator=Validator(),
                report_generator=ReportGenerator(),
                candle_repository=candle_repository,
                validation_repository=validation_repository,
                benchmark_provider=_BenchmarkProvider(),
            )

            result = runner.run(selected_at, evaluation_date, holding_days=20)
            records = validation_repository.load_all()

        self.assertEqual(result.backtest.total_count, 1)
        self.assertAlmostEqual(result.backtest.results[0].return_rate, 0.10)
        self.assertEqual(result.validation.success_count, 1)
        self.assertIn("PRICE_ABOVE_MA20", result.report_markdown)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].result.success_count, 1)
        self.assertAlmostEqual(result.validation.average_benchmark_return, 0.02)
        self.assertAlmostEqual(result.validation.average_excess_return, 0.08)
        self.assertAlmostEqual(records[0].result.average_benchmark_return, 0.02)
        self.assertAlmostEqual(records[0].result.average_excess_return, 0.08)

    def test_requires_a_saved_snapshot_before_validation(self) -> None:
        selected_at = datetime(2026, 1, 2)
        evaluation_date = selected_at + timedelta(days=20)
        with TemporaryDirectory() as directory:
            runner = DeferredValidationRunner(
                selection_repository=SelectionRepository(Path(directory)),
                market_provider=_Provider(selected_at, evaluation_date),
                backtest_engine=BacktestEngine(),
                validator=Validator(),
                report_generator=ReportGenerator(),
            )

            with self.assertRaisesRegex(FileNotFoundError, "no selection snapshot"):
                runner.run(selected_at, evaluation_date, holding_days=20)

    def test_rejects_invalid_validation_dates_and_holding_period(self) -> None:
        selected_at = datetime(2026, 1, 2)
        runner = DeferredValidationRunner(
            selection_repository=SelectionRepository(),
            market_provider=None,
            backtest_engine=BacktestEngine(),
            validator=Validator(),
            report_generator=ReportGenerator(),
        )

        with self.assertRaisesRegex(ValueError, "holding_days"):
            runner.run(selected_at, selected_at + timedelta(days=20), holding_days=0)
        with self.assertRaisesRegex(ValueError, "evaluation_date"):
            runner.run(selected_at, selected_at, holding_days=20)

    def test_validates_multiple_observed_trading_horizons(self) -> None:
        selected_at = datetime(2026, 1, 2)
        as_of = datetime(2026, 1, 12)
        with TemporaryDirectory() as directory:
            repository = SelectionRepository(Path(directory))
            repository.save([self._selection(selected_at)])
            validation_repository = ValidationRepository(
                Path(directory) / "validations"
            )
            runner = DeferredValidationRunner(
                selection_repository=repository,
                market_provider=_HorizonProvider(selected_at),
                backtest_engine=BacktestEngine(),
                validator=Validator(),
                report_generator=ReportGenerator(),
                validation_repository=validation_repository,
                benchmark_provider=_BenchmarkProvider(),
            )

            results = runner.run_horizons(
                selected_at,
                as_of,
                holding_days=[2, 5],
            )
            records = validation_repository.load_all()

        self.assertEqual(list(results), [2, 5])
        self.assertAlmostEqual(
            results[2].backtest.results[0].return_rate,
            (102.0 - 101.0) / 101.0,
        )
        self.assertAlmostEqual(
            results[5].backtest.results[0].return_rate,
            (105.0 - 101.0) / 101.0,
        )
        self.assertEqual([record.holding_days for record in records], [2, 5])

    @staticmethod
    def _selection(selected_at: datetime) -> Selection:
        features = FeatureSet()
        features.add(Feature.create_enabled(FeatureType.PRICE_ABOVE_MA20, 1.0, 1.0))
        grade = PredictionGrade.BUY
        analysis = AnalysisResult(
            code="000001",
            name="Alpha",
            indicators=None,
            features=features,
            score=ScoreResult(trend_score=15, context_score=6),
            prediction=PredictionResult(80, 0.8, grade, 0.1),
            decision=DecisionResult(DecisionType.BUY, grade, "test"),
            market=MarketType.KOSPI,
        )
        return Selection(analysis, selected_at, 1)


class _Provider:
    def __init__(self, selected_at: datetime, evaluation_date: datetime) -> None:
        self.selected_at = selected_at
        self.evaluation_date = evaluation_date

    def get_daily_price(self, stock: Stock) -> CandleSeries:
        return CandleSeries(stock, [
            Candle(
                self.selected_at + timedelta(days=1),
                100.0, 100.0, 100.0, 100.0, 1_000,
            ),
            Candle(self.evaluation_date, 110.0, 110.0, 110.0, 110.0, 1_000),
        ])


class _BenchmarkProvider:
    @staticmethod
    def get_returns(markets, start_date, end_date) -> dict[str, float]:
        return {market.value: 0.02 for market in markets}


class _HorizonProvider:
    def __init__(self, selected_at: datetime) -> None:
        self.selected_at = selected_at

    def get_daily_price(self, stock: Stock) -> CandleSeries:
        dates_and_prices = [
            (self.selected_at, 100.0),
            (datetime(2026, 1, 5), 101.0),
            (datetime(2026, 1, 6), 102.0),
            (datetime(2026, 1, 7), 103.0),
            (datetime(2026, 1, 8), 104.0),
            (datetime(2026, 1, 9), 105.0),
        ]
        return CandleSeries(stock, [
            Candle(date, price, price, price, price, 1_000)
            for date, price in dates_and_prices
        ])


if __name__ == "__main__":
    unittest.main()

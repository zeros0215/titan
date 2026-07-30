from datetime import datetime, timedelta
import unittest

from analysis.analysis_result import AnalysisResult
from backtest.engine.backtest_engine import BacktestEngine
from backtest.engine.selection_engine import SelectionEngine
from backtest.price_resolver import PriceResolution
from decision.decision_result import DecisionResult
from decision.decision_type import DecisionType
from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from prediction.prediction_grade import PredictionGrade
from prediction.prediction_result import PredictionResult
from ranking.ranking_engine import RankingEngine
from report.report_generator import ReportGenerator
from runner.titan_runner import TitanRunner
from scoring.score_result import ScoreResult
from validation.validator import Validator
from config.observation_policy import ObservationPolicy


class TitanRunnerTest(unittest.TestCase):
    def test_coordinates_the_complete_selection_workflow(self) -> None:
        analyses = [
            self._analysis("000001", "Alpha", 40, DecisionType.BUY),
            self._analysis("000002", "Beta", 20, DecisionType.WATCH),
        ]
        selection_repository = _SelectionRepository()
        runner = TitanRunner(
            stock_repository=_Repository(["stock-a", "stock-b"]),
            scanner=_Scanner(analyses),
            ranking_engine=RankingEngine(),
            selection_engine=SelectionEngine(),
            backtest_engine=BacktestEngine(),
            validator=Validator(),
            report_generator=ReportGenerator(),
            selection_repository=selection_repository,
            price_resolver=_PriceResolver(),
        )
        selected = datetime(2026, 1, 2)

        result = runner.run(
            selection_date=selected,
            evaluation_date=selected + timedelta(days=20),
            holding_days=20,
            top_n=2,
            success_return=0.05,
        )

        self.assertEqual(result.ranking.top.analysis.code, "000001")
        self.assertEqual(result.selections[0].code, "000001")
        self.assertEqual(selection_repository.saved[0].code, "000001")
        self.assertEqual(result.backtest.total_count, 2)
        self.assertEqual(result.validation.success_count, 1)
        self.assertIn("# TITAN Selection Validation Report", result.report_markdown)

    def test_keeps_observation_cohort_separate_from_selections(self) -> None:
        analyses = [
            self._analysis("000001", "Selected", 85, DecisionType.BUY),
            self._analysis("000002", "Observed", 75, DecisionType.WATCH),
            self._analysis("000003", "Ignored", 65, DecisionType.PASS),
        ]
        selection_repository = _SelectionRepository()
        observation_repository = _SelectionRepository()
        runner = TitanRunner(
            stock_repository=_Repository(["a", "b", "c"]),
            scanner=_Scanner(analyses),
            ranking_engine=RankingEngine(),
            selection_engine=SelectionEngine(),
            backtest_engine=BacktestEngine(),
            validator=Validator(),
            report_generator=ReportGenerator(),
            selection_repository=selection_repository,
            filter_engine=_ScoreFilter(),
            observation_repository=observation_repository,
            observation_policy=ObservationPolicy(),
        )

        result = runner.select(datetime(2026, 1, 2), top_n=5)

        self.assertEqual([item.code for item in result.selections], ["000001"])
        self.assertEqual([item.code for item in result.observations], ["000002"])
        self.assertEqual(selection_repository.saved[0].code, "000001")
        self.assertEqual(observation_repository.saved[0].code, "000002")

    def test_excludes_quality_quarantined_analysis_before_selection(self):
        analyses = [
            self._analysis("000001", "Blocked", 90, DecisionType.BUY),
            self._analysis("000002", "Allowed", 85, DecisionType.BUY),
        ]
        runner = TitanRunner(
            stock_repository=_Repository(["a", "b"]),
            scanner=_Scanner(analyses),
            ranking_engine=RankingEngine(),
            selection_engine=SelectionEngine(),
            backtest_engine=BacktestEngine(),
            validator=Validator(),
            report_generator=ReportGenerator(),
            quality_quarantine_policy=_Quarantine(),
        )

        result = runner.select(datetime(2026, 1, 2), top_n=5)

        self.assertEqual(["000002"], [item.code for item in result.selections])

    @staticmethod
    def _analysis(
        code: str,
        name: str,
        trend_score: int,
        decision_type: DecisionType,
    ) -> AnalysisResult:
        features = FeatureSet()
        features.add(Feature.create_enabled(FeatureType.PRICE_ABOVE_MA20, 1.0, 1.0))
        grade = PredictionGrade.BUY
        return AnalysisResult(
            code=code,
            name=name,
            indicators=None,
            features=features,
            score=ScoreResult(trend_score=trend_score),
            prediction=PredictionResult(80, 0.8, grade, 0.1),
            decision=DecisionResult(decision_type, grade, "test"),
        )


class _Repository:
    def __init__(self, stocks) -> None:
        self.stocks = stocks

    def get_all(self):
        return self.stocks


class _Scanner:
    def __init__(self, analyses) -> None:
        self.analyses = analyses

    def scan_with_market_data(self, stocks, as_of=None):
        from scanner.scan_result import ScanResult
        return ScanResult(self.analyses, {})


class _SelectionRepository:
    def __init__(self) -> None:
        self.saved = []

    def save(self, selections, selected_at=None) -> None:
        self.saved = selections


class _PriceResolver:
    def resolve(self, selections, series_by_code, evaluation_date):
        return PriceResolution(
            selection_prices={"000001": 100.0, "000002": 200.0},
            evaluation_prices={"000001": 110.0, "000002": 180.0},
        )


class _ScoreFilter:
    @staticmethod
    def filter(analyses):
        return [
            item
            for item in analyses
            if item.score.normalized_score >= 80
        ]


class _Quarantine:
    @staticmethod
    def filter(analyses, as_of):
        return [item for item in analyses if item.code != "000001"]


if __name__ == "__main__":
    unittest.main()

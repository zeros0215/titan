from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from analysis.analysis_result import AnalysisResult
from backtest.model.selection import Selection
from decision.decision_result import DecisionResult
from decision.decision_type import DecisionType
from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from prediction.prediction_grade import PredictionGrade
from prediction.prediction_result import PredictionResult
from repository.selection_repository import SelectionRepository
from repository.observation_repository import ObservationRepository
from scoring.score_result import ScoreResult
from market.context.market_context import MarketContext
from market.context.market_trend import MarketTrend


class SelectionRepositoryTest(unittest.TestCase):
    def test_saves_and_loads_selection_reasoning(self) -> None:
        selected_at = datetime(2026, 7, 27, 9, 0, 0)
        with TemporaryDirectory() as directory:
            repository = SelectionRepository(Path(directory))
            path = repository.save([self._selection(selected_at)])
            snapshots = repository.load(selected_at)
            metadata = repository.load_metadata(selected_at)

        self.assertIsNotNone(path)
        self.assertEqual(path.name, "20260727T090000.json")
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].code, "000001")
        self.assertEqual(snapshots[0].context_score, 6)
        self.assertEqual(snapshots[0].enabled_features, ["PRICE_ABOVE_MA20"])
        self.assertEqual(snapshots[0].prediction_grade, "BUY")
        self.assertEqual(snapshots[0].decision, "BUY")
        self.assertEqual(snapshots[0].market_context["kospi_trend"], "BULL")
        self.assertEqual(snapshots[0].market_context["market_strength"], 0.75)
        self.assertEqual(metadata["version"], 2)
        self.assertEqual(metadata["data_as_of"], selected_at.isoformat())
        self.assertEqual(metadata["strategy_version"], "1.0.0")
        self.assertIn(metadata["price_adjustment"], {"ADJUSTED", "SYNTHETIC"})
        self.assertTrue(metadata["execution_id"].startswith("20260727T090000_"))

    def test_execution_id_is_stable_for_the_same_selection(self) -> None:
        selected_at = datetime(2026, 7, 27, 9, 0, 0)
        with TemporaryDirectory() as directory:
            repository = SelectionRepository(Path(directory))
            repository.save([self._selection(selected_at)])
            first = repository.load_metadata(selected_at)["execution_id"]
            repository.save([self._selection(selected_at)])
            second = repository.load_metadata(selected_at)["execution_id"]

        self.assertEqual(first, second)

    def test_observation_repository_marks_shadow_cohort(self) -> None:
        selected_at = datetime(2026, 7, 27, 9, 0, 0)
        with TemporaryDirectory() as directory:
            repository = ObservationRepository(Path(directory))
            repository.save([self._selection(selected_at)])
            metadata = repository.load_metadata(selected_at)

        self.assertEqual(metadata["cohort_type"], "OBSERVATION")

    def test_saves_an_empty_snapshot_for_a_completed_selection_run(self) -> None:
        selected_at = datetime(2026, 7, 28, 9, 0, 0)
        with TemporaryDirectory() as directory:
            repository = SelectionRepository(Path(directory))
            path = repository.save([], selected_at=selected_at)

            self.assertTrue(repository.exists(selected_at))
            self.assertEqual(repository.load(selected_at), [])

        self.assertEqual(path.name, "20260728T090000.json")

    @staticmethod
    def _selection(selected_at: datetime) -> Selection:
        features = FeatureSet()
        features.add(Feature.create_enabled(
            FeatureType.PRICE_ABOVE_MA20,
            1.0,
            10.0,
            "above MA20",
        ))
        grade = PredictionGrade.BUY
        analysis = AnalysisResult(
            code="000001",
            name="Alpha",
            indicators=None,
            features=features,
            score=ScoreResult(trend_score=15, context_score=6),
            prediction=PredictionResult(80, 0.8, grade, 0.1),
            decision=DecisionResult(DecisionType.BUY, grade, "test"),
            positive_factors=["above MA20"],
            context=MarketContext(
                kospi_trend=MarketTrend.BULL,
                kosdaq_trend=MarketTrend.SIDEWAYS,
                market_strength=0.75,
                sector_strength=0.5,
                theme_strength=0.5,
                foreign_flow=0.0,
                institution_flow=0.0,
                score=8,
            ),
        )
        return Selection(analysis, selected_at, 1)


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from research.next_day_prediction import (
    FEATURE_COUNT,
    _summarize_holding_samples,
    extract_features,
    score_features,
)


class NextDayPredictionTest(unittest.TestCase):
    def setUp(self):
        start = datetime(2025, 1, 1)
        self.candles = []
        for index in range(70):
            close = 100 + index
            self.candles.append(SimpleNamespace(
                date=start + timedelta(days=index), open=close - 1,
                high=close + 2, low=close - 2, close=close,
                volume=1000 + index * 10,
            ))

    def test_extracts_exactly_fifteen_prior_close_features(self):
        features = extract_features(self.candles, 60)
        self.assertEqual(FEATURE_COUNT, len(features))
        self.assertGreater(features["return_5d"], 0)
        self.assertGreater(features["ma5_over_ma20"], 0)

    def test_score_is_bounded_percentage(self):
        score = score_features(extract_features(self.candles, 60))
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_requires_history_before_feature_date(self):
        with self.assertRaises(ValueError):
            extract_features(self.candles, 59)

    def test_holding_comparison_keeps_rejected_slots_as_cash(self):
        samples = {
            (days, cap): []
            for days in (1, 2, 3, 5)
            for cap in (None, 0.00, 0.02, 0.03, 0.05)
        }
        samples[(2, 0.02)] = [
            {"year": 2025, "return": 0.02, "accepted": 2},
            {"year": 2026, "return": -0.01, "accepted": 1},
        ]
        row = next(
            item for item in _summarize_holding_samples(samples, 5)
            if item["holding_days"] == 2 and item["gap_cap"] == 0.02
        )
        self.assertEqual(row["train_2025"]["slot_fill_rate"], 0.4)
        self.assertEqual(row["validation_2026"]["slot_fill_rate"], 0.2)
        self.assertAlmostEqual(row["all"]["average_cohort_net_return"], 0.005)


if __name__ == "__main__":
    unittest.main()

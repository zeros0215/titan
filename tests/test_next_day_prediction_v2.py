import unittest

from research.next_day_prediction_v2 import (
    GROUP_WEIGHTS,
    _market_filter_summary,
    grouped_scores,
    percentile_ranks,
)


class NextDayPredictionV2Test(unittest.TestCase):
    def test_percentile_ranks_average_ties(self):
        ranks = percentile_ranks({"a": 1.0, "b": 2.0, "c": 2.0, "d": 4.0})
        self.assertEqual(ranks["a"], 0.0)
        self.assertEqual(ranks["d"], 1.0)
        self.assertAlmostEqual(ranks["b"], 0.5)
        self.assertEqual(ranks["b"], ranks["c"])

    def test_group_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(GROUP_WEIGHTS.values()), 1.0)

    def test_grouped_score_penalizes_upper_wick_and_overheat(self):
        common = {
            "return_5d": .03, "relative_return_20d": .03, "ma5_over_ma20": .02,
            "ma20_over_ma60": .02, "distance_high_20d": -.01,
            "directional_volume": .02, "trading_value_log": 24,
            "close_location": .9, "breakout_hold": .01, "atr_20d": .04,
        }
        rows = [
            {"code": "safe", "features": {**common, "upper_wick": .05, "consecutive_up": 1, "return_1d": .01}},
            {"code": "hot", "features": {**common, "upper_wick": .8, "consecutive_up": 5, "return_1d": .15}},
        ]
        grouped_scores(rows)
        self.assertGreater(rows[0]["score"], rows[1]["score"])

    def test_market_filter_keeps_down_regime_as_cash(self):
        rows = [
            {"regime": "상승", "average_3d_net_return": .02},
            {"regime": "하락", "average_3d_net_return": -.04},
        ]
        result = _market_filter_summary(2026, rows)
        self.assertAlmostEqual(result["baseline_average_3d_net_return"], -.01)
        self.assertAlmostEqual(result["filtered_average_3d_net_return"], .01)
        self.assertFalse(result["adopted"])


if __name__ == "__main__":
    unittest.main()

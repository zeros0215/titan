import unittest

from analysis.industry_relative_strength import (
    IndustryRsObservation,
    _horizon_summary,
    _percentile_scores,
)


class IndustryRelativeStrengthTest(unittest.TestCase):
    def test_percentile_scores_cover_zero_to_one_hundred(self) -> None:
        self.assertEqual(
            [0.0, 50.0, 100.0],
            _percentile_scores([-0.1, 0.0, 0.2]),
        )

    def test_horizon_summary_reports_top_bottom_spread(self) -> None:
        observations = [
            self._observation(0, -0.02),
            self._observation(20, -0.01),
            self._observation(40, 0.00),
            self._observation(60, 0.01),
            self._observation(80, 0.02),
            self._observation(100, 0.03),
        ]
        result = _horizon_summary(observations, 20)
        self.assertAlmostEqual(0.04, result["top_bottom_spread"])
        self.assertTrue(result["monotonic"])

    @staticmethod
    def _observation(score, forward):
        return IndustryRsObservation(
            signal_date="2023-01-02",
            group="은행",
            code=str(score),
            name="테스트",
            rs_score=score,
            industry_rank=1,
            industry_size=3,
            relative_strength=0.1,
            industry_momentum=0.05,
            stock_momentum=0.15,
            forward_5d=forward,
            forward_20d=forward,
            forward_60d=forward,
        )


if __name__ == "__main__":
    unittest.main()

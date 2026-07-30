import unittest

from validation.score_band_validation import (
    ScoreBandValidation,
    assess_score_monotonicity,
    score_band_for,
)


class ScoreBandValidationTest(unittest.TestCase):
    def test_maps_boundary_scores(self) -> None:
        self.assertEqual(score_band_for(59).label, "0-59")
        self.assertEqual(score_band_for(60).label, "60-69")
        self.assertEqual(score_band_for(89).label, "80-89")
        self.assertEqual(score_band_for(100).label, "90-100")

    def test_assesses_only_bands_with_enough_samples(self) -> None:
        low = ScoreBandValidation(70, 79, 30, 15, 0.01, 0.01)
        high = ScoreBandValidation(80, 89, 30, 21, 0.03, 0.03)
        small = ScoreBandValidation(90, 100, 5, 1, -0.01, -0.01)

        self.assertEqual(
            assess_score_monotonicity([low, high, small]),
            "MONOTONIC",
        )
        self.assertEqual(
            assess_score_monotonicity([low]),
            "INSUFFICIENT_DATA",
        )


if __name__ == "__main__":
    unittest.main()

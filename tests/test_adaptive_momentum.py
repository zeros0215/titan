import unittest

from research.adaptive_momentum import inverse_volatility_weights


class AdaptiveMomentumTest(unittest.TestCase):
    def test_inverse_volatility_weights_sum_to_one(self) -> None:
        weights = inverse_volatility_weights([
            {"code": "A", "volatility": 0.1},
            {"code": "B", "volatility": 0.2},
        ])
        self.assertAlmostEqual(1.0, sum(weights.values()))
        self.assertAlmostEqual(2 / 3, weights["A"])

    def test_ignores_zero_volatility(self) -> None:
        self.assertEqual({}, inverse_volatility_weights([{"code": "A", "volatility": 0}]))

import unittest

from research.dual_market_momentum import choose_market


class DualMarketMomentumTest(unittest.TestCase):
    def test_chooses_stronger_positive_market(self):
        self.assertEqual(
            "KOSDAQ", choose_market({"KOSPI": .05, "KOSDAQ": .08})
        )

    def test_chooses_cash_when_both_markets_are_non_positive(self):
        self.assertEqual(
            "CASH", choose_market({"KOSPI": -.01, "KOSDAQ": 0.0})
        )


if __name__ == "__main__":
    unittest.main()

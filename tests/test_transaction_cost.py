import unittest

from backtest.transaction_cost import TransactionCostPolicy


class TransactionCostPolicyTest(unittest.TestCase):
    def test_zero_cost_matches_gross_return(self) -> None:
        self.assertAlmostEqual(
            TransactionCostPolicy().net_return(100.0, 110.0),
            0.10,
        )

    def test_rejects_invalid_rates(self) -> None:
        with self.assertRaisesRegex(ValueError, "sell_tax_rate"):
            TransactionCostPolicy(sell_tax_rate=-0.001)


if __name__ == "__main__":
    unittest.main()

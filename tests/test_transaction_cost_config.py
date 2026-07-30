import os
import unittest
from unittest.mock import patch

from config.transaction_costs import transaction_cost_policy_from_env


class TransactionCostConfigTest(unittest.TestCase):
    def test_uses_conservative_non_zero_v1_defaults(self) -> None:
        names = [
            "TITAN_BUY_FEE_RATE",
            "TITAN_SELL_FEE_RATE",
            "TITAN_SELL_TAX_RATE",
            "TITAN_ENTRY_SLIPPAGE_RATE",
            "TITAN_EXIT_SLIPPAGE_RATE",
        ]
        with patch.dict(os.environ, {}, clear=False):
            for name in names:
                os.environ.pop(name, None)
            policy = transaction_cost_policy_from_env()

        self.assertAlmostEqual(
            0.0038,
            policy.buy_fee_rate
            + policy.sell_fee_rate
            + policy.sell_tax_rate
            + policy.entry_slippage_rate
            + policy.exit_slippage_rate,
        )

    def test_loads_decimal_rates_from_environment(self) -> None:
        with patch.dict(os.environ, {
            "TITAN_BUY_FEE_RATE": "0.001",
            "TITAN_SELL_TAX_RATE": "0.002",
        }, clear=False):
            policy = transaction_cost_policy_from_env()

        self.assertEqual(policy.buy_fee_rate, 0.001)
        self.assertEqual(policy.sell_tax_rate, 0.002)

    def test_rejects_non_numeric_rate(self) -> None:
        with patch.dict(
            os.environ,
            {"TITAN_BUY_FEE_RATE": "not-a-number"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "TITAN_BUY_FEE_RATE"):
                transaction_cost_policy_from_env()


if __name__ == "__main__":
    unittest.main()

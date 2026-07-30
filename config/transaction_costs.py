"""Configurable trading-cost assumptions for validation runs."""

import os

from backtest.transaction_cost import TransactionCostPolicy


# Conservative V1 backtest assumptions, not a claim about a specific broker's
# live tariff. Environment variables can override each component explicitly.
V1_BACKTEST_COST_DEFAULTS = {
    "TITAN_BUY_FEE_RATE": 0.00015,
    "TITAN_SELL_FEE_RATE": 0.00015,
    "TITAN_SELL_TAX_RATE": 0.0015,
    "TITAN_ENTRY_SLIPPAGE_RATE": 0.001,
    "TITAN_EXIT_SLIPPAGE_RATE": 0.001,
}


def transaction_cost_policy_from_env() -> TransactionCostPolicy:
    """Build a policy without hard-coding changeable brokerage or tax rates."""
    return TransactionCostPolicy(
        buy_fee_rate=_rate("TITAN_BUY_FEE_RATE"),
        sell_fee_rate=_rate("TITAN_SELL_FEE_RATE"),
        sell_tax_rate=_rate("TITAN_SELL_TAX_RATE"),
        entry_slippage_rate=_rate("TITAN_ENTRY_SLIPPAGE_RATE"),
        exit_slippage_rate=_rate("TITAN_EXIT_SLIPPAGE_RATE"),
    )


def _rate(name: str) -> float:
    raw = os.getenv(name, str(V1_BACKTEST_COST_DEFAULTS[name])).strip()
    try:
        return float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a decimal rate") from error

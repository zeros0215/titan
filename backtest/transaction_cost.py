from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class TransactionCostPolicy:
    """Round-trip trading-cost assumptions expressed as decimal rates."""

    buy_fee_rate: float = 0.0
    sell_fee_rate: float = 0.0
    sell_tax_rate: float = 0.0
    entry_slippage_rate: float = 0.0
    exit_slippage_rate: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("buy_fee_rate", self.buy_fee_rate),
            ("sell_fee_rate", self.sell_fee_rate),
            ("sell_tax_rate", self.sell_tax_rate),
            ("entry_slippage_rate", self.entry_slippage_rate),
            ("exit_slippage_rate", self.exit_slippage_rate),
        ):
            if value < 0 or value >= 1:
                raise ValueError(f"{name} must be between 0 and 1")

    def net_return(self, entry_price: float, exit_price: float) -> float:
        if entry_price <= 0:
            raise ValueError("entry_price must be greater than zero")
        if exit_price < 0:
            raise ValueError("exit_price must not be negative")
        entry_cost = entry_price * (
            1 + self.buy_fee_rate + self.entry_slippage_rate
        )
        exit_proceeds = exit_price * (
            1
            - self.sell_fee_rate
            - self.sell_tax_rate
            - self.exit_slippage_rate
        )
        return (exit_proceeds - entry_cost) / entry_cost

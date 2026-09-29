"""Fail-closed comparison between local state and a broker account snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from trading.model import AccountSnapshot, Position


class DifferenceType(str, Enum):
    CASH = "CASH"
    MISSING_AT_BROKER = "MISSING_AT_BROKER"
    MISSING_LOCALLY = "MISSING_LOCALLY"
    POSITION_QUANTITY = "POSITION_QUANTITY"
    POSITION_AVERAGE_PRICE = "POSITION_AVERAGE_PRICE"
    UNKNOWN_OPEN_ORDER = "UNKNOWN_OPEN_ORDER"


@dataclass(frozen=True, slots=True)
class ReconciliationDifference:
    kind: DifferenceType
    symbol: str | None
    local_value: str
    broker_value: str


@dataclass(frozen=True, slots=True)
class InternalPortfolioSnapshot:
    cash: Decimal
    positions: tuple[Position, ...] = field(default_factory=tuple)
    known_open_order_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    ready: bool
    differences: tuple[ReconciliationDifference, ...]


def reconcile_account(
    local: InternalPortfolioSnapshot,
    broker: AccountSnapshot,
    broker_open_order_ids: frozenset[str] = frozenset(),
    *,
    cash_tolerance: Decimal = Decimal("1"),
    average_price_tolerance: Decimal = Decimal("0.01"),
) -> ReconciliationResult:
    differences: list[ReconciliationDifference] = []
    if abs(local.cash - broker.cash) > cash_tolerance:
        differences.append(ReconciliationDifference(
            DifferenceType.CASH, None, str(local.cash), str(broker.cash)
        ))

    local_positions = {item.symbol: item for item in local.positions if item.quantity}
    broker_positions = {
        item.symbol: item for item in broker.positions if item.quantity
    }
    for symbol in sorted(local_positions.keys() | broker_positions.keys()):
        local_position = local_positions.get(symbol)
        broker_position = broker_positions.get(symbol)
        if broker_position is None:
            differences.append(ReconciliationDifference(
                DifferenceType.MISSING_AT_BROKER,
                symbol,
                str(local_position.quantity),
                "0",
            ))
            continue
        if local_position is None:
            differences.append(ReconciliationDifference(
                DifferenceType.MISSING_LOCALLY,
                symbol,
                "0",
                str(broker_position.quantity),
            ))
            continue
        if local_position.quantity != broker_position.quantity:
            differences.append(ReconciliationDifference(
                DifferenceType.POSITION_QUANTITY,
                symbol,
                str(local_position.quantity),
                str(broker_position.quantity),
            ))
        if (
            abs(local_position.average_price - broker_position.average_price)
            > average_price_tolerance
        ):
            differences.append(ReconciliationDifference(
                DifferenceType.POSITION_AVERAGE_PRICE,
                symbol,
                str(local_position.average_price),
                str(broker_position.average_price),
            ))

    for order_id in sorted(
        broker_open_order_ids - local.known_open_order_ids
    ):
        differences.append(ReconciliationDifference(
            DifferenceType.UNKNOWN_OPEN_ORDER, None, "", order_id
        ))
    return ReconciliationResult(not differences, tuple(differences))

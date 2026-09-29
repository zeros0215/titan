"""Conservative matching of an uncertain submission to broker order history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from broker.kiwoom.paper import KiwoomPaperOrderObservation
from trading.model import BrokerOrderRequest


class OrderLookupStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class OrderLookupResult:
    status: OrderLookupStatus
    order: KiwoomPaperOrderObservation | None
    matching_order_ids: tuple[str, ...]


def resolve_uncertain_submission(
    request: BrokerOrderRequest,
    *,
    submission_started_at: datetime,
    known_order_ids_before_submit: frozenset[str],
    observations: tuple[KiwoomPaperOrderObservation, ...],
    clock_skew: timedelta = timedelta(seconds=5),
    lookup_window: timedelta = timedelta(minutes=2),
) -> OrderLookupResult:
    """Resolve only a unique new broker order; never guess among candidates."""
    if submission_started_at.tzinfo is None:
        raise ValueError("submission_started_at must be timezone-aware")
    earliest = submission_started_at - clock_skew
    latest = submission_started_at + lookup_window
    matches = tuple(
        item for item in observations
        if (
            item.broker_order_id not in known_order_ids_before_submit
            and item.symbol == request.symbol
            and item.side is request.side
            and item.requested_quantity == request.quantity
            and earliest <= item.ordered_at.astimezone(
                submission_started_at.tzinfo
            ) <= latest
        )
    )
    ids = tuple(sorted(item.broker_order_id for item in matches))
    if not matches:
        return OrderLookupResult(OrderLookupStatus.NOT_FOUND, None, ())
    if len(matches) != 1:
        return OrderLookupResult(OrderLookupStatus.AMBIGUOUS, None, ids)
    return OrderLookupResult(OrderLookupStatus.FOUND, matches[0], ids)

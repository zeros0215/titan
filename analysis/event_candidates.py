"""Intraday event-candidate filtering for manual shadow operation."""

from __future__ import annotations

from datetime import datetime, time


def snapshot_phase(now: datetime) -> str:
    """Classify a scan so only a genuine 10:00 snapshot becomes an entry."""
    current = now.timetz().replace(tzinfo=None)
    if current < time(9, 30):
        return "EARLY"
    if current < time(9, 50):
        return "PREVIEW"
    if current <= time(10, 10):
        return "ENTRY"
    return "LATE"


def session_progress(now: datetime) -> float:
    """Return elapsed regular-session fraction, bounded for stable estimates."""
    opened = datetime.combine(now.date(), time(9, 0), tzinfo=now.tzinfo)
    closed = datetime.combine(now.date(), time(15, 30), tzinfo=now.tzinfo)
    if now <= opened:
        return 1 / 390
    if now >= closed:
        return 1.0
    return max(1 / 390, (now - opened).total_seconds() / 23400)


def evaluate_event_quote(
    quote: dict,
    previous_volume: float,
    progress: float,
) -> dict[str, float | bool | str | None]:
    price = _float(quote.get("close"))
    opening = _float(quote.get("open"))
    volume = _float(quote.get("volume"))
    vwap = _float(quote.get("vwap"))
    change_rate = _float(quote.get("change_rate"))
    expected_volume = max(previous_volume * progress, 1.0)
    volume_speed = volume / expected_volume if volume is not None else None
    price_in_range = (
        change_rate is not None and -0.01 <= change_rate <= 0.03
    )
    above_open = (
        price is not None and opening not in (None, 0) and price >= opening
    )
    above_vwap = (
        price is not None and vwap not in (None, 0) and price >= vwap
    )
    volume_accelerating = volume_speed is not None and volume_speed >= 2.0
    qualified = (
        price_in_range
        and above_open
        and above_vwap
        and volume_accelerating
    )
    reason = (
        "EVENT_REVIEW"
        if qualified
        else "PRICE_OUT_OF_RANGE"
        if not price_in_range
        else "BELOW_OPEN"
        if not above_open
        else "BELOW_VWAP"
        if not above_vwap
        else "VOLUME_NOT_ACCELERATING"
    )
    return {
        "qualified": qualified,
        "reason": reason,
        "volume_speed": volume_speed,
        "above_open": above_open,
        "above_vwap": above_vwap,
        "price_in_range": price_in_range,
        "reason_detail": (
            "매수 검토"
            if qualified
            else "등락률 -1~+3% 범위 밖"
            if not price_in_range
            else "현재가가 시가 아래"
            if not above_open
            else "현재가가 VWAP 아래"
            if not above_vwap
            else "거래량 속도 2배 미만"
        ),
    }


def _float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)

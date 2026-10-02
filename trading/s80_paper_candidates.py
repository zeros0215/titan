"""Build fail-closed paper-entry candidates from completed S80 selections."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from broker.kiwoom import KiwoomPaperStockInfo
from trading.paper_dashboard import STRATEGY_VERSION


OBSERVATION_STRATEGY_VERSION = "V1.3-S80-OBSERVATION-PAPER"
MAXIMUM_ENTRY_RISE = Decimal("0.03")


def exceeds_entry_rise_limit(
    reference_price: Decimal,
    opening_price: Decimal,
    current_price: Decimal,
) -> bool:
    """Block chasing a price over 3% above either prior close or open."""
    if min(reference_price, opening_price, current_price) <= 0:
        return True
    ceiling = Decimal("1") + MAXIMUM_ENTRY_RISE
    return (
        current_price > reference_price * ceiling
        or current_price > opening_price * ceiling
    )


def load_latest_s80_selection(
    runs_dir: Path,
    entry_date: date,
    *,
    expected_selection_date: date | None = None,
) -> dict | None:
    """Return the newest successful S80 run strictly before the entry date."""
    matches: list[tuple[date, dict]] = []
    for path in runs_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            selection_date = datetime.fromisoformat(str(payload["as_of"])).date()
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            selection_date < entry_date
            and (
                _weekday_distance(selection_date, entry_date) == 1
                or (
                    expected_selection_date is not None
                    and selection_date == expected_selection_date
                )
            )
            and payload.get("status") == "PASS"
            and payload.get("strategy_version") == STRATEGY_VERSION
            and isinstance(payload.get("selected_candidates"), list)
        ):
            matches.append((selection_date, payload))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def _weekday_distance(start: date, end: date) -> int:
    cursor = start
    sessions = 0
    while cursor < end:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if cursor.weekday() < 5:
            sessions += 1
    return sessions


def build_s80_paper_candidates(
    selection: dict | None,
    quotes: dict[str, KiwoomPaperStockInfo],
    *,
    held_symbols: set[str],
    ordered_symbols: set[str],
    maximum_positions: int = 7,
) -> list[dict]:
    if selection is None:
        return []
    selection_date = datetime.fromisoformat(str(selection["as_of"])).date()
    remaining_slots = max(0, maximum_positions - len(held_symbols))
    candidates = []
    ranked = [
        ("SELECTED", STRATEGY_VERSION, item)
        for item in selection["selected_candidates"]
    ] + [
        ("OBSERVATION", OBSERVATION_STRATEGY_VERSION, item)
        for item in selection.get("observation_candidates", [])
    ]
    for cohort, strategy_version, item in ranked:
        symbol = str(item.get("code") or "").zfill(6)
        quote = quotes.get(symbol)
        if quote is None:
            continue
        gap = quote.open_price / quote.reference_price - Decimal("1")
        eligible, reason = True, "모의투자 진입 조건 충족"
        if symbol in held_symbols:
            eligible, reason = False, "이미 보유 중"
        elif symbol in ordered_symbols:
            eligible, reason = False, "오늘 주문 존재"
        elif abs(gap) > Decimal("0.03"):
            eligible, reason = False, "시가 갭 ±3% 초과"
        elif exceeds_entry_rise_limit(
            quote.reference_price, quote.open_price, quote.current_price
        ):
            eligible, reason = False, "현재가 +3% 추격매수 제한"
        elif remaining_slots <= 0:
            eligible, reason = False, f"최대 {maximum_positions}종목 보유 한도"
        if eligible:
            remaining_slots -= 1
        candidates.append({
            "intent_id": (
                f"s80-{selection_date.isoformat()}-{symbol}"
                if cohort == "SELECTED"
                else f"s80-observation-{selection_date.isoformat()}-{symbol}"
            ),
            "cohort": cohort,
            "strategy_version": strategy_version,
            "selection_date": selection_date.isoformat(),
            "code": symbol,
            "name": quote.name,
            "score": item.get("total_score"),
            "previous_close": str(quote.reference_price),
            "opening_price": str(quote.open_price),
            "entry_price": str(quote.current_price),
            "gap_rate": float(gap),
            "quantity": 1,
            "eligible": eligible,
            "approval_enabled": True,
            "reason": (
                reason if cohort == "SELECTED" or not eligible
                else "관찰 후보 · 모의투자 조건 충족"
            ),
        })
    return candidates

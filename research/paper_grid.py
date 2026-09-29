"""Persistent paper-only grid for KODEX KOSDAQ150 Leverage (233740)."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

CODE = "233740"
NAME = "KODEX 코스닥150레버리지"
TICK_SIZE = 5
QUANTITY_PER_LEVEL = 100
MAX_LEVELS = 5
MAX_HOLDING = 500
DEFAULT_FEE_RATE = 0.00015
DEFAULT_SPACING = 100
SELL_REENTRY_DISCOUNT = 10
REFERENCE_PRICE = 5_000
RECALCULATE_BAND = 0.20
ADAPTIVE_SPACING_RATE = 0.02
GAP_HALT_RATE = -0.03
INTRADAY_HALT_RATE = -0.05
LOSS_REVIEW_RATE = -0.07
FIFTH_LEVEL_EXTRA_HALT_RATE = -0.03


def empty_state() -> dict:
    return {
        "schema_version": 3, "paper_only": True, "real_order_requests": 0,
        "code": CODE, "name": NAME, "tick_size": TICK_SIZE,
        "quantity": QUANTITY_PER_LEVEL, "max_levels": MAX_LEVELS,
        "max_holding": MAX_HOLDING, "fee_rate": DEFAULT_FEE_RATE,
        "spacing": DEFAULT_SPACING, "spacing_mode": "FIXED_100",
        "anchor_price": None, "next_buy_price": None, "lots": [],
        "cycle_buys": 0, "status": "STOPPED", "current_price": None,
        "order_side": None, "order_price": None, "halt_reason": None,
        "buy_halted_date": None,
        "risk_review_required": False, "overnight_holding": False,
        "last_quote_date": None, "previous_observed_price": None,
        "cycles": 0, "gross_profit": 0.0, "fees": 0.0,
        "net_profit_before_tax": 0.0, "started_at": None,
        "updated_at": None, "events": [],
        "quote_warning": None, "raw_quote": None, "quote_checked_at": None,
    }


def start(state: dict, quote_or_price, now: str | None = None, **_ignored) -> dict:
    """Start/restart while preserving every open 100-share lot."""
    state = _upgrade(state)
    if state["status"] != "STOPPED":
        return state
    state, quote = _checked_quote(state, quote_or_price, now)
    if quote is None:
        return state
    value = quote["close"]
    timestamp = now or quote.get("time") or _now()
    state = _upgrade(state)
    state.update({"current_price": value, "started_at": timestamp,
                  "updated_at": timestamp, "status": "RUNNING"})
    initial_buy = not state["lots"]
    if initial_buy:
        spacing, mode = _grid_spacing(value)
        state.update({"spacing": spacing, "spacing_mode": mode,
                      "anchor_price": value,
                      "next_buy_price": value,
                      "cycle_buys": 0, "halt_reason": None,
                      "buy_halted_date": None,
                      "previous_observed_price": value,
                      "risk_review_required": False})
    _update_order(state)
    _record_quote_date(state, quote)
    _event(state, timestamp, "START", value, state["order_price"],
           spacing=state["spacing"])
    if initial_buy:
        _buy_lot(state, timestamp)
        _update_order(state)
    return state


def observe(state: dict, quote_or_price, now: str | None = None) -> dict:
    """Apply at most one hypothetical fill from a current-price snapshot."""
    state, quote = _checked_quote(state, quote_or_price, now)
    if quote is None:
        return state
    value = quote["close"]
    timestamp = now or quote.get("time") or _now()
    state = _upgrade(state)
    previous_date = state.get("last_quote_date")
    state.update({"current_price": value, "updated_at": timestamp})
    quote_date = quote.get("date")
    state["overnight_holding"] = bool(
        state["lots"] and previous_date and quote_date and quote_date != previous_date
    )
    _record_quote_date(state, quote)
    if state["status"] == "STOPPED":
        return state

    if (state["status"] == "BUY_HALTED" and quote_date
            and state.get("buy_halted_date")
            and str(quote_date) != str(state["buy_halted_date"])
            and not state["risk_review_required"]):
        state.update({"status": "RUNNING", "halt_reason": None,
                      "buy_halted_date": None})
        _event(state, timestamp, "BUY_RESUMED", value, state.get("next_buy_price"))

    reason = _market_halt_reason(state, quote)
    if reason and state.get("halt_reason") != reason:
        state.update({"halt_reason": reason, "status": "BUY_HALTED",
                      "buy_halted_date": quote_date})
        _event(state, timestamp, "BUY_HALTED", value, None, reason=reason)
    _update_risk_review(state, value, timestamp)

    eligible = sorted(
        (lot for lot in state["lots"] if value >= lot["target_price"]),
        key=lambda lot: lot["target_price"],
    )
    if eligible:
        _sell_lot(state, eligible[0], timestamp)
    elif (
        state["status"] == "RUNNING" and not state.get("halt_reason")
        and not state["risk_review_required"]
        and state["cycle_buys"] < MAX_LEVELS
        and _holding_quantity(state) < MAX_HOLDING
        and state["next_buy_price"] is not None
        and value <= state["next_buy_price"]
    ):
        _buy_lot(state, timestamp)
    _update_order(state)
    return state


def stop(state: dict, now: str | None = None) -> dict:
    state = _upgrade(state)
    timestamp = now or _now()
    state.update({"status": "STOPPED", "order_side": None,
                  "order_price": None, "updated_at": timestamp})
    _event(state, timestamp, "STOP", state.get("current_price"), None)
    return state


class PaperGridRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return empty_state()
        return _upgrade(payload)

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)

    def reset(self) -> dict:
        state = empty_state()
        self.save(state)
        return state


def _buy_lot(state: dict, timestamp: str) -> None:
    fill = int(state["next_buy_price"])
    fee = fill * QUANTITY_PER_LEVEL * state["fee_rate"]
    lot = {"id": state["cycle_buys"] + 1, "entry_price": fill,
           "target_price": fill + state["spacing"],
           "quantity": QUANTITY_PER_LEVEL, "bought_at": timestamp}
    state["lots"].append(lot)
    state["cycle_buys"] += 1
    state["next_buy_price"] = (
        fill - state["spacing"] if state["cycle_buys"] < MAX_LEVELS else None
    )
    state["fees"] += fee
    state["net_profit_before_tax"] -= fee
    _event(state, timestamp, "BUY_FILLED", fill, lot["target_price"],
           buy_price=fill, level=lot["id"])


def _sell_lot(state: dict, lot: dict, timestamp: str) -> None:
    fill, entry = int(lot["target_price"]), int(lot["entry_price"])
    gross = (fill - entry) * lot["quantity"]
    fee = fill * lot["quantity"] * state["fee_rate"]
    invested = entry * lot["quantity"]
    state["lots"].remove(lot)
    state["cycles"] += 1
    state["gross_profit"] += gross
    state["fees"] += fee
    state["net_profit_before_tax"] += gross - fee
    _event(state, timestamp, "SELL_FILLED", fill, None, buy_price=entry,
           sell_price=fill, level=lot["id"], gross_return=gross / invested)
    # A completed sell frees one grid slot. Re-enter only after a small
    # pullback from that fill, whether other lots remain or not.
    state.update({
        "cycle_buys": len(state["lots"]),
        "next_buy_price": max(TICK_SIZE, fill - SELL_REENTRY_DISCOUNT),
    })
    if not state["lots"]:
        spacing, mode = _grid_spacing(fill)
        was_halted = state["status"] == "BUY_HALTED"
        state.update({"spacing": spacing, "spacing_mode": mode,
                      "anchor_price": fill, "overnight_holding": False})
        if not was_halted:
            state.update({"halt_reason": None, "buy_halted_date": None,
                          "risk_review_required": False, "status": "RUNNING"})


def _market_halt_reason(state: dict, quote: dict) -> str | None:
    change = quote.get("change_rate")
    open_price, previous_close = quote.get("open"), quote.get("previous_close")
    if previous_close and open_price and open_price / previous_close - 1 <= GAP_HALT_RATE:
        return "시가가 전일 종가 대비 3% 이상 갭 하락"
    if change is not None and change <= INTRADAY_HALT_RATE:
        return "전일 종가 대비 5% 이상 장중 하락"
    last = state.get("previous_observed_price")
    state["previous_observed_price"] = quote["close"]
    if last and quote["close"] <= last - 2 * state["spacing"]:
        return "직전 관측가에서 그리드 두 단계 이상 갭 하락"
    return None


def _update_risk_review(state: dict, value: int, timestamp: str) -> None:
    if not state["lots"]:
        return
    average = sum(
        lot["entry_price"] * lot["quantity"] for lot in state["lots"]
    ) / _holding_quantity(state)
    fifth = next((lot for lot in state["lots"] if lot["id"] == MAX_LEVELS), None)
    reason = None
    if value / average - 1 <= LOSS_REVIEW_RATE:
        reason = "평균단가 대비 7% 이상 하락"
    elif fifth and value / fifth["entry_price"] - 1 <= FIFTH_LEVEL_EXTRA_HALT_RATE:
        reason = "5차 매수가 대비 추가 3% 이상 하락"
    if reason and not state["risk_review_required"]:
        state.update({"risk_review_required": True, "halt_reason": reason,
                      "status": "BUY_HALTED",
                      "buy_halted_date": state.get("last_quote_date")})
        _event(state, timestamp, "RISK_REVIEW", value, None, reason=reason)


def _update_order(state: dict) -> None:
    if state["status"] == "STOPPED":
        state.update({"order_side": None, "order_price": None})
        return
    sell = min((lot["target_price"] for lot in state["lots"]), default=None)
    if sell is not None:
        state.update({"order_side": "SELL", "order_price": sell})
    elif state["status"] == "RUNNING" and state["next_buy_price"] is not None:
        state.update({"order_side": "BUY", "order_price": state["next_buy_price"]})
    else:
        state.update({"order_side": None, "order_price": None})


def _grid_spacing(anchor: int) -> tuple[int, str]:
    if 4_000 <= anchor <= 6_000:
        return DEFAULT_SPACING, "FIXED_100"
    spacing = max(
        TICK_SIZE, int(round(anchor * ADAPTIVE_SPACING_RATE / TICK_SIZE)) * TICK_SIZE
    )
    return spacing, "ADAPTIVE_2_PERCENT"


def _checked_quote(state: dict, value, now: str | None) -> tuple[dict, dict | None]:
    state = _upgrade(state)
    raw = dict(value) if isinstance(value, dict) else {"close": value}
    state["raw_quote"] = raw
    state["quote_checked_at"] = now or _now()
    try:
        quote = _quote(raw)
    except (ValueError, TypeError, KeyError, OverflowError):
        state["quote_warning"] = (
            "수신 시세가 유효하지 않거나 5원 호가 단위와 맞지 않습니다. "
            "이번 시세의 시작·가상 체결을 건너뛰고 기존 상태를 유지합니다."
        )
        return state, None
    state["quote_warning"] = None
    return state, quote


def _quote(value) -> dict:
    quote = dict(value) if isinstance(value, dict) else {"close": value}
    quote["close"] = _price(quote["close"])
    if quote.get("open") is not None:
        quote["open"] = _price(quote["open"])
    if quote.get("change_rate") is not None:
        quote["change_rate"] = float(quote["change_rate"])
        if quote["change_rate"] != -1:
            quote["previous_close"] = quote["close"] / (1 + quote["change_rate"])
    return quote


def _upgrade(state: dict) -> dict:
    merged = {**empty_state(), **state}
    if int(merged.get("schema_version", 1)) < 2:
        entry = merged.get("entry_price")
        spread = int(merged.get("target_spread", DEFAULT_SPACING))
        merged["lots"] = [] if entry is None else [{
            "id": 1, "entry_price": int(entry),
            "target_price": int(entry) + spread, "quantity": QUANTITY_PER_LEVEL,
            "bought_at": merged.get("updated_at"),
        }]
        merged["cycle_buys"] = len(merged["lots"])
        merged["spacing"] = spread
        merged["next_buy_price"] = (
            int(entry) - spread if entry else merged.get("order_price")
        )
        merged["status"] = (
            "STOPPED" if merged.get("status") == "STOPPED" else "RUNNING"
        )
    if int(merged.get("schema_version", 1)) < 3 and not merged["lots"]:
        last_sell = next(
            (
                event for event in merged.get("events", [])
                if event.get("type") == "SELL_FILLED"
            ),
            None,
        )
        if last_sell and last_sell.get("sell_price") is not None:
            merged["next_buy_price"] = max(
                TICK_SIZE, int(last_sell["sell_price"]) - SELL_REENTRY_DISCOUNT
            )
            merged["cycle_buys"] = 0
    merged["schema_version"] = 3
    return merged


def _holding_quantity(state: dict) -> int:
    return sum(int(lot["quantity"]) for lot in state["lots"])


def _record_quote_date(state: dict, quote: dict) -> None:
    if quote.get("date"):
        state["last_quote_date"] = str(quote["date"])


def _event(state: dict, timestamp: str, kind: str, price, next_order, **details) -> None:
    state["events"] = ([{"time": timestamp, "type": kind, "price": price,
                         "next_order_price": next_order, **details}]
                       + list(state.get("events") or []))[:500]


def _price(value: float) -> int:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("current price must be positive")
    if value % TICK_SIZE:
        raise ValueError("current price must follow the 5 won ETF tick size")
    return int(value)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

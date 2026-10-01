"""Explicitly gated Kiwoom mock order transport; not wired to automation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

import httpx

from broker.kiwoom.paper import (
    MOCK_BASE_URL,
    KiwoomPaperClient,
    KiwoomPaperCredentials,
    KiwoomPaperError,
    _api_error,
    _response_payload,
)
from trading.market_rules import MarketRuleDecision
from trading.model import (
    BrokerOrder,
    BrokerOrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
)
from trading.risk import RiskDecision


ORDER_PATH = "/api/dostk/ordr"


class KiwoomPaperOrderDisabled(KiwoomPaperError):
    pass


class KiwoomPaperSubmissionUncertain(KiwoomPaperError):
    pass


@dataclass(frozen=True, slots=True)
class PaperOrderAuthorization:
    intent_id: str
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.intent_id.strip():
            raise ValueError("intent_id is required")
        for name, value in (
            ("issued_at", self.issued_at), ("expires_at", self.expires_at)
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("authorization expiry must follow issue time")


def authorize_paper_order(
    request: BrokerOrderRequest,
    *,
    risk_decision: RiskDecision,
    market_decision: MarketRuleDecision,
    now: datetime,
    ttl: timedelta = timedelta(seconds=5),
) -> PaperOrderAuthorization:
    if not risk_decision.approved or risk_decision.request != request:
        raise ValueError("matching approved risk decision is required")
    if not market_decision.approved:
        raise ValueError("approved market rule decision is required")
    if ttl <= timedelta(0) or ttl > timedelta(seconds=10):
        raise ValueError("paper order authorization ttl must be 1-10 seconds")
    return PaperOrderAuthorization(request.intent_id, now, now + ttl)


class KiwoomPaperOrderGateway:
    """Single-attempt cash-order transport locked to the Kiwoom mock domain."""

    def __init__(
        self,
        credentials: KiwoomPaperCredentials,
        *,
        submission_enabled: bool = False,
        maximum_quantity: int = 1,
        base_url: str = MOCK_BASE_URL,
        http_client: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
        auth_client: KiwoomPaperClient | None = None,
        known_submitted_order_ids: frozenset[str] = frozenset(),
    ) -> None:
        if base_url.rstrip("/") != MOCK_BASE_URL:
            raise ValueError("Kiwoom paper orders only permit the mock domain")
        if maximum_quantity != 1:
            raise ValueError("the initial paper pilot is fixed to one share")
        if any(not value.strip() for value in known_submitted_order_ids):
            raise ValueError("known submitted order IDs must not be blank")
        self.submission_enabled = submission_enabled
        self.maximum_quantity = maximum_quantity
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._client = http_client or httpx.Client(
            base_url=MOCK_BASE_URL,
            timeout=httpx.Timeout(10.0),
            headers={"Content-Type": "application/json;charset=UTF-8"},
        )
        self._owns_client = http_client is None
        self._auth = auth_client or KiwoomPaperClient(
            credentials, http_client=self._client, clock=self.clock
        )
        self._consumed_intent_ids: set[str] = set()
        self._submitted_order_ids: set[str] = set(known_submitted_order_ids)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def submit_authorized(
        self,
        request: BrokerOrderRequest,
        authorization: PaperOrderAuthorization,
    ) -> BrokerOrder:
        self._verify_gate(request, authorization)
        self._consumed_intent_ids.add(request.intent_id)
        api_id = "kt10000" if request.side is OrderSide.BUY else "kt10001"
        if request.order_type is OrderType.MARKET:
            trade_type, order_price = "3", ""
        elif request.order_type is OrderType.LIMIT:
            if request.limit_price is None or request.limit_price != request.limit_price.to_integral_value():
                raise ValueError("Kiwoom KRX limit price must be an integer KRW value")
            trade_type, order_price = "0", str(int(request.limit_price))
        else:
            raise ValueError("unsupported paper order type")
        payload = self._post_once(api_id, {
            "dmst_stex_tp": "KRX",
            "stk_cd": request.symbol,
            "ord_qty": str(request.quantity),
            "ord_uv": order_price,
            "trde_tp": trade_type,
            "cond_uv": "",
        })
        order_id = str(payload.get("ord_no") or "").strip()
        if not order_id:
            raise KiwoomPaperSubmissionUncertain(
                "PAPER_ORDER_ID_MISSING",
                "mock order response did not include an order number",
            )
        self._submitted_order_ids.add(order_id)
        return BrokerOrder(
            order_id,
            request.intent_id,
            request.symbol,
            request.side,
            request.quantity,
            0,
            OrderStatus.ACCEPTED,
            self.clock(),
            request.limit_price,
        )

    def cancel_order(
        self,
        *,
        broker_order_id: str,
        symbol: str,
        quantity: int = 0,
    ) -> str:
        if not self.submission_enabled:
            raise KiwoomPaperOrderDisabled(
                "PAPER_ORDER_DISABLED", "mock order submission is disabled"
            )
        if not broker_order_id.strip():
            raise ValueError("broker_order_id is required")
        if broker_order_id not in self._submitted_order_ids:
            raise ValueError("cancel is limited to orders submitted by this gateway")
        if len(symbol) != 6 or not symbol.isdigit():
            raise ValueError("symbol must be a six-digit KRX code")
        if quantity not in (0, 1):
            raise ValueError("paper cancel quantity must be zero or one")
        payload = self._post_once("kt10003", {
            "dmst_stex_tp": "KRX",
            "orig_ord_no": broker_order_id,
            "stk_cd": symbol,
            "cncl_qty": str(quantity),
        })
        cancel_order_id = str(payload.get("ord_no") or "").strip()
        if not cancel_order_id:
            raise KiwoomPaperSubmissionUncertain(
                "PAPER_CANCEL_ID_MISSING",
                "mock cancel response did not include an order number",
            )
        return cancel_order_id

    def _verify_gate(
        self,
        request: BrokerOrderRequest,
        authorization: PaperOrderAuthorization,
    ) -> None:
        if not self.submission_enabled:
            raise KiwoomPaperOrderDisabled(
                "PAPER_ORDER_DISABLED", "mock order submission is disabled"
            )
        now = self.clock()
        if authorization.intent_id != request.intent_id:
            raise ValueError("authorization does not match the order intent")
        if now < authorization.issued_at or now > authorization.expires_at:
            raise ValueError("paper order authorization is expired")
        if request.quantity != self.maximum_quantity:
            raise ValueError("the initial paper pilot permits exactly one share")
        if request.intent_id in self._consumed_intent_ids:
            raise ValueError("paper order authorization was already consumed")

    def _post_once(self, api_id: str, body: dict[str, str]) -> dict:
        headers = {
            "authorization": f"Bearer {self._auth.access_token()}",
            "api-id": api_id,
        }
        try:
            response = self._client.post(ORDER_PATH, headers=headers, json=body)
        except httpx.HTTPError as error:
            raise KiwoomPaperSubmissionUncertain(
                "PAPER_ORDER_TRANSPORT_UNCERTAIN", type(error).__name__
            ) from error
        payload = _response_payload(response)
        if response.is_error or payload.get("return_code") not in (None, 0, "0"):
            raise _api_error(response, payload, "PAPER_ORDER_REJECTED")
        return payload

"""Operator-approved bridge from the journal-first coordinator to Kiwoom paper orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from broker.kiwoom.paper_order import (
    KiwoomPaperOrderDisabled,
    KiwoomPaperOrderGateway,
    authorize_paper_order,
)
from trading.market_rules import MarketRuleDecision, validate_market_order
from trading.model import BrokerOrder
from trading.paper_operator_control import PaperOperatorControl
from trading.risk import RiskContext, RiskDecision


@dataclass(frozen=True, slots=True)
class OperatorApproval:
    intent_id: str
    operator_ref: str
    approved_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.intent_id.strip() or not self.operator_ref.strip():
            raise ValueError("intent_id and operator_ref are required")
        for name, value in (("approved_at", self.approved_at), ("expires_at", self.expires_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.expires_at <= self.approved_at:
            raise ValueError("operator approval expiry must follow approval time")


class KiwoomPaperApprovedSubmitter:
    """One-shot manual approvals for coordinator-owned paper submissions.

    Approval issuance is disabled by default and cannot be enabled by environment
    variables. The caller must explicitly construct this bridge with approval
    enabled, then grant each intent separately.
    """

    def __init__(
        self,
        gateway: KiwoomPaperOrderGateway,
        *,
        operator_approval_enabled: bool = False,
        clock: Callable[[], datetime] | None = None,
        approval_ttl: timedelta = timedelta(seconds=30),
        operator_control: PaperOperatorControl | None = None,
    ) -> None:
        if approval_ttl <= timedelta(0) or approval_ttl > timedelta(minutes=5):
            raise ValueError("operator approval ttl must be positive and at most five minutes")
        self.gateway = gateway
        self.operator_approval_enabled = operator_approval_enabled
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.approval_ttl = approval_ttl
        self.operator_control = operator_control
        self._approvals: dict[str, OperatorApproval] = {}
        self._prepared: dict[str, tuple[OperatorApproval, MarketRuleDecision]] = {}

    def grant(self, intent_id: str, *, operator_ref: str) -> OperatorApproval:
        if not self.operator_approval_enabled:
            raise KiwoomPaperOrderDisabled(
                "PAPER_OPERATOR_APPROVAL_DISABLED",
                "operator approval issuance is disabled",
            )
        now = self.clock()
        approval = OperatorApproval(
            intent_id, operator_ref, now, now + self.approval_ttl
        )
        self._approvals[intent_id] = approval
        return approval

    def __call__(self, decision: RiskDecision, context: RiskContext) -> BrokerOrder:
        return self.submit(decision, context)

    def approval_event_payload(self, decision: RiskDecision) -> dict:
        request = decision.request
        if request is None:
            raise ValueError("request is required")
        prepared = self._prepared.get(request.intent_id)
        if prepared is None:
            raise ValueError("operator approval was not prepared")
        approval = prepared[0]
        return {
            "action": "KIWOOM_PAPER_ORDER_APPROVED",
            "operator_ref": approval.operator_ref,
            "approved_at": approval.approved_at,
            "expires_at": approval.expires_at,
        }

    def submit(self, decision: RiskDecision, context: RiskContext) -> BrokerOrder:
        request = decision.request
        if request is None:
            raise ValueError("request is required")
        prepared = self._prepared.pop(request.intent_id, None)
        if prepared is None:
            self.prepare_submission(decision, context)
            prepared = self._prepared.pop(request.intent_id)
        approval, market_decision = prepared
        now = self.clock()
        if self.operator_control is not None:
            try:
                self.operator_control.require_kill_switch_released()
            except ValueError as error:
                raise KiwoomPaperOrderDisabled(
                    "PAPER_KILL_SWITCH_ACTIVE", str(error)
                ) from error
        if now > approval.expires_at:
            raise KiwoomPaperOrderDisabled(
                "PAPER_OPERATOR_APPROVAL_EXPIRED",
                "operator approval expired before submission",
            )
        authorization = authorize_paper_order(
            request,
            risk_decision=decision,
            market_decision=market_decision,
            now=now,
        )
        return self.gateway.submit_authorized(request, authorization)

    def prepare_submission(
        self, decision: RiskDecision, context: RiskContext
    ) -> tuple[OperatorApproval, MarketRuleDecision]:
        request = decision.request
        if not decision.approved or request is None:
            raise ValueError("approved risk decision with request is required")
        if request.intent_id in self._prepared:
            raise ValueError("operator approval was already prepared")
        if self.operator_control is None:
            approval, market_decision = self.preflight(decision, context)
            self._approvals.pop(request.intent_id, None)
        else:
            try:
                stored = self.operator_control.consume_approval(request.intent_id)
            except ValueError as error:
                raise KiwoomPaperOrderDisabled(
                    "PAPER_OPERATOR_APPROVAL_REQUIRED", str(error)
                ) from error
            approval = OperatorApproval(
                stored["intent_id"],
                stored["operator_ref"],
                datetime.fromisoformat(stored["decided_at"]),
                datetime.fromisoformat(stored["expires_at"]),
            )
            market_decision = self._validate_market(decision, context)
        self._prepared[request.intent_id] = (approval, market_decision)
        return approval, market_decision

    def preflight(
        self, decision: RiskDecision, context: RiskContext
    ) -> tuple[OperatorApproval, MarketRuleDecision]:
        request = decision.request
        if not decision.approved or request is None:
            raise ValueError("approved risk decision with request is required")
        approval = self._approvals.get(request.intent_id)
        now = self.clock()
        if approval is None:
            raise KiwoomPaperOrderDisabled(
                "PAPER_OPERATOR_APPROVAL_REQUIRED",
                "a one-shot operator approval is required",
            )
        if now < approval.approved_at or now > approval.expires_at:
            self._approvals.pop(request.intent_id, None)
            raise KiwoomPaperOrderDisabled(
                "PAPER_OPERATOR_APPROVAL_EXPIRED",
                "operator approval expired before submission",
            )
        market_decision = self._validate_market(decision, context)
        return approval, market_decision

    def _validate_market(
        self, decision: RiskDecision, context: RiskContext
    ) -> MarketRuleDecision:
        if context.market_rules is None:
            raise KiwoomPaperOrderDisabled(
                "PAPER_MARKET_RULES_REQUIRED",
                "fresh KRX market rules are required",
            )
        market_decision = validate_market_order(
            _request_as_intent(decision, context),
            context.market_rules,
            now=context.now,
            maximum_age_seconds=5,
        )
        if not market_decision.approved:
            raise KiwoomPaperOrderDisabled(
                "PAPER_MARKET_RULES_REJECTED",
                ",".join(reason.value for reason in market_decision.reasons),
            )
        return market_decision


def _request_as_intent(decision: RiskDecision, context: RiskContext):
    """Rebuild the minimal immutable intent needed by the market-rule validator."""
    from trading.model import OrderIntent

    request = decision.request
    if request is None:  # pragma: no cover - guarded by submit
        raise ValueError("request is required")
    return OrderIntent(
        request.intent_id,
        "KIWOOM-PAPER-APPROVED",
        request.symbol,
        request.side,
        request.quantity,
        request.order_type,
        context.now,
        request.limit_price,
        "operator-approved coordinator submission",
    )

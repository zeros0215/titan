"""Manually approved S80 paper-order submission with fresh fail-closed checks."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from broker.kiwoom import (
    KiwoomPaperClient,
    KiwoomPaperCredentials,
    KiwoomPaperMarketSessionClient,
)
from broker.kiwoom.paper_execution import KiwoomPaperApprovedSubmitter
from broker.kiwoom.paper_order import KiwoomPaperOrderGateway
from trading.coordinator import CoordinationResult, OrderCoordinator
from trading.journal import SQLiteExecutionJournal
from trading.market_rules import MarketRulesSnapshot
from trading.model import (
    AccountSnapshot, BrokerOrder, MarketQuote, OrderIntent, OrderSide,
    OrderStatus, OrderType, Position, TradingMode,
)
from trading.paper_dashboard import STRATEGY_VERSION, load_paper_dashboard
from trading.paper_operator_control import PaperOperatorControl
from trading.paper_position_lifecycle import (
    exit_signal, holding_sessions, managed_s80_symbols,
)
from trading.reconciliation import ReconciliationResult
from trading.risk import RiskContext, RiskLimits, RiskManager


SEOUL = ZoneInfo("Asia/Seoul")


def submit_s80_paper_candidate(
    intent_id: str,
    *,
    dashboard_path: Path,
    control_path: Path,
    journal_path: Path,
    credentials: KiwoomPaperCredentials | None = None,
    reader: KiwoomPaperClient | None = None,
) -> CoordinationResult:
    state = load_paper_dashboard(dashboard_path)
    candidate = next(
        (item for item in state["candidates"] if item.get("intent_id") == intent_id),
        None,
    )
    if candidate is None or not candidate.get("eligible"):
        raise ValueError("eligible S80 candidate was not found")
    if not candidate.get("approval_enabled"):
        raise ValueError("candidate order submission is disabled")
    symbol = str(candidate.get("code") or "")
    if len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("candidate symbol is invalid")

    credentials = credentials or KiwoomPaperCredentials.from_environment()
    owns_reader = reader is None
    reader = reader or KiwoomPaperClient(credentials)
    gateway = None
    try:
        access_token = reader.access_token()
        account_raw = reader.account_snapshot()
        today_orders = reader.order_fill_details(order_date=datetime.now(timezone.utc))
        if any(item.code == symbol for item in account_raw.positions):
            raise ValueError("candidate is already held")
        if any(item.symbol == symbol for item in today_orders):
            raise ValueError("candidate already has an order today")
        if len(account_raw.positions) >= 7:
            raise ValueError("maximum seven paper positions reached")
        session = KiwoomPaperMarketSessionClient(credentials).current_session(
            access_token=access_token
        )
        if not session.regular_session_open:
            raise ValueError("KRX regular session is not open")
        info = reader.stock_info(symbol)
        opening_gap = info.open_price / info.reference_price - Decimal("1")
        if abs(opening_gap) > Decimal("0.03"):
            raise ValueError("opening gap exceeds the S80 three percent limit")

        now = datetime.now(timezone.utc)
        account = AccountSnapshot(
            "kiwoom_paper", account_raw.synchronized_at,
            account_raw.cash, account_raw.buying_power,
            tuple(Position(
                item.code, item.quantity, item.entry_price, item.current_price
            ) for item in account_raw.positions),
        )
        open_orders = tuple(
            BrokerOrder(
                item.broker_order_id, f"broker-{item.broker_order_id}",
                item.symbol, item.side, item.requested_quantity,
                item.filled_quantity,
                OrderStatus.ACCEPTED if item.remaining_quantity else OrderStatus.FILLED,
                item.ordered_at, item.order_price or None,
            )
            for item in today_orders if item.remaining_quantity
        )
        strategy_version = str(candidate.get("strategy_version") or "")
        if strategy_version not in {
            STRATEGY_VERSION, "V1.3-S80-OBSERVATION-PAPER"
        }:
            raise ValueError("candidate strategy version is invalid")
        intent = OrderIntent(
            intent_id, strategy_version, symbol, OrderSide.BUY, 1,
            OrderType.MARKET, now,
            rationale=f"S80 {candidate.get('cohort')} paper candidate; approved",
        )
        rules = MarketRulesSnapshot(
            symbol, "KRX", info.observed_at, session.regular_session_open, info.reference_price,
            info.lower_limit_price, info.upper_limit_price, Decimal("1"),
        )
        control = PaperOperatorControl(control_path)
        context = RiskContext(
            TradingMode.PAPER, now, account, ReconciliationResult(True, ()),
            MarketQuote(symbol, info.observed_at, info.current_price,
                        info.current_price, info.current_price),
            open_orders=open_orders,
            kill_switch_active=control.load()["kill_switch_active"],
            market_rules=rules,
        )
        risk = RiskManager(RiskLimits(
            Decimal("500000"), Decimal("500000"), Decimal("3500000"),
            Decimal("100000"), max_open_orders=7,
            allowed_symbols=frozenset({symbol}), require_market_rules=True,
        ))
        gateway = KiwoomPaperOrderGateway(
            credentials, submission_enabled=True, auth_client=reader
        )
        submitter = KiwoomPaperApprovedSubmitter(
            gateway, operator_control=control
        )
        journal = SQLiteExecutionJournal(
            journal_path, mode=TradingMode.PAPER, account_ref="kiwoom_paper"
        )
        return OrderCoordinator(
            gateway, journal, risk, approved_submitter=submitter
        ).submit(intent, context)
    finally:
        if gateway is not None:
            gateway.close()
        if owns_reader:
            reader.close()


def submit_s80_paper_exit(
    intent_id: str,
    *,
    dashboard_path: Path,
    control_path: Path,
    journal_path: Path,
    credentials: KiwoomPaperCredentials | None = None,
    reader: KiwoomPaperClient | None = None,
    manual: bool = False,
) -> CoordinationResult:
    state = load_paper_dashboard(dashboard_path)
    intent_field = "manual_exit_intent_id" if manual else "exit_intent_id"
    enabled_field = "manual_exit_enabled" if manual else "exit_approval_enabled"
    projected = next(
        (item for item in state["positions"] if item.get(intent_field) == intent_id),
        None,
    )
    if projected is None or not projected.get(enabled_field):
        raise ValueError(
            "approved S80 manual exit was not found"
            if manual else "approved S80 exit signal was not found"
        )
    symbol = str(projected.get("code") or "")
    journal = SQLiteExecutionJournal(
        journal_path, mode=TradingMode.PAPER, account_ref="kiwoom_paper"
    )
    if symbol not in managed_s80_symbols(journal):
        raise ValueError("position is not owned by the S80 paper strategy")

    credentials = credentials or KiwoomPaperCredentials.from_environment()
    owns_reader = reader is None
    reader = reader or KiwoomPaperClient(credentials)
    gateway = None
    try:
        access_token = reader.access_token()
        account_raw = reader.account_snapshot()
        position = next(
            (item for item in account_raw.positions if item.code == symbol), None
        )
        if position is None or position.quantity != 1 or position.sellable_quantity < 1:
            raise ValueError("exactly one sellable S80 paper share is required")
        today_orders = reader.order_fill_details(order_date=datetime.now(timezone.utc))
        if any(item.symbol == symbol and item.side is OrderSide.SELL for item in today_orders):
            raise ValueError("candidate already has a sell order today")
        session = KiwoomPaperMarketSessionClient(credentials).current_session(
            access_token=access_token
        )
        if not session.regular_session_open:
            raise ValueError("KRX regular session is not open")
        info = reader.stock_info(symbol)
        opened_on = datetime.fromisoformat(
            str(projected.get("opened_on"))
        ).date()
        sessions = holding_sessions(
            opened_on, account_raw.synchronized_at.astimezone(SEOUL).date()
        )
        fresh_signal = exit_signal(position.entry_price, info.current_price, sessions)
        if not manual and (
            fresh_signal is None or fresh_signal != projected.get("exit_signal")
        ):
            raise ValueError("S80 exit signal is no longer current")

        now = datetime.now(timezone.utc)
        account = AccountSnapshot(
            "kiwoom_paper", account_raw.synchronized_at,
            account_raw.cash, account_raw.buying_power,
            tuple(Position(
                item.code, item.quantity, item.entry_price, item.current_price
            ) for item in account_raw.positions),
        )
        intent = OrderIntent(
            intent_id, STRATEGY_VERSION, symbol, OrderSide.SELL, 1,
            OrderType.MARKET, now, rationale=(
                "S80 emergency manual exit"
                if manual else f"S80 exit signal: {fresh_signal}"
            ),
        )
        rules = MarketRulesSnapshot(
            symbol, "KRX", info.observed_at, session.regular_session_open,
            info.reference_price, info.lower_limit_price,
            info.upper_limit_price, Decimal("1"),
        )
        control = PaperOperatorControl(control_path)
        context = RiskContext(
            TradingMode.PAPER, now, account, ReconciliationResult(True, ()),
            MarketQuote(symbol, info.observed_at, info.current_price,
                        info.current_price, info.current_price),
            kill_switch_active=control.load()["kill_switch_active"],
            market_rules=rules,
        )
        risk = RiskManager(RiskLimits(
            Decimal("500000"), Decimal("500000"), Decimal("3500000"),
            Decimal("100000"), max_open_orders=7,
            allowed_symbols=frozenset({symbol}), require_market_rules=True,
        ))
        gateway = KiwoomPaperOrderGateway(
            credentials, submission_enabled=True, auth_client=reader
        )
        submitter = KiwoomPaperApprovedSubmitter(
            gateway, operator_control=control
        )
        return OrderCoordinator(
            gateway, journal, risk, approved_submitter=submitter
        ).submit(intent, context)
    finally:
        if gateway is not None:
            gateway.close()
        if owns_reader:
            reader.close()

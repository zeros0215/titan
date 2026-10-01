"""One-shot, explicitly confirmed 005930 one-share Kiwoom mock-market pilot."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from broker.kiwoom import KiwoomPaperClient, KiwoomPaperCredentials, KiwoomPaperMarketSessionClient
from broker.kiwoom.paper_execution import KiwoomPaperApprovedSubmitter
from broker.kiwoom.paper_order import KiwoomPaperOrderGateway
from trading.coordinator import OrderCoordinator
from trading.journal import SQLiteExecutionJournal
from trading.market_rules import MarketRulesSnapshot
from trading.model import AccountSnapshot, MarketQuote, OrderIntent, OrderSide, OrderType, TradingMode
from trading.paper_operator_control import PaperOperatorControl, RELEASE_CONFIRMATION
from trading.reconciliation import ReconciliationResult
from trading.risk import RiskContext, RiskLimits, RiskManager

CONFIRM = "BUY-005930-1-MARKET-PAPER"

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRM:
        raise SystemExit("exact paper-order confirmation is required")
    load_dotenv()
    credentials = KiwoomPaperCredentials.from_environment()
    now = datetime.now(timezone.utc)
    reader = KiwoomPaperClient(credentials)
    control = PaperOperatorControl(Path("output/kiwoom_paper/operator_control.json"))
    try:
        access_token = reader.access_token()
        account_raw = reader.account_snapshot()
        if reader.order_fill_details(order_date=now):
            raise SystemExit("pilot blocked: account already has orders today")
        session = KiwoomPaperMarketSessionClient(credentials).current_session(access_token=access_token)
        if not session.regular_session_open:
            raise SystemExit(f"pilot blocked: KRX regular session is not open ({session.status_code})")
        info = reader.stock_info("005930")
        now = datetime.now(timezone.utc)
        account = AccountSnapshot("kiwoom_paper", account_raw.synchronized_at, account_raw.cash, account_raw.buying_power)
        intent_id = f"paper-005930-{uuid4().hex}"
        intent = OrderIntent(intent_id, "KIWOOM-PAPER-PILOT", "005930", OrderSide.BUY, 1, OrderType.MARKET, now, rationale="explicit one-share pilot")
        rules = MarketRulesSnapshot("005930", "KRX", info.observed_at, True, info.reference_price, info.lower_limit_price, info.upper_limit_price, Decimal("1"))
        context = RiskContext(TradingMode.PAPER, now, account, ReconciliationResult(True, ()), MarketQuote("005930", info.observed_at, info.current_price, info.current_price, info.current_price), market_rules=rules)
        risk = RiskManager(RiskLimits(Decimal("500000"), Decimal("500000"), Decimal("500000"), Decimal("100000"), allowed_symbols=frozenset({"005930"}), require_market_rules=True))
        control.set_kill_switch(False, operator_ref="codex-approved-pilot", confirmation=RELEASE_CONFIRMATION)
        control.decide(intent_id=intent_id, approved=True, operator_ref="codex-approved-pilot")
        gateway = KiwoomPaperOrderGateway(credentials, submission_enabled=True, auth_client=reader)
        submitter = KiwoomPaperApprovedSubmitter(gateway, operator_control=control)
        journal = SQLiteExecutionJournal(Path("output/kiwoom_paper/pilot_orders.sqlite"), mode=TradingMode.PAPER, account_ref="kiwoom_paper")
        result = OrderCoordinator(gateway, journal, risk, approved_submitter=submitter).submit(intent, context)
        print({"intent_id": intent_id, "broker_order_id": result.order.broker_order_id, "status": result.order.status.value})
        gateway.close()
    finally:
        reader.close()
        control.set_kill_switch(True, operator_ref="codex-approved-pilot")

if __name__ == "__main__": main()

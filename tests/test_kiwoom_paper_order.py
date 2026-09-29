import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

from broker.kiwoom.paper import KiwoomPaperCredentials
from broker.kiwoom.paper_order import (
    KiwoomPaperOrderDisabled,
    KiwoomPaperOrderGateway,
    KiwoomPaperSubmissionUncertain,
    authorize_paper_order,
)
from trading.market_rules import MarketRuleDecision, MarketRuleReason
from trading.model import BrokerOrderRequest, OrderSide, OrderType
from trading.risk import RiskDecision, RiskReason


NOW = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


class KiwoomPaperOrderGatewayTest(unittest.TestCase):
    def request(self, *, side=OrderSide.BUY, order_type=OrderType.MARKET):
        return BrokerOrderRequest(
            "intent-1", "005930", side, 1, order_type,
            Decimal("70000") if order_type is OrderType.LIMIT else None,
        )

    def authorization(self, request):
        return authorize_paper_order(
            request,
            risk_decision=RiskDecision(
                True,
                (RiskReason.APPROVED,),
                Decimal("70000"),
                Decimal("70000"),
                request,
            ),
            market_decision=MarketRuleDecision(
                True, (MarketRuleReason.APPROVED,)
            ),
            now=NOW,
        )

    def gateway(self, handler, *, enabled=True):
        return KiwoomPaperOrderGateway(
            KiwoomPaperCredentials("paper-key", "paper-secret"),
            submission_enabled=enabled,
            http_client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url="https://mockapi.kiwoom.com",
            ),
            clock=lambda: NOW,
        )

    @staticmethod
    def token_response(request):
        return httpx.Response(200, json={
            "token": "private-token",
            "expires_dt": "20300102030405",
        })

    def test_disabled_gateway_makes_no_network_request(self) -> None:
        calls = []
        gateway = self.gateway(lambda request: calls.append(request), enabled=False)
        request = self.request()

        with self.assertRaises(KiwoomPaperOrderDisabled):
            gateway.submit_authorized(request, self.authorization(request))

        self.assertEqual([], calls)

    def test_submits_one_share_market_buy_with_exact_official_contract(self) -> None:
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.path == "/oauth2/token":
                return self.token_response(request)
            self.assertEqual(request.headers["api-id"], "kt10000")
            self.assertEqual(
                request.read().decode(),
                '{"dmst_stex_tp":"KRX","stk_cd":"005930",'
                '"ord_qty":"1","ord_uv":"","trde_tp":"3","cond_uv":""}',
            )
            return httpx.Response(200, json={
                "ord_no": "0000024", "return_code": 0,
                "return_msg": "정상적으로 처리되었습니다",
            })

        gateway = self.gateway(handler)
        request = self.request()
        order = gateway.submit_authorized(request, self.authorization(request))

        self.assertEqual("0000024", order.broker_order_id)
        self.assertEqual(2, len(calls))

    def test_submits_limit_sell_and_maps_integer_price(self) -> None:
        def handler(request):
            if request.url.path == "/oauth2/token":
                return self.token_response(request)
            self.assertEqual(request.headers["api-id"], "kt10001")
            self.assertIn('"ord_uv":"70000"', request.read().decode())
            self.assertIn('"trde_tp":"0"', request.read().decode())
            return httpx.Response(200, json={
                "ord_no": "0000138", "return_code": 0,
            })

        gateway = self.gateway(handler)
        request = self.request(side=OrderSide.SELL, order_type=OrderType.LIMIT)
        order = gateway.submit_authorized(request, self.authorization(request))
        self.assertEqual(OrderSide.SELL, order.side)

    def test_transport_timeout_is_uncertain_and_never_retried(self) -> None:
        order_calls = 0

        def handler(request):
            nonlocal order_calls
            if request.url.path == "/oauth2/token":
                return self.token_response(request)
            order_calls += 1
            raise httpx.ReadTimeout("unknown outcome", request=request)

        gateway = self.gateway(handler)
        request = self.request()
        authorization = self.authorization(request)
        with self.assertRaises(KiwoomPaperSubmissionUncertain):
            gateway.submit_authorized(request, authorization)
        with self.assertRaisesRegex(ValueError, "already consumed"):
            gateway.submit_authorized(request, authorization)

        self.assertEqual(1, order_calls)

    def test_cancel_uses_krx_cancel_contract(self) -> None:
        order_submitted = False

        def handler(request):
            nonlocal order_submitted
            if request.url.path == "/oauth2/token":
                return self.token_response(request)
            if request.headers["api-id"] == "kt10000":
                order_submitted = True
                return httpx.Response(200, json={
                    "ord_no": "0000024", "return_code": 0,
                })
            self.assertEqual(request.headers["api-id"], "kt10003")
            self.assertEqual(
                request.read().decode(),
                '{"dmst_stex_tp":"KRX","orig_ord_no":"0000024",'
                '"stk_cd":"005930","cncl_qty":"0"}',
            )
            return httpx.Response(200, json={
                "ord_no": "0000025", "return_code": 0,
            })

        gateway = self.gateway(handler)
        request = self.request()
        gateway.submit_authorized(request, self.authorization(request))
        result = gateway.cancel_order(
            broker_order_id="0000024", symbol="005930"
        )
        self.assertTrue(order_submitted)
        self.assertEqual("0000025", result)

    def test_cancel_refuses_order_not_submitted_by_gateway(self) -> None:
        gateway = self.gateway(lambda request: self.token_response(request))
        with self.assertRaisesRegex(ValueError, "submitted by this gateway"):
            gateway.cancel_order(
                broker_order_id="manual-order", symbol="005930"
            )

    def test_authorization_requires_both_approvals_and_short_ttl(self) -> None:
        request = self.request()
        rejected_risk = RiskDecision(
            False, (RiskReason.KILL_SWITCH_ACTIVE,), None, None, None
        )
        market = MarketRuleDecision(True, (MarketRuleReason.APPROVED,))
        with self.assertRaisesRegex(ValueError, "risk decision"):
            authorize_paper_order(
                request, risk_decision=rejected_risk,
                market_decision=market, now=NOW,
            )
        with self.assertRaisesRegex(ValueError, "ttl"):
            authorize_paper_order(
                request,
                risk_decision=RiskDecision(
                    True, (RiskReason.APPROVED,), Decimal("1"),
                    Decimal("1"), request,
                ),
                market_decision=market,
                now=NOW,
                ttl=timedelta(minutes=1),
            )


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from broker.kiwoom.paper import (
    KiwoomPaperClient,
    KiwoomPaperCredentials,
)


class KiwoomPaperClientTest(unittest.TestCase):
    def test_rejects_live_domain(self) -> None:
        with self.assertRaisesRegex(ValueError, "mock domain"):
            KiwoomPaperClient(
                KiwoomPaperCredentials("paper-key", "paper-secret"),
                base_url="https://api.kiwoom.com",
            )

    def test_authenticates_and_reads_deposit_and_krx_balance(self) -> None:
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/oauth2/token":
                self.assertEqual(
                    request.read().decode(),
                    '{"grant_type":"client_credentials","appkey":"paper-key",'
                    '"secretkey":"paper-secret"}',
                )
                return httpx.Response(200, json={
                    "token": "private-token",
                    "token_type": "Bearer",
                    "expires_dt": "20300102030405",
                })
            api_id = request.headers["api-id"]
            self.assertEqual(request.headers["authorization"], "Bearer private-token")
            if api_id == "kt00001":
                return httpx.Response(200, json={
                    "return_code": 0,
                    "entr": "2000000",
                    "ord_alow_amt": "1900000",
                })
            self.assertEqual(api_id, "kt00018")
            self.assertEqual(
                request.read().decode(),
                '{"qry_tp":"1","dmst_stex_tp":"KRX"}',
            )
            return httpx.Response(200, json={
                "return_code": 0,
                "tot_evlt_amt": "100000",
                "tot_evlt_pl": "-5000",
                "acnt_evlt_remn_indv_tot": [{
                    "stk_cd": "A005930",
                    "stk_nm": "삼성전자",
                    "rmnd_qty": "1",
                    "trde_able_qty": "1",
                    "pur_pric": "105000",
                    "cur_prc": "100000",
                    "evlt_amt": "100000",
                    "evltv_prft": "-5000",
                    "prft_rt": "-4.76",
                }],
            })

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(
            transport=transport, base_url="https://mockapi.kiwoom.com"
        )
        client = KiwoomPaperClient(
            KiwoomPaperCredentials("paper-key", "paper-secret"),
            http_client=http_client,
            clock=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
            wait=lambda _: None,
        )
        snapshot = client.account_snapshot()

        self.assertEqual(snapshot.cash, Decimal("2000000"))
        self.assertEqual(snapshot.buying_power, Decimal("1900000"))
        self.assertEqual(snapshot.unrealized_pnl, Decimal("-5000"))
        self.assertEqual(snapshot.positions[0].code, "005930")
        self.assertEqual(snapshot.positions[0].quantity, 1)
        self.assertEqual(snapshot.positions[0].return_rate, Decimal("-0.0476"))
        self.assertEqual(len(requests), 3)

    def test_account_error_does_not_expose_credentials_or_token(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2/token":
                return httpx.Response(200, json={
                    "token": "private-token",
                    "expires_dt": "20300102030405",
                })
            return httpx.Response(400, json={
                "return_code": "AUTH_401",
                "return_msg": "access denied",
            })

        client = KiwoomPaperClient(
            KiwoomPaperCredentials("paper-key", "paper-secret"),
            http_client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url="https://mockapi.kiwoom.com",
            ),
            clock=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
            wait=lambda _: None,
        )
        with self.assertRaises(Exception) as raised:
            client.account_snapshot()
        message = str(raised.exception)
        self.assertNotIn("paper-secret", message)
        self.assertNotIn("private-token", message)

    def test_reads_order_fill_details_with_krx_only_contract(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2/token":
                return httpx.Response(200, json={
                    "token": "private-token",
                    "expires_dt": "20300102030405",
                })
            self.assertEqual(request.headers["api-id"], "kt00007")
            self.assertEqual(request.url.path, "/api/dostk/acnt")
            self.assertEqual(
                request.read().decode(),
                '{"qry_tp":"1","stk_bond_tp":"1","sell_tp":"0",'
                '"dmst_stex_tp":"KRX","ord_dt":"20260929",'
                '"stk_cd":"005930","fr_ord_no":""}',
            )
            return httpx.Response(200, json={
                "return_code": 0,
                "acnt_ord_cntr_prps_dtl": [{
                    "ord_no": "0000024",
                    "stk_cd": "A005930",
                    "trde_tp": "2",
                    "io_tp_nm": "+매수",
                    "ord_qty": "1",
                    "ord_uv": "70000",
                    "cntr_uv": "70100",
                    "cntr_qty": "1",
                    "ord_remnq": "0",
                    "ord_tm": "09:00:15",
                    "dmst_stex_tp": "KRX",
                }],
            })

        client = KiwoomPaperClient(
            KiwoomPaperCredentials("paper-key", "paper-secret"),
            http_client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url="https://mockapi.kiwoom.com",
            ),
            clock=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
            wait=lambda _: None,
        )
        orders = client.order_fill_details(
            order_date=datetime(2026, 9, 29, tzinfo=timezone.utc),
            symbol="005930",
        )

        self.assertEqual("0000024", orders[0].broker_order_id)
        self.assertEqual("005930", orders[0].symbol)
        self.assertEqual(1, orders[0].filled_quantity)
        self.assertEqual(Decimal("70100"), orders[0].order_price)
        self.assertEqual("KRX", orders[0].venue)
        self.assertEqual((9, 0, 15), (
            orders[0].ordered_at.hour,
            orders[0].ordered_at.minute,
            orders[0].ordered_at.second,
        ))

    def test_reads_stock_info_with_official_daily_limits(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2/token":
                return httpx.Response(200, json={
                    "token": "private-token", "expires_dt": "20300102030405",
                })
            self.assertEqual("ka10001", request.headers["api-id"])
            self.assertEqual("/api/dostk/stkinfo", request.url.path)
            self.assertEqual('{"stk_cd":"005930"}', request.read().decode())
            return httpx.Response(200, json={
                "return_code": 0,
                "stk_cd": "A005930",
                "stk_nm": "삼성전자",
                "cur_prc": "+70100",
                "base_pric": "70000",
                "open_pric": "+69500",
                "lst_pric": "49000",
                "upl_pric": "91000",
            })

        client = KiwoomPaperClient(
            KiwoomPaperCredentials("paper-key", "paper-secret"),
            http_client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url="https://mockapi.kiwoom.com",
            ),
            clock=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
            wait=lambda _: None,
        )
        info = client.stock_info("005930")

        self.assertEqual("005930", info.symbol)
        self.assertEqual("삼성전자", info.name)
        self.assertEqual(Decimal("70100"), info.current_price)
        self.assertEqual(Decimal("69500"), info.open_price)
        self.assertEqual(Decimal("49000"), info.lower_limit_price)
        self.assertEqual(Decimal("91000"), info.upper_limit_price)

    def test_read_only_stock_info_retries_mock_rate_limit(self) -> None:
        calls = 0
        waits = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            if request.url.path == "/oauth2/token":
                return httpx.Response(200, json={
                    "token": "private-token", "expires_dt": "20300102030405",
                })
            calls += 1
            if calls == 1:
                return httpx.Response(200, json={
                    "return_code": 5,
                    "return_msg": "허용된 요청 개수를 초과하였습니다[1700]",
                })
            return httpx.Response(200, json={
                "return_code": 0, "stk_cd": "005930", "stk_nm": "삼성전자",
                "cur_prc": "100", "base_pric": "100", "open_pric": "100",
                "lst_pric": "70", "upl_pric": "130",
            })

        client = KiwoomPaperClient(
            KiwoomPaperCredentials("paper-key", "paper-secret"),
            http_client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url="https://mockapi.kiwoom.com",
            ),
            clock=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
            wait=waits.append,
        )
        self.assertEqual("005930", client.stock_info("005930").symbol)
        self.assertEqual(2, calls)
        self.assertIn(1.25, waits)


if __name__ == "__main__":
    unittest.main()

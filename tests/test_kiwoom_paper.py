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
                    "cntr_qty": "1",
                    "ord_remnq": "0",
                    "ord_tm": "090015",
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
        self.assertEqual("KRX", orders[0].venue)


if __name__ == "__main__":
    unittest.main()

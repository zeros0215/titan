import unittest
from unittest.mock import patch
import httpx

from broker.kis.client import KisClient, KisReadOnlyClient
from broker.kis.exception import KisApiException


class KisClientTest(unittest.TestCase):
    def test_read_only_client_blocks_non_auth_post(self) -> None:
        client = object.__new__(KisReadOnlyClient)
        client.order_request_count = 0

        with self.assertRaisesRegex(KisApiException, "READ_ONLY"):
            client.post("/uapi/domestic-stock/v1/trading/order-cash")

        self.assertEqual(1, client.order_request_count)

    def test_retries_server_errors_before_returning_success(self) -> None:
        client = object.__new__(KisClient)
        client.client = _HttpClient([
            _Response(500, {"msg_cd": "TEMP", "msg1": "temporary"}),
            _Response(200, {}),
        ])

        with patch("broker.kis.client.sleep") as pause:
            response = client.get("/test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.client.calls, 2)
        pause.assert_called_once_with(0.5)
        self.assertEqual(client.retry_count, 1)
        self.assertEqual(client.success_count, 1)

    def test_retries_transport_error(self) -> None:
        client = object.__new__(KisClient)
        client.client = _TransportThenSuccessClient()

        with patch("broker.kis.client.sleep") as pause:
            response = client.get("/test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.retry_count, 1)
        self.assertEqual(client.failure_count, 0)
        pause.assert_called_once_with(0.5)


class _HttpClient:
    def __init__(self, responses) -> None:
        self.responses = responses
        self.calls = 0

    def get(self, url, headers=None, params=None):
        response = self.responses[self.calls]
        self.calls += 1
        return response


class _Response:
    def __init__(self, status_code, payload) -> None:
        self.status_code = status_code
        self.payload = payload
        self.reason_phrase = "server error" if status_code >= 500 else "ok"
        self.is_server_error = status_code >= 500
        self.is_error = status_code >= 400

    def json(self):
        return self.payload


class _TransportThenSuccessClient:
    def __init__(self):
        self.calls = 0

    def get(self, url, headers=None, params=None):
        self.calls += 1
        if self.calls == 1:
            raise httpx.ConnectTimeout("fixture timeout")
        return _Response(200, {})


if __name__ == "__main__":
    unittest.main()

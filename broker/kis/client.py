"""
KIS HTTP Client
"""


from typing import Any
from time import perf_counter, sleep

import httpx

from broker.kis.exception import KisApiException
from broker.kis.constants import TOKEN_URL
from config.settings import settings



class KisClient:

    MAX_ATTEMPTS = 3


    def __init__(self):
        self.minimum_interval_seconds = 0.0
        self._last_request_at = 0.0

        self.client = httpx.Client(

            base_url=settings.kis_base_url,

            timeout=10.0

        )



    def get(

        self,

        url: str,

        headers: dict | None = None,

        params: dict | None = None

    ) -> httpx.Response:


        return self._request_with_retry(
            lambda: self.client.get(url, headers=headers, params=params)
        )
        self.request_count = 0
        self.success_count = 0
        self.retry_count = 0
        self.failure_count = 0
        self.server_error_count = 0
        self.transport_error_count = 0



    def post(

        self,

        url: str,

        headers: dict | None = None,

        json: dict[str, Any] | None = None

    ) -> httpx.Response:


        return self._request_with_retry(
            lambda: self.client.post(url, headers=headers, json=json)
        )

    def _request_with_retry(self, request):
        for attribute in (
            "request_count",
            "success_count",
            "retry_count",
            "failure_count",
            "server_error_count",
            "transport_error_count",
        ):
            if not hasattr(self, attribute):
                setattr(self, attribute, 0)
        response = None
        for attempt in range(self.MAX_ATTEMPTS):
            minimum_interval = getattr(
                self, "minimum_interval_seconds", 0.0
            )
            elapsed = perf_counter() - getattr(
                self, "_last_request_at", 0.0
            )
            if elapsed < minimum_interval:
                sleep(minimum_interval - elapsed)
            self.request_count += 1
            try:
                response = request()
                self._last_request_at = perf_counter()
            except httpx.TransportError:
                self._last_request_at = perf_counter()
                self.transport_error_count += 1
                if attempt == self.MAX_ATTEMPTS - 1:
                    self.failure_count += 1
                    raise
                self.retry_count += 1
                sleep(0.5 * (attempt + 1))
                continue
            if not response.is_server_error or attempt == self.MAX_ATTEMPTS - 1:
                break
            self.server_error_count += 1
            self.retry_count += 1
            sleep(0.5 * (attempt + 1))

        if response is None:
            self.failure_count += 1
            raise KisApiException("HTTP_ERROR", "KIS request was not created")
        if response.is_error:
            self.failure_count += 1
            raise self._to_api_exception(response)
        self.success_count += 1
        return response

    @staticmethod
    def _to_api_exception(response) -> KisApiException:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return KisApiException(
            payload.get("msg_cd", f"HTTP_{response.status_code}"),
            payload.get("msg1", response.reason_phrase),
        )



    def close(self):

        self.client.close()


class KisReadOnlyClient(KisClient):
    """KIS client that permits authentication and quotation reads only."""

    def __init__(self):
        super().__init__()
        self.order_request_count = 0

    def post(
        self,
        url: str,
        headers: dict | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if url != TOKEN_URL:
            self.order_request_count += 1
            raise KisApiException(
                "READ_ONLY_VIOLATION",
                f"POST is blocked in KIS read-only pilot: {url}",
            )
        return super().post(url, headers=headers, json=json)

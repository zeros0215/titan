"""Mock-domain-only Kiwoom authentication and account reads."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from threading import Lock
from time import monotonic, sleep
from typing import Callable

import httpx


MOCK_BASE_URL = "https://mockapi.kiwoom.com"
TOKEN_PATH = "/oauth2/token"
ACCOUNT_PATH = "/api/dostk/acnt"
READ_ONLY_API_IDS = frozenset({"kt00001", "kt00018"})


class KiwoomPaperError(RuntimeError):
    """Sanitized Kiwoom paper API failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class KiwoomPaperCredentials:
    app_key: str
    app_secret: str

    @classmethod
    def from_environment(cls) -> "KiwoomPaperCredentials":
        credentials = cls(
            os.getenv("KIWOOM_PAPER_APP_KEY", "").strip(),
            os.getenv("KIWOOM_PAPER_APP_SECRET", "").strip(),
        )
        if not credentials.app_key or not credentials.app_secret:
            raise KiwoomPaperError(
                "PAPER_CREDENTIALS_MISSING",
                "KIWOOM_PAPER_APP_KEY and KIWOOM_PAPER_APP_SECRET are required",
            )
        return credentials


@dataclass(frozen=True, slots=True)
class KiwoomPaperPosition:
    code: str
    name: str
    quantity: int
    sellable_quantity: int
    entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    return_rate: Decimal


@dataclass(frozen=True, slots=True)
class KiwoomPaperAccountSnapshot:
    cash: Decimal
    buying_power: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    positions: tuple[KiwoomPaperPosition, ...]
    synchronized_at: datetime


class KiwoomPaperClient:
    """Kiwoom client permanently restricted to mock authentication/account reads."""

    def __init__(
        self,
        credentials: KiwoomPaperCredentials,
        *,
        base_url: str = MOCK_BASE_URL,
        http_client: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
        wait: Callable[[float], None] = sleep,
    ) -> None:
        if base_url.rstrip("/") != MOCK_BASE_URL:
            raise ValueError("Kiwoom paper client only permits the official mock domain")
        if not credentials.app_key or not credentials.app_secret:
            raise ValueError("non-empty paper credentials are required")
        self._credentials = credentials
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._wait = wait
        self._client = http_client or httpx.Client(
            base_url=MOCK_BASE_URL,
            timeout=httpx.Timeout(10.0),
            headers={"Content-Type": "application/json;charset=UTF-8"},
        )
        self._owns_client = http_client is None
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._token_lock = Lock()
        self._last_tr_request: dict[str, float] = {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def account_snapshot(self) -> KiwoomPaperAccountSnapshot:
        deposit = self._read_all("kt00001", {"qry_tp": "3"})
        balance = self._read_all(
            "kt00018", {"qry_tp": "1", "dmst_stex_tp": "KRX"}
        )
        positions = tuple(
            _position(row)
            for row in balance.get("acnt_evlt_remn_indv_tot", [])
            if isinstance(row, dict) and _integer(row.get("rmnd_qty")) > 0
        )
        return KiwoomPaperAccountSnapshot(
            cash=_decimal(deposit.get("entr")),
            buying_power=_decimal(deposit.get("ord_alow_amt")),
            market_value=_decimal(balance.get("tot_evlt_amt")),
            unrealized_pnl=_signed_decimal(balance.get("tot_evlt_pl")),
            positions=positions,
            synchronized_at=self._clock(),
        )

    def _access_token(self) -> str:
        if self._token_is_valid():
            return self._token or ""
        with self._token_lock:
            if self._token_is_valid():
                return self._token or ""
            try:
                response = self._client.post(
                    TOKEN_PATH,
                    json={
                        "grant_type": "client_credentials",
                        "appkey": self._credentials.app_key,
                        "secretkey": self._credentials.app_secret,
                    },
                )
            except httpx.HTTPError as error:
                raise KiwoomPaperError(
                    "PAPER_AUTH_TRANSPORT_ERROR", type(error).__name__
                ) from error
            payload = _response_payload(response)
            token = str(payload.get("token") or "").strip()
            if response.is_error or not token:
                raise _api_error(response, payload, "PAPER_AUTH_FAILED")
            self._token = token
            self._token_expires_at = _parse_expiry(
                payload.get("expires_dt"), self._clock()
            )
            return token

    def _token_is_valid(self) -> bool:
        return bool(
            self._token
            and self._token_expires_at
            and self._clock() + timedelta(minutes=1) < self._token_expires_at
        )

    def _read_all(self, api_id: str, body: dict[str, str]) -> dict:
        if api_id not in READ_ONLY_API_IDS:
            raise KiwoomPaperError(
                "READ_ONLY_VIOLATION", f"API ID is not allowed: {api_id}"
            )
        combined: dict = {}
        continuation = None
        next_key = None
        for _ in range(10):
            self._throttle(api_id)
            headers = {
                "authorization": f"Bearer {self._access_token()}",
                "api-id": api_id,
            }
            if continuation == "Y" and next_key:
                headers.update({"cont-yn": "Y", "next-key": next_key})
            try:
                response = self._client.post(
                    ACCOUNT_PATH, headers=headers, json=body
                )
            except httpx.HTTPError as error:
                raise KiwoomPaperError(
                    "PAPER_ACCOUNT_TRANSPORT_ERROR", type(error).__name__
                ) from error
            payload = _response_payload(response)
            if response.is_error or payload.get("return_code") not in (None, 0, "0"):
                raise _api_error(response, payload, "PAPER_ACCOUNT_READ_FAILED")
            _merge_page(combined, payload)
            continuation = response.headers.get("cont-yn")
            next_key = response.headers.get("next-key")
            if continuation != "Y":
                return combined
        raise KiwoomPaperError(
            "PAPER_PAGINATION_LIMIT", f"too many pages for {api_id}"
        )

    def _throttle(self, api_id: str) -> None:
        now = monotonic()
        elapsed = now - self._last_tr_request.get(api_id, 0.0)
        if elapsed < 1.0:
            self._wait(1.0 - elapsed)
        self._last_tr_request[api_id] = monotonic()


def _response_payload(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as error:
        raise KiwoomPaperError(
            "PAPER_INVALID_RESPONSE", f"HTTP {response.status_code} returned non-JSON"
        ) from error
    if not isinstance(payload, dict):
        raise KiwoomPaperError("PAPER_INVALID_RESPONSE", "JSON body is not an object")
    return payload


def _api_error(
    response: httpx.Response, payload: dict, fallback: str
) -> KiwoomPaperError:
    code = str(payload.get("return_code") or f"HTTP_{response.status_code}" or fallback)
    message = str(payload.get("return_msg") or fallback)
    return KiwoomPaperError(code, message[:300])


def _parse_expiry(value: object, now: datetime) -> datetime:
    text = str(value or "").strip()
    for parser in (
        datetime.fromisoformat,
        lambda item: datetime.strptime(item, "%Y%m%d%H%M%S"),
    ):
        try:
            parsed = parser(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=now.tzinfo or timezone.utc)
            return parsed
        except ValueError:
            continue
    return now + timedelta(hours=23)


def _merge_page(target: dict, page: dict) -> None:
    for key, value in page.items():
        if key in {"return_code", "return_msg"}:
            continue
        if isinstance(value, list):
            target.setdefault(key, []).extend(value)
        elif key not in target or target[key] in (None, ""):
            target[key] = value


def _decimal(value: object) -> Decimal:
    text = str(value or "0").strip().replace(",", "")
    try:
        return abs(Decimal(text))
    except InvalidOperation as error:
        raise KiwoomPaperError(
            "PAPER_INVALID_NUMBER", "account response contains an invalid number"
        ) from error


def _signed_decimal(value: object) -> Decimal:
    text = str(value or "0").strip().replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as error:
        raise KiwoomPaperError(
            "PAPER_INVALID_NUMBER", "account response contains an invalid number"
        ) from error


def _integer(value: object) -> int:
    return int(_decimal(value))


def _position(row: dict) -> KiwoomPaperPosition:
    raw_code = str(row.get("stk_cd") or "").strip()
    code = raw_code[1:] if raw_code.startswith("A") else raw_code
    return KiwoomPaperPosition(
        code=code.zfill(6),
        name=str(row.get("stk_nm") or "").strip(),
        quantity=_integer(row.get("rmnd_qty")),
        sellable_quantity=_integer(row.get("trde_able_qty")),
        entry_price=_decimal(row.get("pur_pric")),
        current_price=_decimal(row.get("cur_prc")),
        market_value=_decimal(row.get("evlt_amt")),
        unrealized_pnl=_signed_decimal(row.get("evltv_prft")),
        return_rate=_signed_decimal(row.get("prft_rt")) / Decimal("100"),
    )

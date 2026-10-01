"""Official mock WebSocket market-session observation for Kiwoom paper orders."""
from __future__ import annotations
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from pathlib import Path
import websocket
from broker.kiwoom.paper import KiwoomPaperClient, KiwoomPaperCredentials, KiwoomPaperError

WS_URL = "wss://mockapi.kiwoom.com:10000/api/dostk/websocket"

@dataclass(frozen=True, slots=True)
class KiwoomMarketSession:
    status_code: str
    regular_session_open: bool
    observed_at: datetime

class KiwoomPaperMarketSessionClient:
    def __init__(self, credentials: KiwoomPaperCredentials, *, socket_factory: Callable = websocket.create_connection, clock: Callable[[], datetime] | None = None):
        self.credentials = credentials
        self.socket_factory = socket_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def current_session(self, timeout: float = 15.0, *, access_token: str | None = None) -> KiwoomMarketSession:
        token = access_token
        if token is None:
            auth = KiwoomPaperClient(self.credentials, clock=self.clock)
            try:
                token = auth.access_token()
            finally:
                auth.close()
        ws = self.socket_factory(WS_URL, timeout=timeout)
        try:
            ws.send(json.dumps({"trnm": "LOGIN", "token": token}))
            login = self._receive(ws, timeout)
            if str(login.get("trnm", "")).upper() != "LOGIN" or login.get("return_code") not in (None, 0, "0"):
                raise KiwoomPaperError("PAPER_MARKET_LOGIN_FAILED", str(login.get("return_msg") or "login rejected"))
            ws.send(json.dumps({"trnm":"REG","grp_no":"1","refresh":"1","data":[{"item":["005930"],"type":["0B"]}]}))
            for _ in range(20):
                message = self._receive(ws, timeout)
                for event in message.get("data", []) if isinstance(message, dict) else []:
                    session = _market_session_event({"data": [event]}, clock=self.clock)
                    if session is not None:
                        return session
            raise KiwoomPaperError("PAPER_MARKET_STATUS_UNAVAILABLE", "0B trade was not received")
        finally:
            ws.close()

    @staticmethod
    def _receive(ws, timeout: float) -> dict:
        while True:
            raw = ws.recv()
            if raw in ("", b""):
                continue
            if isinstance(raw, str) and raw.strip().upper() == "PING":
                ws.send("PING")
                continue
            try:
                value = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError as error:
                raise KiwoomPaperError(
                    "PAPER_MARKET_INVALID", "invalid WebSocket JSON payload"
                ) from error
            if isinstance(value, dict) and str(value.get("trnm", "")).upper() == "PING":
                ws.send(json.dumps(value)); continue
            if not isinstance(value, dict):
                raise KiwoomPaperError("PAPER_MARKET_INVALID", "invalid WebSocket payload")
            return value


class KiwoomPaperMarketSessionMonitor:
    """Reconnect forever and persist only sanitized market-session state."""

    def __init__(self, credentials: KiwoomPaperCredentials, state_path: Path, *, clock: Callable[[], datetime] | None = None, socket_factory: Callable = websocket.create_connection):
        self.credentials = credentials
        self.state_path = state_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.socket_factory = socket_factory
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._run_connection()
            except Exception as error:
                safe_error = str(getattr(error, "code", type(error).__name__))
                self._write_state("DISCONNECTED", None, False, safe_error)
            self.stop_event.wait(5)

    def stop(self) -> None:
        self.stop_event.set()

    def _run_connection(self) -> None:
        auth = KiwoomPaperClient(self.credentials, clock=self.clock)
        try:
            token = auth.access_token()
        finally:
            auth.close()
        ws = self.socket_factory(WS_URL, timeout=30)
        try:
            ws.send(json.dumps({"trnm": "LOGIN", "token": token}))
            login = KiwoomPaperMarketSessionClient._receive(ws, 30)
            if login.get("return_code") not in (None, 0, "0"):
                raise KiwoomPaperError("PAPER_MARKET_LOGIN_FAILED", "mock WebSocket login rejected")
            ws.send(json.dumps({"trnm":"REG","grp_no":"1","refresh":"1","data":[{"item":["005930"],"type":["0B"]}]}))
            self._write_state("CONNECTED", None, False, "AWAITING_0B_TRADE")
            while not self.stop_event.is_set():
                try:
                    message = KiwoomPaperMarketSessionClient._receive(ws, 30)
                except websocket.WebSocketTimeoutException:
                    continue
                event = _market_session_event(message)
                if event is not None:
                    self._write_state("CONNECTED", event.status_code, event.regular_session_open, None, observed_at=event.observed_at)
        finally:
            ws.close()

    def _write_state(self, connection: str, status_code: str | None, regular_open: bool, error: str | None, *, observed_at: datetime | None = None) -> None:
        payload = {"connection": connection, "status_code": status_code, "regular_session_open": regular_open, "observed_at": observed_at.isoformat() if observed_at else None, "updated_at": self.clock().isoformat(), "error": error}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)


def _market_session_event(message: dict, *, clock: Callable[[], datetime] | None = None) -> KiwoomMarketSession | None:
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    for event in message.get("data", []) if isinstance(message, dict) else []:
        event_type = str(event.get("type"))
        values = event.get("values") or {}
        if event_type == "0s":
            code = str(values.get("215") or "").strip()
            if code:
                return KiwoomMarketSession(code, code == "3", now)
        if event_type == "0B":
            trade_time = str(values.get("20") or "").strip()
            price = str(values.get("10") or "").lstrip("+-").strip()
            volume = str(values.get("15") or "").lstrip("+-").strip()
            if len(trade_time) == 6 and trade_time.isdigit() and price.isdigit() and volume.isdigit() and int(price) > 0 and int(volume) > 0:
                return KiwoomMarketSession("TRADE_0B", True, now)
    return None


def load_market_session_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value.get("regular_session_open"), bool):
            raise ValueError
        return value
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"connection":"DISCONNECTED","status_code":None,"regular_session_open":False,"observed_at":None,"updated_at":None,"error":"MARKET_SESSION_UNAVAILABLE"}

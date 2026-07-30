import json
from datetime import date, datetime
from pathlib import Path

from broker.kis.constants import HOLIDAY_URL, TR_HOLIDAY
from config.constants import CACHE_DIR


class HolidayCache:
    """Persistent KRX session cache keyed by calendar date."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CACHE_DIR / "krx_sessions.json"

    def load(self) -> dict[date, bool]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return {
                datetime.strptime(key, "%Y-%m-%d").date(): bool(value)
                for key, value in payload.get("sessions", {}).items()
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def save(self, sessions: dict[date, bool]) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now().isoformat(),
            "sessions": {
                key.isoformat(): value
                for key, value in sorted(sessions.items())
            },
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.path


class KisHolidayProvider:
    """Loads domestic market open/closed flags from the KIS holiday API."""

    def __init__(self, session) -> None:
        self.session = session

    def get_sessions(self, start: date, end: date) -> dict[date, bool]:
        if end < start:
            raise ValueError("end must be on or after start")
        response = self.session.get(
            HOLIDAY_URL,
            TR_HOLIDAY,
            params={
                "BASS_DT": start.strftime("%Y%m%d"),
                "CTX_AREA_NK": "",
                "CTX_AREA_FK": "",
            },
        )
        payload = response.json()
        if str(payload.get("rt_cd", "0")) != "0":
            raise ValueError(
                f"KIS holiday API failed: {payload.get('msg_cd', 'UNKNOWN')} "
                f"{payload.get('msg1', '')}".strip()
            )
        rows = payload.get("output", [])
        if not isinstance(rows, list):
            raise ValueError("KIS holiday API output must be a list")
        sessions: dict[date, bool] = {}
        for row in rows:
            raw_date = row.get("bass_dt")
            if not raw_date:
                continue
            day = datetime.strptime(str(raw_date), "%Y%m%d").date()
            if start <= day <= end:
                open_flag = row.get("opnd_yn", row.get("bzdy_yn", "N"))
                sessions[day] = str(open_flag).upper() == "Y"
        return sessions

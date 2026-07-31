"""Read-only KIS historical intraday price access."""

from __future__ import annotations

from datetime import date

from broker.kis.constants import (
    TIME_DAILY_CHART_PRICE_URL,
    TR_TIME_DAILY_CHART_PRICE,
)
from broker.kis.header import HeaderBuilder
from broker.kis.session import KisSession


class KisIntradayProvider:
    def __init__(self, session: KisSession | None = None):
        self.session = session or KisSession()

    def get_minutes(
        self,
        code: str,
        trading_date: date,
        end_time: str = "100000",
    ) -> list[dict]:
        if len(code) != 6 or not code.isdigit():
            raise ValueError("code must be a six-digit stock code")
        if len(end_time) != 6 or not end_time.isdigit():
            raise ValueError("end_time must use HHMMSS")
        token = self.session.auth.get_token()
        response = self.session.client.get(
            TIME_DAILY_CHART_PRICE_URL,
            headers=HeaderBuilder.authorization(
                token, TR_TIME_DAILY_CHART_PRICE
            ),
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_HOUR_1": end_time,
                "FID_INPUT_DATE_1": trading_date.strftime("%Y%m%d"),
                "FID_PW_DATA_INCU_YN": "N",
                "FID_FAKE_TICK_INCU_YN": "",
            },
        )
        payload = response.json()
        if payload.get("rt_cd") not in (None, "0"):
            raise ValueError(
                f"KIS intraday request failed: "
                f"{payload.get('msg_cd')} {payload.get('msg1')}"
            )
        result = []
        expected_date = trading_date.strftime("%Y%m%d")
        for raw in payload.get("output2") or []:
            value_date = raw.get("stck_bsop_date", expected_date)
            value_time = raw.get("stck_cntg_hour", "")
            if value_date != expected_date or len(value_time) != 6:
                continue
            result.append({
                "date": value_date,
                "time": value_time,
                "open": _number(raw, "stck_oprc"),
                "high": _number(raw, "stck_hgpr"),
                "low": _number(raw, "stck_lwpr"),
                "close": _number(raw, "stck_prpr"),
                "volume": _number(raw, "cntg_vol"),
                "trading_value": _optional_number(
                    raw, "acml_tr_pbmn", "acml_tr_pbm"
                ),
            })
        return sorted(result, key=lambda row: row["time"])


def _number(row: dict, key: str) -> float:
    value = row.get(key)
    if value in (None, ""):
        raise ValueError(f"KIS intraday response is missing {key}")
    return float(value)


def _optional_number(row: dict, *keys: str) -> float | None:
    for key in keys:
        if row.get(key) not in (None, ""):
            return float(row[key])
    return None

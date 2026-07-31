"""Read-only KIS current-price quotations."""

from __future__ import annotations

from datetime import datetime

from broker.kis.client import KisReadOnlyClient
from broker.kis.constants import CURRENT_PRICE_URL, TR_CURRENT_PRICE
from broker.kis.session import KisSession
from config.settings import settings


class KisCurrentPriceProvider:
    def __init__(self, session: KisSession | None = None) -> None:
        self.session = session or KisSession(client=KisReadOnlyClient())
        self.session.client.minimum_interval_seconds = (
            1.0 if settings.kis_mode.upper() == "VIRTUAL" else 0.06
        )

    def get_prices(self, codes: list[str]) -> dict[str, dict]:
        prices = {}
        for code in dict.fromkeys(codes):
            if len(code) != 6 or not code.isdigit():
                raise ValueError(f"잘못된 종목코드입니다: {code}")
            response = self.session.get(
                CURRENT_PRICE_URL,
                TR_CURRENT_PRICE,
                {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": code,
                },
            )
            payload = response.json()
            if payload.get("rt_cd") not in (None, "0"):
                raise ValueError(
                    f"KIS 현재가 조회 실패({code}): "
                    f"{payload.get('msg_cd')} {payload.get('msg1')}"
                )
            output = payload.get("output") or {}
            price = _number(output, "stck_prpr")
            change_rate = _optional_number(output, "prdy_ctrt")
            volume = _optional_number(output, "acml_vol")
            trading_value = _optional_number(output, "acml_tr_pbmn")
            prices[code] = {
                "close": price,
                "change_rate": (
                    change_rate / 100 if change_rate is not None else None
                ),
                "open": _optional_number(output, "stck_oprc"),
                "high": _optional_number(output, "stck_hgpr"),
                "low": _optional_number(output, "stck_lwpr"),
                "volume": volume,
                "trading_value": trading_value,
                "vwap": (
                    trading_value / volume
                    if volume not in (None, 0)
                    and trading_value is not None
                    else None
                ),
                "date": output.get("stck_bsop_date") or datetime.now().date().isoformat(),
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "source": "KIS_REALTIME",
            }
        return prices

    def close(self) -> None:
        self.session.close()


def _number(row: dict, key: str) -> float:
    value = row.get(key)
    if value in (None, ""):
        raise ValueError(f"KIS 현재가 응답에 {key}가 없습니다.")
    return float(value)


def _optional_number(row: dict, key: str) -> float | None:
    value = row.get(key)
    return None if value in (None, "") else float(value)

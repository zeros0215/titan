from datetime import datetime

from benchmark.provider import BenchmarkProvider
from broker.kis.constants import (
    DAILY_INDEX_CHART_PRICE_URL,
    TR_DAILY_INDEX_CHART_PRICE,
)
from broker.kis.header import HeaderBuilder
from broker.kis.session import KisSession
from domain.enums import MarketType


class KisBenchmarkProvider(BenchmarkProvider):
    """KOSPI/KOSDAQ period returns from the official KIS index chart API."""

    INDEX_CODES = {
        MarketType.KOSPI: "0001",
        MarketType.KOSDAQ: "1001",
    }

    def __init__(self, session: KisSession | None = None) -> None:
        self.session = session or KisSession()

    def get_returns(
        self,
        markets: set[MarketType],
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, float]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        return {
            market.value: self._get_return(market, start_date, end_date)
            for market in markets
        }

    def _get_return(
        self,
        market: MarketType,
        start_date: datetime,
        end_date: datetime,
    ) -> float:
        token = self.session.auth.get_token()
        response = self.session.client.get(
            DAILY_INDEX_CHART_PRICE_URL,
            headers=HeaderBuilder.authorization(
                token,
                TR_DAILY_INDEX_CHART_PRICE,
            ),
            params={
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": self.INDEX_CODES[market],
                "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
            },
        )
        payload = response.json()
        if payload.get("rt_cd") not in (None, "0"):
            raise ValueError(
                f"KIS benchmark request failed: {payload.get('msg1', 'unknown error')}"
            )
        points = sorted(
            (
                datetime.strptime(item["stck_bsop_date"], "%Y%m%d"),
                float(item["bstp_nmix_prpr"]),
            )
            for item in payload.get("output2", [])
            if item.get("stck_bsop_date") and item.get("bstp_nmix_prpr")
        )
        if len(points) < 2:
            raise ValueError(
                f"insufficient benchmark data for {market.value}"
            )
        first_price = points[0][1]
        last_price = points[-1][1]
        if first_price <= 0:
            raise ValueError("benchmark start price must be greater than zero")
        return (last_price - first_price) / first_price

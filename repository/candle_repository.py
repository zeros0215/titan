import json
from datetime import datetime
from pathlib import Path

from config.constants import OUTPUT_DIR
from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.enums import MarketType
from domain.stock import Stock


class CandleRepository:
    """Persists daily OHLCV and merges newly fetched candles by timestamp."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or OUTPUT_DIR / "market_data"

    def save(self, series: CandleSeries) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{series.stock.code}.json"
        payload = {
            "code": series.stock.code,
            "name": series.stock.name,
            "market": series.stock.market.value,
            "candles": [
                {
                    "date": candle.date.isoformat(),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
                for candle in series.candles
            ],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def save_many(self, series_by_code: dict[str, CandleSeries]) -> None:
        for series in series_by_code.values():
            self.save(series)

    def load(self, code: str) -> CandleSeries | None:
        path = self.directory / f"{code}.json"
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        stock = Stock(
            code=payload["code"],
            name=payload["name"],
            market=MarketType(payload["market"]),
        )
        return CandleSeries(
            stock=stock,
            candles=[
                Candle(
                    date=datetime.fromisoformat(item["date"]),
                    open=item["open"],
                    high=item["high"],
                    low=item["low"],
                    close=item["close"],
                    volume=item["volume"],
                )
                for item in payload["candles"]
            ],
        )

    @staticmethod
    def merge(
        cached: CandleSeries | None,
        fetched: CandleSeries,
    ) -> CandleSeries:
        candles = {
            candle.date: candle
            for candle in (cached.candles if cached is not None else [])
        }
        candles.update({candle.date: candle for candle in fetched.candles})
        return CandleSeries(
            stock=fetched.stock,
            candles=sorted(candles.values(), key=lambda candle: candle.date),
        )

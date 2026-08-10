"""Point-in-time top-cohort equal-weight benchmark for offline research."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from benchmark.provider import BenchmarkProvider
from domain.enums import MarketType


class HistoricalEqualWeightBenchmarkProvider(BenchmarkProvider):
    def __init__(self, price_dir: Path, limit: int = 100) -> None:
        self.price_dir = price_dir
        self.limit = limit
        ranking = json.loads(
            (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
        )
        self.sessions = ranking["sessions"]
        self.keys = sorted(self.sessions)
        self.cache: dict[tuple[str, str], float] = {}

    def get_returns(
        self, markets: set[MarketType], start_date: datetime, end_date: datetime,
    ) -> dict[str, float]:
        key = (start_date.date().isoformat(), end_date.date().isoformat())
        if key not in self.cache:
            self.cache[key] = self._return(*key)
        return {market.value: self.cache[key] for market in markets}

    def _return(self, start: str, end: str) -> float:
        eligible = [key for key in self.keys if key[:10] <= start]
        if not eligible:
            raise ValueError(f"no benchmark cohort on or before {start}")
        codes = self.sessions[eligible[-1]][:self.limit]
        values = []
        for raw_code in codes:
            try:
                candles = json.loads(
                    (self.price_dir / f"{str(raw_code).zfill(6)}.json").read_text(
                        encoding="utf-8"
                    )
                )["candles"]
                start_points = [row for row in candles if str(row["date"])[:10] >= start]
                end_points = [row for row in candles if str(row["date"])[:10] <= end]
                if not start_points or not end_points:
                    continue
                first, last = float(start_points[0]["close"]), float(end_points[-1]["close"])
                if first > 0 and str(end_points[-1]["date"])[:10] >= str(start_points[0]["date"])[:10]:
                    values.append(last / first - 1)
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        if not values:
            raise ValueError(f"no benchmark prices for {start}..{end}")
        return sum(values) / len(values)

"""Point-in-time stock repository limited by historical market capitalization."""

import bisect
import json
from datetime import datetime
from pathlib import Path

from repository.universe_snapshot import UniverseSnapshot


class MarketCapStockRepository:
    def __init__(self, base_repository, ranking_path: Path) -> None:
        self.base_repository = base_repository
        payload = json.loads(ranking_path.read_text(encoding="utf-8"))
        self.limit = int(payload["limit"])
        self.sessions = payload["sessions"]
        self.session_dates = sorted(self.sessions)
        if not self.session_dates:
            raise ValueError("market-cap ranking contains no sessions")

    def get_all(self):
        return self.base_repository.get_all()

    def get_as_of(self, as_of: datetime) -> UniverseSnapshot:
        snapshot = self.base_repository.get_as_of(as_of)
        key = as_of.strftime("%Y-%m-%dT%H:%M:%S")
        index = bisect.bisect_right(self.session_dates, key) - 1
        if index < 0:
            raise ValueError(
                f"no market-cap ranking on or before {as_of.date()}"
            )
        codes = set(self.sessions[self.session_dates[index]][: self.limit])
        stocks = [stock for stock in snapshot.stocks if stock.code in codes]
        return UniverseSnapshot(
            as_of=snapshot.as_of,
            stocks=stocks,
            source_count=snapshot.source_count,
            dated_count=snapshot.dated_count,
            excluded_before_listing=snapshot.excluded_before_listing,
            excluded_after_delisting=snapshot.excluded_after_delisting,
            coverage=snapshot.coverage,
            point_in_time_complete=snapshot.point_in_time_complete,
        )

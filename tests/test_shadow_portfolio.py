from types import SimpleNamespace
import unittest
from datetime import datetime

from domain.enums import MarketType
from pathlib import Path
from research.shadow_portfolio import (
    _allocate, _summary, replay_shadow_month, replay_weekday_sensitivity,
    save_weekly_snapshot,
)
from tempfile import TemporaryDirectory


class ShadowPortfolioTest(unittest.TestCase):
    def test_allocates_fixed_source_slots_and_records_skips(self) -> None:
        freeze = {"portfolio": {"slot_limits": {
            "challenger-a-breakout-h40": 1,
            "challenger-c-pullback-h40": 1,
        }}}
        a1 = self._selection("001", 1)
        a2 = self._selection("002", 2)
        c1 = self._selection("001", 1)
        positions = []

        _allocate(
            positions, {"A": [a1, a2], "C": [c1]}, freeze,
            datetime(2026, 8, 5),
        )

        self.assertEqual("PENDING_ENTRY", positions[0]["status"])
        self.assertEqual("SOURCE_CAPACITY", positions[1]["exclusion_reason"])
        self.assertEqual("DUPLICATE_CODE", positions[2]["exclusion_reason"])
        self.assertEqual(0, _summary(positions)["operational_orders"])

    def test_replay_rejects_invalid_month_before_reading_data(self) -> None:
        with self.assertRaisesRegex(ValueError, "YYYY-MM"):
            replay_shadow_month(
                "2026/01", "weekly", Path("active.json"),
                Path("freeze.json"), Path("state.json"),
            )

    def test_weekday_test_rejects_reversed_months(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be after"):
            replay_weekday_sensitivity(
                "2026-06", "2026-01", Path("active.json"),
                Path("freeze.json"), Path("output"),
            )

    def test_weekly_snapshot_is_no_order_and_tracks_milestones(self) -> None:
        state = {
            "updated_at": "2026-08-06T09:00:00", "run_dates": ["2026-08-05T00:00:00"],
            "positions": [], "summary": {"horizons": {}},
        }
        with TemporaryDirectory() as directory:
            result = save_weekly_snapshot(state, Path(directory))
            self.assertEqual("NOT_ELIGIBLE", result["promotion_status"])
            self.assertEqual(0, result["operational_orders"])
            self.assertTrue(Path(result["latest_path"]).exists())

    @staticmethod
    def _selection(code, rank):
        features = SimpleNamespace(enabled=lambda: [])
        analysis = SimpleNamespace(
            market=MarketType.KOSPI,
            score=SimpleNamespace(normalized_score=80),
            features=features,
            context=SimpleNamespace(market_strength=.7),
        )
        return SimpleNamespace(
            code=code, name=code, rank=rank, analysis=analysis,
        )


if __name__ == "__main__":
    unittest.main()

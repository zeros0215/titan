import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from analysis.event_candidates import (
    evaluate_event_quote,
    session_progress,
    snapshot_phase,
)


class EventCandidatesTest(unittest.TestCase):
    def test_qualifies_price_volume_and_vwap_confirmation(self) -> None:
        result = evaluate_event_quote(
            {
                "close": 102,
                "open": 100,
                "vwap": 101,
                "volume": 300,
                "change_rate": 0.02,
            },
            previous_volume=1000,
            progress=0.1,
        )

        self.assertTrue(result["qualified"])
        self.assertEqual(result["reason"], "EVENT_REVIEW")
        self.assertEqual(result["volume_speed"], 3)

    def test_rejects_already_surged_quote(self) -> None:
        result = evaluate_event_quote(
            {
                "close": 106,
                "open": 100,
                "vwap": 102,
                "volume": 300,
                "change_rate": 0.06,
            },
            previous_volume=1000,
            progress=0.1,
        )

        self.assertFalse(result["qualified"])
        self.assertEqual(result["reason"], "PRICE_OUT_OF_RANGE")

    def test_session_progress_uses_regular_market_minutes(self) -> None:
        now = datetime(2026, 7, 31, 9, 39, tzinfo=ZoneInfo("Asia/Seoul"))

        self.assertAlmostEqual(session_progress(now), 0.1)

    def test_only_near_ten_is_entry_snapshot(self) -> None:
        zone = ZoneInfo("Asia/Seoul")
        self.assertEqual(
            snapshot_phase(datetime(2026, 7, 31, 9, 30, tzinfo=zone)),
            "PREVIEW",
        )
        self.assertEqual(
            snapshot_phase(datetime(2026, 7, 31, 10, 0, tzinfo=zone)),
            "ENTRY",
        )
        self.assertEqual(
            snapshot_phase(datetime(2026, 7, 31, 10, 11, tzinfo=zone)),
            "LATE",
        )

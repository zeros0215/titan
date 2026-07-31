import json
import tempfile
import unittest
from pathlib import Path

from analysis.event_shadow import summarize_event_shadow


class EventShadowTest(unittest.TestCase):
    def test_uses_entry_snapshot_and_ignores_same_day_range(self) -> None:
        runs = [{
            "executed_at": "2026-07-30T10:00:00+09:00",
            "snapshot_phase": "ENTRY",
            "candidates": [{
                "code": "090430",
                "name": "아모레퍼시픽",
                "close": 100,
            }],
        }]
        with tempfile.TemporaryDirectory() as directory:
            price_dir = Path(directory)
            (price_dir / "090430.json").write_text(
                json.dumps({"candles": [
                    {
                        "date": "2026-07-30",
                        "high": 110,
                        "low": 80,
                        "close": 100,
                    },
                    {
                        "date": "2026-07-31",
                        "high": 106,
                        "low": 99,
                        "close": 105,
                    },
                ]}),
                encoding="utf-8",
            )
            result = summarize_event_shadow(runs, price_dir)

        self.assertEqual(result["entry_candidates"], 1)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["trades"][0]["exit_reason"], "TAKE_PROFIT")

    def test_preview_snapshot_is_not_counted_as_entry(self) -> None:
        result = summarize_event_shadow([{
            "executed_at": "2026-07-30T09:30:00+09:00",
            "snapshot_phase": "PREVIEW",
            "candidates": [{"code": "090430", "close": 100}],
        }], None)

        self.assertEqual(result["entry_candidates"], 0)

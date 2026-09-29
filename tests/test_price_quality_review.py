import csv
import json
import tempfile
import unittest
from pathlib import Path

from price_history.review import review_price_quality


class PriceQualityReviewTest(unittest.TestCase):
    def test_builds_pending_official_evidence_queue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "stock_count": 1,
                "adjustment_event_count": 1,
                "unresolved_large_jump_count": 1,
                "quality_quarantine_count": 1,
                "rejected_row_count": 0,
                "formal_backtest_ready": False,
                "formal_blocker": "official evidence required",
            }
            stock = {
                "code": "000001",
                "name": "Example",
                "official_adjusted_prices": False,
                "adjustment_events": [{
                    "date": "2024-01-02T00:00:00",
                    "share_ratio": 2.0,
                    "backward_price_factor": 0.5,
                    "continuity": 1.0,
                }],
                "unresolved_large_jumps": [{
                    "date": "2024-02-01T00:00:00",
                    "classification": "UNRESOLVED_CORPORATE_ACTION",
                    "share_ratio": 1.5,
                    "price_ratio": 0.5,
                    "continuity": 0.75,
                }],
            }
            quarantine = [{
                "code": "000001",
                "start": "2024-02-01T00:00:00",
                "end": "2024-04-30T00:00:00",
                "classification": "UNRESOLVED_CORPORATE_ACTION",
            }]
            for name, payload in (
                ("price_history_manifest.json", manifest),
                ("quality_quarantines.json", quarantine),
                ("rejected_price_rows.json", []),
                ("000001.json", stock),
            ):
                (root / name).write_text(
                    json.dumps(payload), encoding="utf-8"
                )

            result = review_price_quality(root, root / "review.md")
            with (root / "review_queue.csv").open(
                encoding="utf-8-sig", newline=""
            ) as stream:
                queue = list(csv.DictReader(stream))

        self.assertEqual("PASS", result["status"])
        self.assertEqual(1, result["inferred_adjustment_count"])
        self.assertEqual(2, result["official_evidence_pending_count"])
        self.assertEqual([], result["invalid_adjustments"])
        self.assertEqual(
            ["INFERRED_ADJUSTMENT", "UNRESOLVED_DISCONTINUITY"],
            [row["event_type"] for row in queue],
        )
        self.assertTrue(all(
            row["review_status"] == "PENDING_OFFICIAL_EVIDENCE"
            for row in queue
        ))


if __name__ == "__main__":
    unittest.main()

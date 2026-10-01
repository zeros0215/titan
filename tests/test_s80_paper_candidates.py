import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from broker.kiwoom import KiwoomPaperStockInfo
from trading.paper_dashboard import STRATEGY_VERSION
from trading.s80_paper_candidates import (
    build_s80_paper_candidates,
    load_latest_s80_selection,
)


def quote(code: str, *, opening: str = "102", current: str = "103"):
    return KiwoomPaperStockInfo(
        code, "테스트", Decimal(current), Decimal("100"), Decimal(opening),
        Decimal("70"), Decimal("130"), datetime.now(timezone.utc),
    )


class S80PaperCandidatesTest(unittest.TestCase):
    def test_loads_only_latest_prior_successful_s80_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for day, status in (("2026-09-28", "PASS"), ("2026-09-29", "PASS"), ("2026-09-30", "PASS")):
                (root / f"{day}.json").write_text(json.dumps({
                    "as_of": f"{day}T00:00:00",
                    "status": status,
                    "strategy_version": STRATEGY_VERSION,
                    "selected_candidates": [{"code": day[-2:], "total_score": 80}],
                }), encoding="utf-8")
            result = load_latest_s80_selection(root, date(2026, 9, 30))

        self.assertEqual("2026-09-29T00:00:00", result["as_of"])

    def test_official_coverage_date_allows_holiday_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {
                "as_of": "2026-09-25T00:00:00",
                "status": "PASS",
                "strategy_version": STRATEGY_VERSION,
                "selected_candidates": [],
            }
            (root / "run.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            result = load_latest_s80_selection(
                root, date(2026, 9, 29),
                expected_selection_date=date(2026, 9, 25),
            )
        self.assertEqual("2026-09-25T00:00:00", result["as_of"])

    def test_prior_weekday_pass_takes_priority_over_stale_coverage_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for day in ("2026-09-29", "2026-09-30"):
                (root / f"{day}.json").write_text(json.dumps({
                    "as_of": f"{day}T00:00:00",
                    "status": "PASS",
                    "strategy_version": STRATEGY_VERSION,
                    "selected_candidates": [{"code": "000001"}],
                }), encoding="utf-8")

            result = load_latest_s80_selection(
                root, date(2026, 10, 1),
                expected_selection_date=date(2026, 9, 29),
            )

        self.assertEqual("2026-09-30T00:00:00", result["as_of"])

    def test_applies_gap_holding_order_and_portfolio_gates(self):
        selection = {
            "as_of": "2026-09-29T00:00:00",
            "selected_candidates": [
                {"code": "000001", "total_score": 90},
                {"code": "000002", "total_score": 89},
                {"code": "000003", "total_score": 88},
                {"code": "000004", "total_score": 87},
            ],
        }
        quotes = {
            "000001": quote("000001"),
            "000002": quote("000002"),
            "000003": quote("000003", opening="104"),
            "000004": quote("000004"),
        }
        rows = build_s80_paper_candidates(
            selection, quotes,
            held_symbols={"000001"}, ordered_symbols={"000002"},
            maximum_positions=2,
        )

        self.assertEqual("이미 보유 중", rows[0]["reason"])
        self.assertEqual("오늘 주문 존재", rows[1]["reason"])
        self.assertEqual("시가 갭 ±3% 초과", rows[2]["reason"])
        self.assertTrue(rows[3]["eligible"])
        self.assertTrue(rows[3]["approval_enabled"])
        self.assertEqual("s80-2026-09-29-000004", rows[3]["intent_id"])
        self.assertAlmostEqual(.02, rows[3]["gap_rate"])

    def test_position_limit_is_fail_closed(self):
        selection = {
            "as_of": "2026-09-29T00:00:00",
            "selected_candidates": [{"code": "000001", "total_score": 90}],
        }
        rows = build_s80_paper_candidates(
            selection, {"000001": quote("000001")},
            held_symbols={f"{value:06d}" for value in range(10, 17)},
            ordered_symbols=set(),
        )
        self.assertFalse(rows[0]["eligible"])
        self.assertEqual("최대 7종목 보유 한도", rows[0]["reason"])

    def test_selected_candidates_have_priority_over_observation_candidates(self):
        selection = {
            "as_of": "2026-09-29T00:00:00",
            "selected_candidates": [{"code": "000001", "total_score": 85}],
            "observation_candidates": [
                {"code": "000002", "total_score": 79},
                {"code": "000003", "total_score": 78},
            ],
        }
        quotes = {code: quote(code) for code in ("000001", "000002", "000003")}
        rows = build_s80_paper_candidates(
            selection, quotes, held_symbols=set(), ordered_symbols=set(),
            maximum_positions=2,
        )
        self.assertEqual(["SELECTED", "OBSERVATION", "OBSERVATION"], [
            row["cohort"] for row in rows
        ])
        self.assertTrue(rows[0]["eligible"])
        self.assertTrue(rows[1]["eligible"])
        self.assertFalse(rows[2]["eligible"])
        self.assertEqual("최대 2종목 보유 한도", rows[2]["reason"])
        self.assertEqual(
            "V1.3-S80-OBSERVATION-PAPER", rows[1]["strategy_version"]
        )


if __name__ == "__main__":
    unittest.main()

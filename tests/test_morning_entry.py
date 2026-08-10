import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from analysis.morning_entry import (
    _bounded_daily_exit,
    _no_progress_daily_exit,
    audit_intraday_exit_coverage,
    build_collection_manifest,
    build_daily_collection_manifest,
    evaluate_morning_bars,
)


class MorningEntryTest(unittest.TestCase):
    def test_daily_manifest_uses_latest_prior_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / "runs"
            runs.mkdir()
            row = {
                "as_of": "2026-01-02T00:00:00",
                "strategy_version": "V1.3",
                "selected_candidates": [{"code": "005930", "name": "Samsung"}],
            }
            (runs / "run.json").write_text(
                json.dumps(row), encoding="utf-8"
            )
            result = build_daily_collection_manifest(
                runs, root / "manifest.json", "V1.3", datetime(2026, 1, 5).date()
            )
            self.assertEqual(1, result["target_count"])
            self.assertEqual("2026-01-05", result["targets"][0]["entry_date"])

    def test_builds_deduplicated_next_session_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / "runs"
            runs.mkdir()
            row = {
                "as_of": "2026-01-02T00:00:00",
                "strategy_version": "V1.3",
                "selected_candidates": [
                    {"code": "5930", "name": "삼성전자", "rank": 1,
                     "total_score": 81}
                ],
            }
            for name in ("a.json", "b.json"):
                (runs / name).write_text(
                    json.dumps(row, ensure_ascii=False), encoding="utf-8"
                )
            output = root / "manifest.json"
            result = build_collection_manifest(
                runs,
                [datetime(2026, 1, 2), datetime(2026, 1, 5)],
                output,
                "V1.3",
            )
            self.assertEqual(1, result["target_count"])
            self.assertEqual("2026-01-05", result["targets"][0]["entry_date"])
            self.assertEqual("005930", result["targets"][0]["code"])

    def test_qualifies_stable_morning(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bars.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "timestamp", "code", "open", "high", "low", "close",
                        "volume", "trading_value",
                    ],
                )
                writer.writeheader()
                start = datetime(2026, 1, 5, 9)
                for index in range(12):
                    low = 100 + index * 0.05
                    close = low + 0.20
                    writer.writerow({
                        "timestamp": (start + timedelta(minutes=5 * index)).isoformat(),
                        "code": "005930",
                        "open": 100,
                        "high": close + 0.1,
                        "low": low,
                        "close": close,
                        "volume": 100,
                        "trading_value": close * 100,
                    })
            result = evaluate_morning_bars(path, previous_close=100)
            self.assertTrue(result["qualified"])
            self.assertTrue(all(result["conditions"].values()))

    def test_rejects_falling_recent_lows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bars.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow([
                    "timestamp", "code", "open", "high", "low", "close",
                    "volume", "trading_value",
                ])
                start = datetime(2026, 1, 5, 9)
                for index in range(12):
                    low = 100 if index < 9 else 100 - index / 10
                    writer.writerow([
                        (start + timedelta(minutes=5 * index)).isoformat(),
                        "005930", 100, 101, low, 100, 100, 10000,
                    ])
            result = evaluate_morning_bars(path, previous_close=100)
            self.assertFalse(result["qualified"])
            self.assertFalse(result["conditions"]["recent_lows_stable"])

    def test_exit_coverage_rejects_morning_only_bars(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"targets": [{
                "selection_date": "2026-01-02", "entry_date": "2026-01-05",
                "code": "005930", "name": "Samsung",
            }]}), encoding="utf-8")
            bars_path = root / "bars" / "2026-01-05" / "005930.csv"
            bars_path.parent.mkdir(parents=True)
            with bars_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["timestamp", "code", "open", "high", "low", "close", "volume", "trading_value"])
                for index in range(12):
                    writer.writerow([
                        (datetime(2026, 1, 5, 9) + timedelta(minutes=5 * index)).isoformat(),
                        "005930", 100, 101, 99, 100, 100, 10000,
                    ])
            result = audit_intraday_exit_coverage(
                [manifest], root / "bars", root / "audit"
            )
            self.assertEqual("NOT_READY", result["status"])
            self.assertEqual(0, result["after_entry_count"])
            self.assertFalse(result["can_resolve_same_day_target_stop_order"])

    def test_exit_bounds_choose_opposite_sides_when_both_hit(self):
        from types import SimpleNamespace
        session = datetime(2026, 1, 5)
        candle = SimpleNamespace(
            date=session, open=100, high=106, low=89, close=100
        )
        candles = {session.date(): candle}
        pessimistic = _bounded_daily_exit(
            [session], 0, candles, 100, .05, .10, 1, 101, 99,
            "PESSIMISTIC",
        )
        optimistic = _bounded_daily_exit(
            [session], 0, candles, 100, .05, .10, 1, 101, 99,
            "OPTIMISTIC",
        )
        self.assertEqual("BOTH_STOP_FIRST", pessimistic["reason"])
        self.assertEqual("BOTH_TARGET_FIRST", optimistic["reason"])

    def test_no_progress_exit_closes_on_fifth_session(self):
        from types import SimpleNamespace
        sessions = [datetime(2026, 1, 5) + timedelta(days=index) for index in range(5)]
        candles = {
            session.date(): SimpleNamespace(
                date=session, open=100, high=101, low=98, close=99
            )
            for session in sessions
        }
        result = _no_progress_daily_exit(
            sessions, 0, candles, 100, .05, .10, 20, 101, 99,
            progress_rate=.02, checkpoint_sessions=5,
            count_uncertain_entry_progress=False,
        )
        self.assertEqual("NO_PROGRESS_EXIT", result["reason"])
        self.assertEqual(5, result["holding_sessions"])
        self.assertEqual(99, result["price"])

    def test_no_progress_exit_preserves_trade_after_two_percent_progress(self):
        from types import SimpleNamespace
        sessions = [datetime(2026, 1, 5) + timedelta(days=index) for index in range(6)]
        candles = {}
        for index, session in enumerate(sessions):
            candles[session.date()] = SimpleNamespace(
                date=session, open=100,
                high=103 if index == 1 else 101,
                low=98, close=99 if index == 4 else 100,
            )
        result = _no_progress_daily_exit(
            sessions, 0, candles, 100, .05, .10, 6, 101, 99,
            progress_rate=.02, checkpoint_sessions=5,
            count_uncertain_entry_progress=False,
        )
        self.assertEqual("MAX_HOLD", result["reason"])
        self.assertTrue(result["progress_hit"])


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from tools.kis_dashboard_server import _save_operational_entry_snapshot


class _History:
    def __init__(self, _path):
        pass

    def load_all(self):
        return [{
            "run_id": "run-1",
            "as_of": "2026-08-04T00:00:00",
            "status": "PASS",
            "strategy_version": "V1.3-S80-N7-TP5-SL10-CANDIDATE",
            "observation_candidates": [
                {"code": "000660", "name": "SK hynix", "total_score": 75},
            ],
            "selected_candidates": [
                {"code": "005930", "name": "삼성전자", "total_score": 82},
            ],
        }]


class OperationalEntrySnapshotTest(unittest.TestCase):
    def test_saves_selected_quote_during_entry_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch(
            "tools.kis_dashboard_server.ROOT", Path(temporary)
        ), patch(
            "tools.kis_dashboard_server.PilotHistoryRepository", _History
        ):
            result = _save_operational_entry_snapshot(
                {
                    "005930": {
                        "close": 103,
                        "change_rate": 0.03,
                        "time": "2026-08-05T10:00:05+09:00",
                    },
                    "000660": {"close": 110, "change_rate": 0.10},
                },
                datetime.fromisoformat("2026-08-05T10:00:05+09:00"),
            )

            self.assertEqual(2, result["candidate_count"])
            payload = json.loads(
                (Path(temporary) / result["path"]).read_text(encoding="utf-8")
            )
            selected = next(
                row for row in payload["candidates"] if row["code"] == "005930"
            )
            observed = next(
                row for row in payload["candidates"] if row["code"] == "000660"
            )
            self.assertTrue(selected["entry_allowed"])
            self.assertEqual("OBSERVATION", observed["cohort"])
            self.assertTrue(observed["hypothetical_entry"])
            self.assertFalse(observed["entry_allowed"])

    def test_does_not_save_outside_entry_window(self) -> None:
        result = _save_operational_entry_snapshot(
            {}, datetime.fromisoformat("2026-08-05T11:00:00+09:00")
        )
        self.assertIsNone(result)

    def test_uses_latest_observation_only_run(self) -> None:
        class ObservationOnlyHistory:
            def __init__(self, _path):
                pass

            def load_all(self):
                older = _History(None).load_all()[0]
                return [older, {
                    "run_id": "run-2",
                    "as_of": "2026-08-11T00:00:00",
                    "status": "PASS",
                    "strategy_version": "V1.3-S80-N7-TP5-SL10-CANDIDATE",
                    "selected_candidates": [],
                    "observation_candidates": [
                        {"code": "003690", "name": "코리안리", "total_score": 78},
                    ],
                }]

        with tempfile.TemporaryDirectory() as temporary, patch(
            "tools.kis_dashboard_server.ROOT", Path(temporary)
        ), patch(
            "tools.kis_dashboard_server.PilotHistoryRepository",
            ObservationOnlyHistory,
        ):
            result = _save_operational_entry_snapshot(
                {"003690": {"close": 14490, "change_rate": -0.015}},
                datetime.fromisoformat("2026-08-12T10:00:05+09:00"),
            )

            self.assertEqual(1, result["candidate_count"])
            payload = json.loads(
                (Path(temporary) / result["path"]).read_text(encoding="utf-8")
            )
            self.assertEqual("run-2", payload["source_run_id"])
            self.assertEqual("003690", payload["candidates"][0]["code"])
            self.assertEqual("OBSERVATION", payload["candidates"][0]["cohort"])


if __name__ == "__main__":
    unittest.main()

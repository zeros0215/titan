import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from operation.calendar import CachedMarketCalendar, WeekdayMarketCalendar
from operation.holiday import HolidayCache, KisHolidayProvider
from operation.model import RunStatus
from operation.runner import DailyOperationRunner
from repository.run_repository import RunRepository
from repository.selection_repository import SelectionRepository
from repository.validation_repository import ValidationRepository


class _SelectionResult:
    selections = [object(), object()]
    observations = [object()]


class _TitanRunner:
    def __init__(self):
        self.calls = 0

    def select(self, operation_date, top_n):
        self.calls += 1
        return _SelectionResult()


class _ValidationRunner:
    def __init__(self):
        self.calls = []

    def run_horizons(self, **kwargs):
        self.calls.append(kwargs)
        return {}


class _SnapshotRepository:
    def __init__(self, dates):
        self.dates = dates

    def list_dates(self):
        return self.dates


class _ValidationRepository:
    def __init__(self, existing=()):
        self.existing = set(existing)

    def exists(self, selected_at, holding_days):
        return (selected_at, holding_days) in self.existing


class _ReportRepository:
    def __init__(self, directory):
        self.directory = directory

    def save(self, name, markdown):
        path = self.directory / name
        path.write_text(markdown, encoding="utf-8")
        return path


class DailyOperationTest(unittest.TestCase):
    def test_weekday_calendar_counts_sessions_and_holidays(self):
        calendar = WeekdayMarketCalendar({datetime(2026, 7, 29)})
        self.assertEqual(
            4,
            calendar.session_count(datetime(2026, 7, 27), datetime(2026, 8, 3)),
        )

    def test_run_validates_only_mature_unvalidated_horizons(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selected_at = datetime(2026, 7, 20)
            selected_validator = _ValidationRunner()
            runner = DailyOperationRunner(
                titan_runner=_TitanRunner(),
                selected_validation_runner=selected_validator,
                observation_validation_runner=_ValidationRunner(),
                selection_repository=_SnapshotRepository([selected_at]),
                observation_repository=_SnapshotRepository([]),
                selected_validation_repository=_ValidationRepository(
                    {(selected_at, 5)}
                ),
                observation_validation_repository=_ValidationRepository(),
                run_repository=RunRepository(root / "runs"),
                report_repository=_ReportRepository(root / "reports"),
                calendar=WeekdayMarketCalendar(),
            )
            (root / "reports").mkdir()

            result = runner.run(datetime(2026, 8, 4))

            self.assertEqual(RunStatus.COMPLETED, result.record.status)
            self.assertEqual(1, result.record.skipped_validation_count)
            self.assertEqual(1, result.record.validation_count)
            self.assertEqual([10], selected_validator.calls[0]["holding_days"])
            self.assertTrue(result.run_path.exists())
            self.assertTrue(result.report_path.exists())

    def test_completed_run_is_not_repeated_without_force(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report_dir = root / "reports"
            report_dir.mkdir()
            titan = _TitanRunner()
            runner = DailyOperationRunner(
                titan_runner=titan,
                selected_validation_runner=_ValidationRunner(),
                observation_validation_runner=_ValidationRunner(),
                selection_repository=_SnapshotRepository([]),
                observation_repository=_SnapshotRepository([]),
                selected_validation_repository=_ValidationRepository(),
                observation_validation_repository=_ValidationRepository(),
                run_repository=RunRepository(root / "runs"),
                report_repository=_ReportRepository(report_dir),
                calendar=WeekdayMarketCalendar(),
            )
            operation_date = datetime(2026, 7, 28)

            first = runner.run(operation_date)
            second = runner.run(operation_date)

            self.assertEqual(RunStatus.COMPLETED, first.record.status)
            self.assertEqual(RunStatus.SKIPPED, second.record.status)
            self.assertEqual(1, titan.calls)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class _KisSession:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def get(self, url, tr_id, params=None):
        self.calls.append((url, tr_id, params))
        if self.error:
            raise self.error
        return _Response(self.payload)


class HolidayCalendarTest(unittest.TestCase):
    def test_kis_provider_maps_open_flags(self):
        session = _KisSession(
            {
                "rt_cd": "0",
                "output": [
                    {"bass_dt": "20260727", "opnd_yn": "Y"},
                    {"bass_dt": "20260728", "opnd_yn": "N"},
                ],
            }
        )
        provider = KisHolidayProvider(session)

        result = provider.get_sessions(
            datetime(2026, 7, 27).date(),
            datetime(2026, 7, 28).date(),
        )

        self.assertTrue(result[datetime(2026, 7, 27).date()])
        self.assertFalse(result[datetime(2026, 7, 28).date()])
        self.assertEqual("CTCA0903R", session.calls[0][1])

    def test_cached_calendar_persists_kis_sessions(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = HolidayCache(Path(temporary) / "sessions.json")
            provider = KisHolidayProvider(
                _KisSession(
                    {
                        "rt_cd": "0",
                        "output": [
                            {"bass_dt": "20260727", "opnd_yn": "Y"},
                            {"bass_dt": "20260728", "opnd_yn": "N"},
                            {"bass_dt": "20260729", "opnd_yn": "Y"},
                        ],
                    }
                )
            )
            calendar = CachedMarketCalendar(provider, cache)

            count = calendar.session_count(
                datetime(2026, 7, 26),
                datetime(2026, 7, 29),
            )

            self.assertEqual(2, count)
            self.assertIsNone(calendar.last_fallback_reason)
            self.assertTrue(cache.path.exists())

    def test_cached_calendar_falls_back_when_kis_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            calendar = CachedMarketCalendar(
                KisHolidayProvider(_KisSession(error=RuntimeError("offline"))),
                HolidayCache(Path(temporary) / "sessions.json"),
            )

            count = calendar.session_count(
                datetime(2026, 7, 26),
                datetime(2026, 7, 28),
            )

            self.assertEqual(2, count)
            self.assertIn("offline", calendar.last_fallback_reason)

    def test_cached_calendar_refreshes_at_most_once_per_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = _KisSession({"rt_cd": "0", "output": []})
            calendar = CachedMarketCalendar(
                KisHolidayProvider(session),
                HolidayCache(Path(temporary) / "sessions.json"),
            )

            calendar.session_count(
                datetime(2026, 7, 1),
                datetime(2026, 7, 10),
            )
            calendar.session_count(
                datetime(2026, 7, 11),
                datetime(2026, 7, 20),
            )

            self.assertEqual(1, len(session.calls))


class RepositoryListingTest(unittest.TestCase):
    def test_selection_list_dates_ignores_invalid_documents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.mkdir(exist_ok=True)
            (root / "bad.json").write_text("{}", encoding="utf-8")
            repository = SelectionRepository(root)
            selected_at = datetime(2026, 7, 28)
            repository.save([], selected_at=selected_at)

            self.assertEqual([selected_at], repository.list_dates())

    def test_validation_exists_matches_horizon(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = ValidationRepository(Path(temporary))
            self.assertFalse(repository.exists(datetime(2026, 7, 28), 20))


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import date, datetime

from tools.kis_dashboard_server import (
    _latest_completed_weekday,
    _parse_operational_selection_date,
    _parse_entry_settings,
    _parse_exit_rates,
    _weekdays_between,
)


class DashboardDataUpdateTest(unittest.TestCase):
    def test_parses_ten_oclock_entry_limit(self) -> None:
        self.assertEqual(
            ("KIS_1000_LIMIT", 0.03, -0.03),
            _parse_entry_settings({
                "entry_mode": "KIS_1000_LIMIT",
                "entry_limit": "3",
                "entry_minimum": "-3",
            }),
        )

    def test_rejects_unknown_entry_mode(self) -> None:
        with self.assertRaises(ValueError):
            _parse_entry_settings({"entry_mode": "MARKET"})

    def test_parses_custom_exit_percentages(self) -> None:
        self.assertEqual(
            (0.075, 0.12),
            _parse_exit_rates({"profit_target": "7.5", "stop_loss": "12"}),
        )

    def test_requires_both_custom_exit_percentages(self) -> None:
        with self.assertRaises(ValueError):
            _parse_exit_rates({"profit_target": "5", "stop_loss": ""})

    def test_allows_strategy_defaults_when_both_are_blank(self) -> None:
        self.assertEqual(
            (None, None),
            _parse_exit_rates({"profit_target": None, "stop_loss": None}),
        )

    def test_uses_previous_day_before_market_data_cutoff(self) -> None:
        self.assertEqual(
            date(2026, 7, 29),
            _latest_completed_weekday(datetime(2026, 7, 30, 12, 0)),
        )

    def test_skips_weekend_for_latest_completed_day(self) -> None:
        self.assertEqual(
            date(2026, 7, 24),
            _latest_completed_weekday(datetime(2026, 7, 27, 9, 0)),
        )

    def test_allows_previous_weekday_selection_next_morning(self) -> None:
        self.assertEqual(
            date(2026, 7, 30),
            _parse_operational_selection_date(
                "2026-07-30",
                datetime(2026, 7, 31, 9, 0),
            ),
        )

    def test_rejects_incomplete_current_day_selection(self) -> None:
        with self.assertRaises(ValueError):
            _parse_operational_selection_date(
                "2026-07-31",
                datetime(2026, 7, 31, 9, 0),
            )

    def test_allows_current_day_after_market_data_cutoff(self) -> None:
        self.assertEqual(
            date(2026, 7, 31),
            _parse_operational_selection_date(
                "2026-07-31",
                datetime(2026, 7, 31, 15, 40),
            ),
        )

    def test_rejects_weekend_selection(self) -> None:
        with self.assertRaises(ValueError):
            _parse_operational_selection_date(
                "2026-07-26",
                datetime(2026, 7, 27, 9, 0),
            )

    def test_counts_only_weekdays_after_current_coverage(self) -> None:
        self.assertEqual(
            2,
            _weekdays_between(date(2026, 7, 24), date(2026, 7, 28)),
        )


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import date, datetime

from tools.kis_dashboard_server import _latest_kis_test_date


class DashboardKisDateTest(unittest.TestCase):
    def test_before_close_uses_previous_weekday(self) -> None:
        self.assertEqual(
            date(2026, 7, 29),
            _latest_kis_test_date(datetime(2026, 7, 30, 13, 0)),
        )

    def test_after_close_uses_today(self) -> None:
        self.assertEqual(
            date(2026, 7, 30),
            _latest_kis_test_date(datetime(2026, 7, 30, 15, 40)),
        )

    def test_monday_before_close_uses_friday(self) -> None:
        self.assertEqual(
            date(2026, 7, 24),
            _latest_kis_test_date(datetime(2026, 7, 27, 9, 0)),
        )


if __name__ == "__main__":
    unittest.main()

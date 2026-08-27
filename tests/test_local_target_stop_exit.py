import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from tools.local_monthly_test import _run_period, _target_stop_exit


class LocalTargetStopExitTest(unittest.TestCase):
    def test_custom_exit_requires_target_and_stop_together(self):
        with self.assertRaisesRegex(ValueError, "provided together"):
            _run_period(
                "2026-01", 5, 20, "V1.1",
                profit_target=0.05, stop_loss=None,
            )

    def test_custom_exit_rates_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "greater than 0"):
            _run_period(
                "2026-01", 5, 20, "V1.1",
                profit_target=0, stop_loss=0.1,
            )

    def setUp(self):
        self.sessions = [
            datetime(2026, 1, 1) + timedelta(days=index)
            for index in range(21)
        ]

    def test_takes_five_percent_profit(self):
        candles = {
            value: SimpleNamespace(high=106, low=99, close=102)
            for value in self.sessions
        }
        result = _target_stop_exit(
            self.sessions, 0, candles, 100, .05, .05, 20
        )
        self.assertEqual("PROFIT_TARGET_5", result[3])
        self.assertEqual(105, result[1])

    def test_stops_first_when_both_prices_trade_same_day(self):
        candles = {
            value: SimpleNamespace(high=106, low=94, close=100)
            for value in self.sessions
        }
        result = _target_stop_exit(
            self.sessions, 0, candles, 100, .05, .05, 20
        )
        self.assertEqual("STOP_LOSS_5", result[3])
        self.assertEqual(95, result[1])

    def test_sells_at_twentieth_close_inside_band(self):
        candles = {
            value: SimpleNamespace(high=104, low=96, close=101)
            for value in self.sessions
        }
        result = _target_stop_exit(
            self.sessions, 0, candles, 100, .05, .05, 20
        )
        self.assertEqual("MAX_HOLD_20", result[3])
        self.assertEqual(101, result[1])
        self.assertEqual(20, result[2])

    def test_resolves_target_before_incomplete_holding_period(self):
        sessions = self.sessions[:3]
        candles = {
            sessions[1]: SimpleNamespace(high=104, low=99, close=102),
            sessions[2]: SimpleNamespace(high=106, low=101, close=105),
        }

        result = _target_stop_exit(
            sessions, 0, candles, 100, .05, .10, 20,
            allow_incomplete=True,
        )

        self.assertEqual("PROFIT_TARGET_5", result[3])
        self.assertEqual(105, result[1])
        self.assertEqual(2, result[2])

    def test_keeps_unresolved_incomplete_trade_pending(self):
        sessions = self.sessions[:3]
        candles = {
            value: SimpleNamespace(high=104, low=96, close=101)
            for value in sessions[1:]
        }

        result = _target_stop_exit(
            sessions, 0, candles, 100, .05, .10, 20,
            allow_incomplete=True,
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

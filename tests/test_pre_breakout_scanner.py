import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from analysis.pre_breakout_scanner import (
    _close_location,
    _classify_market_regime,
    _monthly_exit,
    _true_ranges,
)


class PreBreakoutScannerTest(unittest.TestCase):
    def test_true_range_includes_overnight_gap(self) -> None:
        candles = [
            SimpleNamespace(high=100, low=90, close=95),
            SimpleNamespace(high=112, low=108, close=110),
        ]
        self.assertEqual([17], _true_ranges(candles))

    def test_close_location_detects_strong_confirmation_close(self) -> None:
        candle = SimpleNamespace(high=110, low=100, close=108)
        self.assertEqual(0.8, _close_location(candle))

    def test_market_regime_uses_breadth_and_trend(self) -> None:
        self.assertEqual("STRONG_UP", _classify_market_regime(.65, .60, .03))
        self.assertEqual("UP", _classify_market_regime(.55, .50, -.02))
        self.assertEqual("SIDEWAYS", _classify_market_regime(.45, .35, .01))
        self.assertEqual("DOWN", _classify_market_regime(.39, .70, .10))

    def test_monthly_exit_uses_profit_target(self) -> None:
        sessions = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(20)]
        candles = {
            value: SimpleNamespace(high=116, low=99, close=110)
            for value in sessions
        }
        result = _monthly_exit(sessions, 0, candles, 100, 0.15, 0.08, 20)
        self.assertEqual("PROFIT_TARGET", result[3])
        self.assertAlmostEqual(115, result[1])
        self.assertEqual(0.08, result[4])

    def test_monthly_exit_is_conservative_when_target_and_stop_both_hit(self) -> None:
        sessions = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(20)]
        candles = {
            value: SimpleNamespace(high=116, low=91, close=100)
            for value in sessions
        }
        result = _monthly_exit(sessions, 0, candles, 100, 0.15, 0.08, 20)
        self.assertEqual("STOP_LOSS", result[3])
        self.assertEqual(92, result[1])

    def test_monthly_exit_uses_atr_adaptive_stop(self) -> None:
        sessions = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(40)]
        candles = {
            value: SimpleNamespace(high=101, low=99, close=100)
            for value in sessions
        }
        result = _monthly_exit(sessions, 20, candles, 100, 0.50, 0.08, 20)
        self.assertEqual(0.04, result[4])


if __name__ == "__main__":
    unittest.main()

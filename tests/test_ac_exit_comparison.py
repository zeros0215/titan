import unittest
from datetime import datetime
from types import SimpleNamespace

from backtest.transaction_cost import TransactionCostPolicy
from research.ac_exit_comparison import target_stop_exit


def candle(day, open_, high, low, close):
    return SimpleNamespace(date=datetime(2026, 1, day), open=open_, high=high, low=low, close=close)


class AcExitComparisonTest(unittest.TestCase):
    def test_excludes_entry_day_and_uses_later_target(self):
        rows = [candle(1, 100, 110, 90, 100), candle(2, 100, 106, 99, 105)]
        result = target_stop_exit(rows, 100, .05, .10, 20, TransactionCostPolicy())
        self.assertEqual("TARGET", result.reason)

    def test_ambiguous_daily_bar_uses_stop_first(self):
        rows = [candle(1, 100, 100, 100, 100), candle(2, 100, 106, 89, 100)]
        result = target_stop_exit(rows, 100, .05, .10, 20, TransactionCostPolicy())
        self.assertEqual("STOP_AMBIGUOUS", result.reason)
        self.assertEqual(-.10, result.net_return)

    def test_stop_gap_fills_at_open(self):
        rows = [candle(1, 100, 100, 100, 100), candle(2, 85, 90, 80, 88)]
        result = target_stop_exit(rows, 100, .05, .10, 20, TransactionCostPolicy())
        self.assertEqual("STOP_GAP", result.reason)
        self.assertEqual(-.15, result.net_return)

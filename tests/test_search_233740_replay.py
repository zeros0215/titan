import unittest

from tools.search_233740_replay import simulate


class ReplayExecutionTest(unittest.TestCase):
    def run_case(self, high, low, opening=100):
        bars = [{'time': '0900'}, {'time': '0905'}]
        rows = [dict(time='090000', open=100, high=999, low=1, close=100),
                dict(time='090500', open=opening, high=high, low=low, close=100)]
        return simulate(bars, rows, {0: {'stop': 90, 'signal': '0900'}},
                        10, 'pivot', slip=0, end='090500')

    def test_entry_is_next_bar_and_same_minute_stop_wins(self):
        # The terminal minute normally disallows entries, so use a later close.
        bars = [{'time': '0900'}, {'time': '0905'}]
        rows = [dict(time='090000', open=100, high=999, low=1, close=100),
                dict(time='090500', open=100, high=120, low=80, close=100),
                dict(time='090600', open=100, high=100, low=100, close=100)]
        r = simulate(bars, rows, {0: {'stop': 90, 'signal': '0900'}},
                     10, 'pivot', slip=0, end='090600')
        trade = r['trades'][0]
        self.assertEqual('090500', trade['entry_time'])
        self.assertEqual('STOP', trade['reason'])
        self.assertEqual(90, trade['exit'])
        self.assertAlmostEqual(-1002.85, trade['net'])

    def test_no_entry_at_session_end(self):
        self.assertEqual(0, self.run_case(120, 80)['trade_count'])

    def test_gap_below_stop_uses_open(self):
        bars = [{'time': '0900'}, {'time': '0905'}]
        rows = [dict(time='090500', open=100, high=105, low=95, close=100),
                dict(time='090600', open=80, high=85, low=75, close=80)]
        r = simulate(bars, rows, {0: {'stop': 90, 'signal': '0900'}},
                     10, 'pivot', slip=0, end='090600')
        self.assertEqual(80, r['trades'][0]['exit'])


if __name__ == '__main__':
    unittest.main()

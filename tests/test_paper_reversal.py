import unittest
from datetime import datetime, timedelta
from research.paper_reversal import empty_state, observe, signal


class PaperReversalTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat('2026-09-08T09:30:05+09:00')
        closes = [7000]*5 + [6990]*5 + [6980]*5 + [6985,6990,6995,7000,7005]
        start = self.now.replace(minute=10, second=0)
        self.rows = [dict(date='20260908', time=(start+timedelta(minutes=i)).strftime('%H%M%S'),
                          open=p, high=p+5, low=p-5, close=p, volume=100)
                     for i,p in enumerate(closes)]
        self.quote = dict(close=7005, date='2026-09-08')

    def test_completed_signal_ignores_future_rows(self):
        self.assertTrue(signal(self.rows, self.now)[2])
        self.assertTrue(signal(self.rows+[dict(date='20260908',time='093000',close=1)], self.now)[2])

    def test_missing_and_invalid_data_block_entry(self):
        self.assertEqual(signal(self.rows[:-1], self.now)[1], 'MISSING_MINUTES')
        self.rows[-1]['close'] = 7006
        self.assertEqual(signal(self.rows, self.now)[1], 'INVALID_PRICE')

    def test_entry_exit_costs_and_no_same_boundary_reentry(self):
        state = empty_state()
        observe(state, self.rows, self.quote, self.now)
        self.assertEqual(state['position']['entry'], 7010)
        observe(state, self.rows, dict(close=7060,date='20260908'), self.now+timedelta(seconds=5))
        self.assertEqual(len(state['trades']), 1)
        self.assertAlmostEqual(state['realized_net'], 4500-(7010+7055)*100*.00015)
        observe(state, self.rows, self.quote, self.now+timedelta(seconds=10))
        self.assertIsNone(state['position'])
        self.assertEqual(state['real_orders'], 0)

    def test_late_signal_is_not_replayed(self):
        state = empty_state()
        observe(state, self.rows, self.quote, self.now+timedelta(minutes=1))
        self.assertEqual(state['status'], 'MISSED_BOUNDARY')
        self.assertIsNone(state['position'])

    def test_stale_quote_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Stale'):
            observe(empty_state(), self.rows, dict(close=7005,date='20260907'), self.now)

    def test_overnight_position_requires_review(self):
        state = empty_state()
        observe(state, self.rows, self.quote, self.now)
        observe(state, [], dict(close=7100,date='20260909'), self.now+timedelta(days=1))
        self.assertEqual(state['status'], 'REVIEW_OVERNIGHT')
        self.assertEqual(state['trades'], [])

    def test_gap_stop_uses_observed_price(self):
        state = empty_state()
        observe(state, self.rows, self.quote, self.now)
        observe(state, [], dict(close=6800,date='20260908'), self.now+timedelta(seconds=5))
        self.assertEqual(state['trades'][0]['exit'], 6795)
        self.assertEqual(state['trades'][0]['reason'], 'STOP')


if __name__ == '__main__':
    unittest.main()

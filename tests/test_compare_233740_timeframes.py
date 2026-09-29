import unittest
from tools.compare_233740_timeframes import aggregate


class AggregationTest(unittest.TestCase):
    def test_three_minutes_preserves_ohlcv_and_excludes_partial(self):
        rows=[dict(time=f'151{n}00',open=100+n,high=110+n,low=90+n,
                   close=101+n,volume=n) for n in range(5,10)]
        self.assertEqual([dict(time='1515',open=105,high=117,low=95,
                               close=108,volume=18)],aggregate(rows,3))

    def test_missing_minute_is_not_silently_aggregated(self):
        row=dict(time='090000',open=100,high=110,low=90,close=100,volume=1)
        with self.assertRaises(AssertionError):
            aggregate([row],3)


if __name__=='__main__':
    unittest.main()

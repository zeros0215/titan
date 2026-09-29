import unittest
from tools.search_233740_patterns import replay


class PatternReplayTest(unittest.TestCase):
    def test_one_minute_trail_updates_after_that_minute(self):
        bars=[dict(time='0900',high=100),dict(time='0901',high=150)]
        minutes=[dict(time='090100',open=100,high=150,low=90,close=140),
                 dict(time='090200',open=140,high=140,low=115,close=120)]
        r=replay(bars,minutes,{0:dict(signal_time='0900')},80,'trailing',30,
                 slip=0,bar_minutes=1)
        self.assertEqual('090200',r['trades'][0]['exit_time'])
        self.assertEqual(120,r['trades'][0]['exit'])

    def test_trailing_uses_completed_bar_and_not_same_bar_low(self):
        bars=[dict(time='0900',high=100),dict(time='0905',high=150)]
        minutes=[dict(time='090500',open=100,high=105,low=95,close=100),
                 dict(time='090900',open=100,high=150,low=90,close=140),
                 dict(time='091000',open=140,high=140,low=115,close=120),
                 dict(time='153000',open=120,high=120,low=120,close=120)]
        signals={0:dict(signal_time='0900')}
        r=replay(bars,minutes,signals,80,'trailing',30,slip=0)
        self.assertEqual('091000',r['trades'][0]['exit_time'])
        self.assertEqual(120,r['trades'][0]['exit'])

    def test_fixed_stop_has_priority_over_target_same_minute(self):
        bars=[dict(time='0900',high=100),dict(time='0905',high=150)]
        minutes=[dict(time='090500',open=100,high=150,low=50,close=100)]
        r=replay(bars,minutes,{0:dict(signal_time='0900')},30,'fixed',30,slip=0)
        self.assertEqual(70,r['trades'][0]['exit'])


if __name__=='__main__':
    unittest.main()

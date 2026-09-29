import unittest
from tools.search_233740_mixed import direction


class MixedTimeframeTest(unittest.TestCase):
    def test_unclosed_five_minute_bar_cannot_change_filter(self):
        bars=[dict(time='0900',close=100),dict(time='0905',close=90),
              dict(time='0910',close=999)]
        self.assertFalse(direction(bars,5,554,'rising_close'))
        self.assertTrue(direction(bars,5,555,'rising_close'))

    def test_ma_needs_history_and_uses_only_completed_bars(self):
        bars=[dict(time=f'090{i}',close=100+i) for i in range(6)]
        self.assertFalse(direction(bars,1,545,'ma5'))
        self.assertTrue(direction(bars,1,546,'ma5'))
        bars.append(dict(time='0906',close=1))
        self.assertTrue(direction(bars,1,546,'ma5'))
        self.assertFalse(direction(bars,1,547,'ma5'))


if __name__=='__main__':
    unittest.main()

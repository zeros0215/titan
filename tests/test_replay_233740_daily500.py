import unittest
from tools.replay_233740_daily500 import replay_lots


class Daily500Test(unittest.TestCase):
    def fixture(self):
        bars = [dict(time=f'090{i}', high=7000) for i in range(8)]
        minutes = [dict(time=f'090{i}00', open=7000, high=7010, low=6990, close=7000)
                   for i in range(1, 8)]
        minutes.append(dict(time='153000', open=7000, high=7000, low=7000, close=7000))
        return bars, minutes, {i: dict(signal_time=f'090{i}') for i in range(7)}

    def test_adds_while_holding_but_caps_daily_buys(self):
        bars, minutes, signals = self.fixture()
        r = replay_lots(bars, minutes, signals)
        self.assertEqual(r['bought_quantity'], 500)
        self.assertEqual(r['skipped_daily_limit'], 2)
        self.assertTrue(all(t['exit_time'] == '153000' for t in r['trades']))
        self.assertEqual(len({t['entry_time'] for t in r['trades']}), 5)

    def test_selling_does_not_restore_daily_limit(self):
        bars, minutes, signals = self.fixture()
        for m in minutes[:-1]:
            m['high'] = 7100
        r = replay_lots(bars, minutes, signals)
        self.assertEqual(r['bought_quantity'], 500)
        self.assertEqual(r['wins'], 5)
        self.assertTrue(all(t['entry_time'] == t['exit_time'] for t in r['trades']))

    def test_independent_targets_and_stop_priority(self):
        bars, minutes, _ = self.fixture()
        minutes[1].update(open=7020, high=7030, low=7010, close=7020)
        minutes[2].update(open=7030, high=7060, low=7010, close=7040)
        minutes[3].update(open=7020, high=7080, low=6950, close=7000)
        r = replay_lots(bars, minutes, {0: {}, 1: {}})
        self.assertEqual([t['entry'] for t in r['trades']], [7005, 7025])
        self.assertEqual([t['reason'] for t in r['trades']], ['TARGET', 'STOP_OR_TRAIL'])


if __name__ == '__main__':
    unittest.main()

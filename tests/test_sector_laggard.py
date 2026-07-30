import unittest
from dataclasses import replace

from analysis.sector_laggard import SectorLaggardTrade, _summary


class SectorLaggardTest(unittest.TestCase):
    def test_summary_uses_net_returns(self) -> None:
        trade = SectorLaggardTrade(
            signal_date="2023-01-02", group="은행", code="000001",
            name="테스트", group_return=.05, stock_return=.01, lag_gap=.04,
            positive_ratio=.8, volume_ratio=1.2, confirmed=True,
            entry_date="2023-01-03", exit_date="2023-01-09",
            exit_reason="5거래일 종가", holding_sessions=5,
            gross_return=.02, net_return=.015, win=True,
        )
        result = _summary([trade, replace(trade, net_return=-.005, win=False)])
        self.assertEqual(2, result["trades"])
        self.assertEqual(.5, result["win_rate"])
        self.assertAlmostEqual(.005, result["average_net_return"])


if __name__ == "__main__":
    unittest.main()

import unittest

from price_history.krx_adjustment import KrxAdjustedPriceCompiler


def row(day, close, shares):
    return (
        "Stock", "KOSPI", day, close, close, close, close, 1000, shares
    )


class KrxAdjustmentTest(unittest.TestCase):
    def test_normalizes_no_trade_ohlc_to_close(self):
        values = (
            "005930", "Stock", "KOSPI", "2024-01-01T00:00:00",
            0.0, 0.0, 0.0, 100.0, 0, 1000,
        )

        normalized = KrxAdjustedPriceCompiler._normalize_no_trade(values)

        self.assertEqual((100.0, 100.0, 100.0, 100.0), normalized[4:8])

    def test_detects_split_and_adjusts_only_prior_prices(self):
        rows = [
            row("2024-01-01T00:00:00", 100.0, 100),
            row("2024-01-02T00:00:00", 20.0, 500),
            row("2024-01-03T00:00:00", 22.0, 500),
        ]
        compiler = KrxAdjustedPriceCompiler()

        actions, unresolved = compiler._events(rows)
        factors = compiler._backward_factors(rows, actions)

        self.assertEqual(1, len(actions))
        self.assertEqual([], unresolved)
        self.assertAlmostEqual(0.2, factors[0][0])
        self.assertAlmostEqual(1.0, factors[1][0])
        self.assertAlmostEqual(1.0, factors[2][0])

    def test_does_not_adjust_unexplained_price_jump(self):
        rows = [
            row("2024-01-01T00:00:00", 100.0, 100),
            row("2024-01-02T00:00:00", 200.0, 100),
        ]

        actions, unresolved = KrxAdjustedPriceCompiler()._events(rows)

        self.assertEqual([], actions)
        self.assertEqual(1, len(unresolved))
        self.assertEqual(
            "UNEXPLAINED_PRICE_DISCONTINUITY",
            unresolved[0]["classification"],
        )

    def test_quarantines_61_sessions_after_unresolved_jump(self):
        rows = [
            row(f"2024-01-{index + 1:02d}T00:00:00", 100.0, 100)
            for index in range(70)
        ]
        unresolved = [{
            "index": 2,
            "classification": "UNEXPLAINED_PRICE_DISCONTINUITY",
        }]

        intervals = KrxAdjustedPriceCompiler._quarantines(
            rows, unresolved
        )

        self.assertEqual(rows[2][2], intervals[0]["start"])
        self.assertEqual(rows[62][2], intervals[0]["end"])


if __name__ == "__main__":
    unittest.main()

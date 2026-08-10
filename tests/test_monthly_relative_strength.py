import unittest

from research.monthly_relative_strength import select_low_volatility


class MonthlyRelativeStrengthTest(unittest.TestCase):
    def test_selects_lowest_volatility_inside_top_momentum_quintile(self) -> None:
        rows = [
            {"code": f"{index:06d}", "momentum": index / 100, "volatility": 1 / index}
            for index in range(1, 11)
        ]

        selected = select_low_volatility(rows, top_fraction=0.2, limit=5)

        self.assertEqual(["000010", "000009"], [row["code"] for row in selected])

    def test_rejects_invalid_parameters(self) -> None:
        with self.assertRaises(ValueError):
            select_low_volatility([], top_fraction=0)
        with self.assertRaises(ValueError):
            select_low_volatility([], limit=0)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from research.portfolio_evaluation import (
    _replay,
    evaluate_mixed_fixed_slot_portfolio,
    save_portfolio_report,
)
from datetime import datetime, timedelta


class PortfolioEvaluationTest(unittest.TestCase):
    def test_report_keeps_zero_trade_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate-zero"
            candidate.mkdir()
            output = root / "portfolio.md"

            save_portfolio_report([candidate], output)

            report = output.read_text(encoding="utf-8")
            self.assertIn("candidate-zero", report)
            self.assertIn("no trades", report)

    def test_mixed_replay_enforces_source_slots_and_duplicate_codes(self) -> None:
        entry = datetime(2025, 1, 2)
        exit_at = entry + timedelta(days=2)
        signals = [
            {
                "source": "A", "entry": entry, "exit": exit_at,
                "code": "001", "rank": 1, "selection_price": 100.0,
                "net_return": .10,
            },
            {
                "source": "A", "entry": entry, "exit": exit_at,
                "code": "002", "rank": 2, "selection_price": 100.0,
                "net_return": .10,
            },
            {
                "source": "C", "entry": entry, "exit": exit_at,
                "code": "001", "rank": 1, "selection_price": 100.0,
                "net_return": .10,
            },
        ]
        prices = {
            code: {entry: 100.0, exit_at: 110.0}
            for code in ("001", "002")
        }

        result = _replay(signals, prices, 2, {"A": 1, "C": 1})

        self.assertEqual(1, result["accepted_trades"])
        self.assertEqual(2, result["capacity_skips"] + result["duplicate_skips"])

    def test_mixed_portfolio_requires_matching_sources(self) -> None:
        with self.assertRaises(ValueError):
            evaluate_mixed_fixed_slot_portfolio(
                {"A": Path("a")}, {"C": 1},
            )


if __name__ == "__main__":
    unittest.main()

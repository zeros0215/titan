import json
import tempfile
import unittest
from pathlib import Path

from research.strategy_search import (
    generate_bounded_candidates,
    rank_walk_forward_results,
    render_ranking_markdown,
    representative_candidates,
    save_candidate_grid,
)


class StrategySearchTest(unittest.TestCase):
    def test_grid_preserves_s80_safety_filters(self) -> None:
        rows = generate_bounded_candidates()

        self.assertEqual(81, len(rows))
        self.assertTrue(all(row["config"]["use_market_regime_rules"] for row in rows))
        self.assertTrue(all(row["config"]["reject_combined_volatility_warnings"] for row in rows))
        self.assertTrue(all(row["config"]["require_acceleration_or_volume_surge"] for row in rows))
        self.assertTrue(all(
            sum(row["config"][key] for key in (
                "trend_weight", "momentum_weight", "volume_weight",
                "price_action_weight", "risk_weight", "context_weight",
            )) == 100 for row in rows
        ))

    def test_saves_immutable_research_configs_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = generate_bounded_candidates()[:2]

            manifest = save_candidate_grid(root, rows)

            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertTrue(payload["operational_strategy_unchanged"])
            self.assertEqual(2, payload["candidate_count"])

    def test_selects_five_representative_candidates(self) -> None:
        rows = representative_candidates(generate_bounded_candidates())
        self.assertEqual(5, len(rows))
        self.assertIn("s80-m60-mom10-t30-r15", {
            row["research_id"] for row in rows
        })

    def test_ranks_only_sufficient_out_of_sample_evidence_as_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            good = root / "good.json"
            small = root / "small.json"
            good.write_text(json.dumps({
                "strategy_version": "good",
                "folds": [
                    {"total_count": 60, "average_net_return": 0.02, "average_excess_return": 0.01},
                    {"total_count": 60, "average_net_return": 0.03, "average_excess_return": 0.015},
                ],
            }), encoding="utf-8")
            small.write_text(json.dumps({
                "strategy_version": "small",
                "folds": [{"total_count": 3, "average_net_return": 0.20, "average_excess_return": 0.19}],
            }), encoding="utf-8")

            rows = rank_walk_forward_results([small, good])

            self.assertEqual("good", rows[0]["strategy_version"])
            self.assertTrue(rows[0]["eligible"])
            self.assertEqual("INSUFFICIENT_TRADES", rows[1]["reason"])
            self.assertIn("Research only", render_ranking_markdown(rows))

    def test_absolute_objective_accepts_profit_despite_negative_excess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "negative.json"
            path.write_text(json.dumps({
                "strategy_version": "negative",
                "folds": [
                    {"total_count": 60, "average_net_return": 0.01, "average_excess_return": -0.01},
                    {"total_count": 60, "average_net_return": 0.02, "average_excess_return": -0.02},
                ],
            }), encoding="utf-8")

            row = rank_walk_forward_results([path])[0]

            self.assertTrue(row["eligible"])
            self.assertEqual("ELIGIBLE", row["reason"])

    def test_absolute_objective_rejects_profit_concentrated_in_one_fold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unstable.json"
            path.write_text(json.dumps({
                "strategy_version": "unstable",
                "folds": [
                    {"total_count": 40, "average_net_return": -0.01, "average_excess_return": 0.01},
                    {"total_count": 40, "average_net_return": -0.01, "average_excess_return": 0.01},
                    {"total_count": 40, "average_net_return": 0.08, "average_excess_return": 0.01},
                ],
            }), encoding="utf-8")

            row = rank_walk_forward_results([path])[0]

            self.assertFalse(row["eligible"])
            self.assertEqual("INSUFFICIENT_PROFITABLE_FOLDS", row["reason"])


if __name__ == "__main__":
    unittest.main()

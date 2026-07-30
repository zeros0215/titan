import json
import tempfile
import unittest
from pathlib import Path

from repository.strategy_candidate_repository import StrategyCandidateRepository
from strategy_gate.gate import StrategyGate
from strategy_gate.model import CandidateStatus
from strategy_gate.service import StrategyGateService


class StrategyGateTest(unittest.TestCase):
    def test_stronger_complete_candidate_passes_all_gates(self):
        comparison, checks = StrategyGate().evaluate(
            self._result("1.0.0", 0.02, 0.01, 90),
            self._result("1.1.0", 0.03, 0.02, 96),
        )

        self.assertTrue(comparison["passed"])
        self.assertTrue(all(item["passed"] for item in checks))

    def test_partial_universe_blocks_candidate(self):
        candidate = self._result("1.1.0", 0.03, 0.02, 96)
        candidate["folds"][0]["universe_coverages"] = ["PARTIAL"]

        comparison, checks = StrategyGate().evaluate(
            self._result("1.0.0", 0.02, 0.01, 90),
            candidate,
        )

        self.assertFalse(comparison["passed"])
        universe = next(
            item for item in checks if item["name"] == "COMPLETE_UNIVERSE"
        )
        self.assertFalse(universe["passed"])

    def test_repository_hash_detects_config_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = StrategyCandidateRepository(Path(temporary))
            candidate = repository.propose(
                "1.1.0",
                "test candidate",
                {"minimum_score": 82},
                "tester",
            )
            candidate.config["minimum_score"] = 70

            with self.assertRaises(ValueError):
                repository.save(candidate)

    def test_repository_detects_audit_event_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = StrategyCandidateRepository(Path(temporary))
            repository.propose(
                "1.1.0",
                "test candidate",
                {"minimum_score": 82},
                "tester",
            )
            path = Path(temporary) / "1.1.0.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["audit_events"][0]["details"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "audit chain"):
                repository.load("1.1.0")

    def test_only_passed_candidate_can_be_approved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = StrategyCandidateRepository(root / "candidates")
            service = StrategyGateService(repository, StrategyGate())
            repository.propose(
                "1.1.0",
                "test candidate",
                {"minimum_score": 82},
                "author",
            )
            baseline = root / "baseline.json"
            candidate_result = root / "candidate.json"
            baseline.write_text(
                json.dumps(self._result("1.0.0", 0.02, 0.01, 90)),
                encoding="utf-8",
            )
            candidate_result.write_text(
                json.dumps({
                    **self._result("1.1.0", 0.03, 0.02, 96),
                    "strategy_config_hash": repository.load("1.1.0").config_hash,
                }),
                encoding="utf-8",
            )

            evaluated = service.evaluate(
                "1.1.0",
                baseline,
                candidate_result,
                "reviewer",
            )
            approved = service.approve(
                "1.1.0",
                "owner",
                "all evidence reviewed",
            )

            self.assertEqual(CandidateStatus.PASSED, evaluated.status)
            self.assertEqual(CandidateStatus.APPROVED, approved.status)
            self.assertEqual("owner", approved.approved_by)
            self.assertEqual(3, len(approved.audit_events))

    @staticmethod
    def _result(version, net_return, excess_return, successes):
        return {
            "strategy_version": version,
            "strategy_frozen": True,
            "holding_days": 20,
            "interval_months": 1,
            "folds": [
                {
                    "index": index,
                    "attempted_dates": 10,
                    "completed_dates": 10,
                    "total_count": 60,
                    "success_count": successes // 2,
                    "average_net_return": net_return,
                    "average_excess_return": excess_return,
                    "universe_coverages": ["COMPLETE"],
                    "errors": [],
                }
                for index in (1, 2)
            ],
        }


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from research.challenger_freeze import save_challenger_freeze


class ChallengerFreezeTest(unittest.TestCase):
    def test_freeze_is_idempotent_and_rejects_changed_rules(self) -> None:
        candidates = [
            {"research_id": "challenger-a-breakout-h40", "config": {"x": 1}, "holding_days": 40},
            {"research_id": "challenger-c-pullback-h40", "config": {"x": 2}, "holding_days": 40},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "freeze.json"
            save_challenger_freeze(candidates, output)
            first = json.loads(output.read_text(encoding="utf-8"))

            save_challenger_freeze(candidates, output)
            candidates[1]["config"]["x"] = 3

            with self.assertRaises(ValueError):
                save_challenger_freeze(candidates, output)
            self.assertEqual(
                first, json.loads(output.read_text(encoding="utf-8"))
            )


if __name__ == "__main__":
    unittest.main()

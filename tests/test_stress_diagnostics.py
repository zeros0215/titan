import json
import tempfile
import unittest
from pathlib import Path

from research.stress_diagnostics import save_stress_diagnostics


class StressDiagnosticsTest(unittest.TestCase):
    def test_report_summarizes_year_regime_and_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "artifact"
            validations = artifact / "validations"
            validations.mkdir(parents=True)
            (validations / "one.json").write_text(json.dumps({
                "selected_at": "2022-01-03T00:00:00",
                "result": {"contexts": [{
                    "regime": "BULL", "total_count": 1,
                    "average_return": .1, "average_excess_return": .03,
                }]},
                "trades": [{
                    "code": "001", "name": "Alpha", "net_return": .1,
                }],
            }), encoding="utf-8")
            output = Path(temporary) / "report.md"

            save_stress_diagnostics({"A": artifact}, output)

            report = output.read_text(encoding="utf-8")
            self.assertIn("2022", report)
            self.assertIn("BULL", report)
            self.assertIn("Alpha", report)


if __name__ == "__main__":
    unittest.main()

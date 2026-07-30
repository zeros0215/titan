import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from data.quarantine import QualityQuarantinePolicy


class QualityQuarantineTest(unittest.TestCase):
    def test_excludes_only_code_inside_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quality.json"
            path.write_text(json.dumps([{
                "code": "000001",
                "start": "2024-01-02T00:00:00",
                "end": "2024-03-31T00:00:00",
            }]), encoding="utf-8")
            policy = QualityQuarantinePolicy.from_file(path)

            inside = policy.filter(
                [
                    SimpleNamespace(code="000001"),
                    SimpleNamespace(code="000002"),
                ],
                datetime(2024, 2, 1),
            )
            after = policy.filter(
                [SimpleNamespace(code="000001")],
                datetime(2024, 4, 1),
            )

        self.assertEqual(["000002"], [item.code for item in inside])
        self.assertEqual(["000001"], [item.code for item in after])


if __name__ == "__main__":
    unittest.main()

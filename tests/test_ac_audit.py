import unittest

from research.ac_audit import _weekday_pass


class AcAuditTest(unittest.TestCase):
    def test_weekday_gate_requires_four_positive_robust_days(self) -> None:
        self.assertTrue(_weekday_pass({"rows": [
            {"average_without_best": value} for value in (0.1, 0.2, 0.3, 0.4, -0.1)
        ]}))
        self.assertFalse(_weekday_pass({"rows": [
            {"average_without_best": value} for value in (0.1, 0.2, 0.3, -0.1, -0.2)
        ]}))

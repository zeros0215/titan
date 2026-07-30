import unittest

from pilot.history import PilotReadinessEvaluator


def record(day: int, status: str = "PASS") -> dict:
    return {
        "as_of": f"2026-07-{day:02d}T15:30:00",
        "status": status,
        "api_success_rate": 1.0 if status == "PASS" else 0.0,
        "retry_count": 0,
        "request_count": 10,
        "exclusion_rate": 0.0 if status == "PASS" else 1.0,
        "fetch_failures": {},
    }


class PilotReadinessEvaluatorTest(unittest.TestCase):
    def test_uses_worst_result_when_same_day_has_multiple_runs(self) -> None:
        result = PilotReadinessEvaluator(required_days=5).evaluate([
            record(28, "PASS"),
            record(28, "FAIL"),
        ])

        self.assertEqual("COLLECTING", result.status)
        self.assertEqual(1, result.observed_days)
        self.assertEqual("FAIL", result.days[0].status)
        self.assertEqual(2, result.days[0].run_count)

    def test_is_ready_after_required_consecutive_passing_days(self) -> None:
        result = PilotReadinessEvaluator(required_days=5).evaluate(
            [record(day) for day in range(21, 26)]
        )

        self.assertEqual("READY", result.status)
        self.assertEqual(5, result.passing_days)
        self.assertEqual(5, result.consecutive_passing_days)

    def test_zero_request_count_does_not_divide_by_zero(self) -> None:
        item = record(28)
        item["request_count"] = 0

        result = PilotReadinessEvaluator().evaluate([item])

        self.assertEqual(0.0, result.days[0].maximum_retry_rate)


if __name__ == "__main__":
    unittest.main()

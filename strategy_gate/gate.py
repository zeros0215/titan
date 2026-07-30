from strategy_gate.policy import StrategyGatePolicy


class StrategyGate:
    def __init__(self, policy: StrategyGatePolicy | None = None) -> None:
        self.policy = policy or StrategyGatePolicy()

    def evaluate(self, baseline: dict, candidate: dict) -> tuple[dict, list[dict]]:
        baseline_metrics = self._metrics(baseline)
        candidate_metrics = self._metrics(candidate)
        comparable = (
            baseline.get("holding_days") == candidate.get("holding_days")
            and baseline.get("interval_months") == candidate.get("interval_months")
        )
        matched = self._matched_folds(baseline, candidate)
        positive_fold_ratio = (
            sum(
                candidate_excess is not None
                and baseline_excess is not None
                and candidate_excess > baseline_excess
                for baseline_excess, candidate_excess in matched
            ) / len(matched)
            if matched else 0.0
        )
        net_delta = self._delta(
            candidate_metrics["average_net_return"],
            baseline_metrics["average_net_return"],
        )
        excess_delta = self._delta(
            candidate_metrics["average_excess_return"],
            baseline_metrics["average_excess_return"],
        )
        checks = [
            self._check(
                "BASE_VERSION_MATCH",
                baseline.get("strategy_version") is not None,
                baseline.get("strategy_version"),
            ),
            self._check(
                "DISTINCT_STRATEGY_VERSION",
                candidate.get("strategy_version") is not None
                and candidate.get("strategy_version")
                != baseline.get("strategy_version"),
                candidate.get("strategy_version"),
            ),
            self._check("COMPARABLE_PLAN", comparable),
            self._check(
                "STRATEGY_FROZEN",
                candidate.get("strategy_frozen") is True,
            ),
            self._check(
                "MINIMUM_FOLDS",
                candidate_metrics["fold_count"] >= self.policy.minimum_folds,
                candidate_metrics["fold_count"],
            ),
            self._check(
                "MINIMUM_SAMPLES",
                candidate_metrics["total_count"] >= self.policy.minimum_samples,
                candidate_metrics["total_count"],
            ),
            self._check(
                "COMPLETION_RATE",
                candidate_metrics["completion_rate"]
                >= self.policy.minimum_completion_rate,
                candidate_metrics["completion_rate"],
            ),
            self._check(
                "ZERO_ERRORS",
                not self.policy.require_zero_errors
                or candidate_metrics["error_count"] == 0,
                candidate_metrics["error_count"],
            ),
            self._check(
                "COMPLETE_UNIVERSE",
                not self.policy.require_complete_universe
                or candidate_metrics["complete_universe"],
                candidate_metrics["universe_coverages"],
            ),
            self._check(
                "NET_RETURN_IMPROVEMENT",
                net_delta is not None
                and net_delta >= self.policy.minimum_net_return_improvement,
                net_delta,
            ),
            self._check(
                "EXCESS_RETURN_IMPROVEMENT",
                excess_delta is not None
                and excess_delta
                >= self.policy.minimum_excess_return_improvement,
                excess_delta,
            ),
            self._check(
                "NON_DECREASING_WIN_RATE",
                candidate_metrics["win_rate"] >= baseline_metrics["win_rate"],
                candidate_metrics["win_rate"] - baseline_metrics["win_rate"],
            ),
            self._check(
                "POSITIVE_EXCESS_RETURN",
                candidate_metrics["average_excess_return"] is not None
                and candidate_metrics["average_excess_return"] > 0,
                candidate_metrics["average_excess_return"],
            ),
            self._check(
                "POSITIVE_FOLD_RATIO",
                positive_fold_ratio >= self.policy.minimum_positive_fold_ratio,
                positive_fold_ratio,
            ),
        ]
        comparison = {
            "baseline": baseline_metrics,
            "candidate": candidate_metrics,
            "net_return_delta": net_delta,
            "excess_return_delta": excess_delta,
            "win_rate_delta": (
                candidate_metrics["win_rate"] - baseline_metrics["win_rate"]
            ),
            "positive_fold_ratio": positive_fold_ratio,
            "passed": all(item["passed"] for item in checks),
        }
        return comparison, checks

    @staticmethod
    def _metrics(payload):
        folds = payload.get("folds", [])
        total = sum(item.get("total_count", 0) for item in folds)

        def weighted(key):
            available = [
                item for item in folds
                if item.get(key) is not None and item.get("total_count", 0)
            ]
            count = sum(item["total_count"] for item in available)
            return (
                sum(item[key] * item["total_count"] for item in available) / count
                if count else None
            )

        attempted = sum(item.get("attempted_dates", 0) for item in folds)
        completed = sum(item.get("completed_dates", 0) for item in folds)
        coverages = sorted({
            coverage
            for item in folds
            for coverage in item.get("universe_coverages", [])
        })
        success = sum(item.get("success_count", 0) for item in folds)
        return {
            "fold_count": len(folds),
            "total_count": total,
            "win_rate": success / total if total else 0.0,
            "average_net_return": weighted("average_net_return"),
            "average_excess_return": weighted("average_excess_return"),
            "completion_rate": completed / attempted if attempted else 0.0,
            "error_count": sum(len(item.get("errors", [])) for item in folds),
            "universe_coverages": coverages,
            "complete_universe": bool(coverages)
            and all(item == "COMPLETE" for item in coverages),
        }

    @staticmethod
    def _matched_folds(baseline, candidate):
        baseline_by_index = {
            item.get("index"): item.get("average_excess_return")
            for item in baseline.get("folds", [])
        }
        return [
            (
                baseline_by_index[item.get("index")],
                item.get("average_excess_return"),
            )
            for item in candidate.get("folds", [])
            if item.get("index") in baseline_by_index
        ]

    @staticmethod
    def _delta(left, right):
        return left - right if left is not None and right is not None else None

    @staticmethod
    def _check(name, passed, actual=None):
        return {"name": name, "passed": bool(passed), "actual": actual}

from collections import defaultdict
from datetime import datetime

from monitoring.model import (
    HorizonKpi,
    DataQualityKpi,
    KpiMetrics,
    MonitoringSnapshot,
    MonitorStatus,
    OperationKpi,
)
from monitoring.policy import MonitoringPolicy
from operation.model import RunStatus


class MonitoringEngine:
    """Compares recent outturn with a non-overlapping historical baseline."""

    def __init__(self, aggregator, policy: MonitoringPolicy | None = None) -> None:
        self.aggregator = aggregator
        self.policy = policy or MonitoringPolicy()

    def build(
        self,
        validation_records,
        run_records=(),
        quality_records=(),
    ) -> MonitoringSnapshot:
        ordered = sorted(
            validation_records,
            key=lambda record: (record.evaluation_date, record.holding_days),
        )
        recent = ordered[-self.policy.recent_run_count:]
        baseline = ordered[:-self.policy.recent_run_count]
        cumulative_summary = self.aggregator.aggregate(ordered)
        recent_summary = self.aggregator.aggregate(recent)
        baseline_summary = self.aggregator.aggregate(baseline)
        horizons = self._horizons(ordered)

        overall_status = max(
            (item.status for item in horizons),
            key=self._severity,
            default=MonitorStatus.NORMAL,
        )
        eligible = [item for item in horizons if item.data_state == "READY"]
        reasons = [
            f"{item.holding_days}일: {reason}"
            for item in horizons
            for reason in item.reasons
        ]
        data_state = "READY" if eligible else "INSUFFICIENT_DATA"
        if not eligible:
            reasons.append(
                "최근 구간과 기준 구간이 각각 최소 "
                f"{self.policy.minimum_sample_size}개 표본을 충족해야 판정합니다."
            )

        return MonitoringSnapshot(
            generated_at=datetime.now(),
            status=overall_status,
            data_state=data_state,
            cumulative=self._metrics(cumulative_summary),
            recent=self._metrics(recent_summary),
            baseline=self._metrics(baseline_summary),
            horizons=horizons,
            operation=self._operation(run_records),
            data_quality=self._data_quality(quality_records),
            reasons=reasons,
            context_rows=cumulative_summary.context_validations,
            feature_rows=cumulative_summary.feature_validations,
            score_band_rows=cumulative_summary.score_band_validations,
        )

    def _horizons(self, records) -> list[HorizonKpi]:
        grouped = defaultdict(list)
        for record in records:
            grouped[record.holding_days].append(record)
        return [
            self._assess_horizon(days, items)
            for days, items in sorted(grouped.items())
        ]

    def _assess_horizon(self, holding_days, records) -> HorizonKpi:
        recent_records = records[-self.policy.recent_run_count:]
        baseline_records = records[:-self.policy.recent_run_count]
        recent = self._metrics(self.aggregator.aggregate(recent_records))
        baseline = self._metrics(self.aggregator.aggregate(baseline_records))
        if (
            recent.sample_count < self.policy.minimum_sample_size
            or baseline.sample_count < self.policy.minimum_sample_size
        ):
            return HorizonKpi(
                holding_days=holding_days,
                status=MonitorStatus.NORMAL,
                data_state="INSUFFICIENT_DATA",
                recent=recent,
                baseline=baseline,
                reasons=[],
            )

        win_delta = recent.win_rate - baseline.win_rate
        excess_delta = self._optional_delta(
            recent.average_excess_return,
            baseline.average_excess_return,
        )
        reasons: list[str] = []
        alert = False
        watch = False
        if win_delta <= -self.policy.alert_win_rate_drop:
            alert = True
            reasons.append(f"승률이 기준 대비 {win_delta:.1%} 하락")
        elif win_delta <= -self.policy.watch_win_rate_drop:
            watch = True
            reasons.append(f"승률이 기준 대비 {win_delta:.1%} 하락")
        if excess_delta is not None:
            if excess_delta <= -self.policy.alert_excess_return_drop:
                alert = True
                reasons.append(f"초과수익률이 기준 대비 {excess_delta:.2%} 하락")
            elif excess_delta <= -self.policy.watch_excess_return_drop:
                watch = True
                reasons.append(f"초과수익률이 기준 대비 {excess_delta:.2%} 하락")
        if (
            recent.win_rate < self.policy.absolute_alert_win_rate
            and recent.average_excess_return is not None
            and recent.average_excess_return
            < self.policy.absolute_alert_excess_return
        ):
            alert = True
            reasons.append("최근 승률과 초과수익률이 절대 경고 기준을 동시 하회")

        status = (
            MonitorStatus.ALERT
            if alert
            else MonitorStatus.WATCH
            if watch
            else MonitorStatus.NORMAL
        )
        return HorizonKpi(
            holding_days=holding_days,
            status=status,
            data_state="READY",
            recent=recent,
            baseline=baseline,
            win_rate_delta=win_delta,
            excess_return_delta=excess_delta,
            reasons=reasons,
        )

    @staticmethod
    def _metrics(summary) -> KpiMetrics:
        return KpiMetrics(
            run_count=summary.run_count,
            sample_count=summary.total_count,
            win_rate=summary.win_rate,
            average_net_return=summary.average_net_return,
            average_benchmark_return=summary.average_benchmark_return,
            average_excess_return=summary.average_excess_return,
        )

    @staticmethod
    def _operation(records) -> OperationKpi:
        records = list(records)
        completed = sum(item.status == RunStatus.COMPLETED for item in records)
        partial = sum(item.status == RunStatus.PARTIAL for item in records)
        failed = sum(item.status == RunStatus.FAILED for item in records)
        completed_runs = completed + partial + failed
        return OperationKpi(
            run_count=len(records),
            completed_count=completed,
            partial_count=partial,
            failed_count=failed,
            failure_rate=(
                (partial + failed) / completed_runs if completed_runs else 0.0
            ),
        )

    @staticmethod
    def _data_quality(records) -> DataQualityKpi:
        records = list(records)
        total = sum(item.get("total_count", 0) for item in records)
        warnings = sum(item.get("warning_count", 0) for item in records)
        excluded = sum(item.get("excluded_count", 0) for item in records)
        return DataQualityKpi(
            run_count=len(records),
            total_count=total,
            valid_count=sum(item.get("valid_count", 0) for item in records),
            warning_count=warnings,
            excluded_count=excluded,
            warning_rate=warnings / total if total else 0.0,
            exclusion_rate=excluded / total if total else 0.0,
        )

    @staticmethod
    def _optional_delta(left, right):
        return left - right if left is not None and right is not None else None

    @staticmethod
    def _severity(status):
        return {
            MonitorStatus.NORMAL: 0,
            MonitorStatus.WATCH: 1,
            MonitorStatus.ALERT: 2,
        }[status]

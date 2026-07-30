from datetime import datetime
from uuid import uuid4

from config.constants import VERSION
from operation.model import OperationResult, RunRecord, RunStatus
from operation.report import generate_operation_markdown


class DailyOperationRunner:
    HORIZONS = (5, 10, 20, 40)

    def __init__(
        self,
        titan_runner,
        selected_validation_runner,
        observation_validation_runner,
        selection_repository,
        observation_repository,
        selected_validation_repository,
        observation_validation_repository,
        run_repository,
        report_repository,
        calendar,
        max_attempts: int = 2,
    ) -> None:
        self.titan_runner = titan_runner
        self.selected_validation_runner = selected_validation_runner
        self.observation_validation_runner = observation_validation_runner
        self.selection_repository = selection_repository
        self.observation_repository = observation_repository
        self.selected_validation_repository = selected_validation_repository
        self.observation_validation_repository = observation_validation_repository
        self.run_repository = run_repository
        self.report_repository = report_repository
        self.calendar = calendar
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")
        self.max_attempts = max_attempts

    def run(
        self,
        operation_date: datetime,
        top_n: int = 5,
        success_return: float = 0.03,
        force: bool = False,
    ) -> OperationResult:
        previous = self.run_repository.find(operation_date, VERSION)
        if previous is not None and previous.status in {
            RunStatus.COMPLETED,
            RunStatus.PARTIAL,
        } and not force:
            skipped = RunRecord(
                run_id=previous.run_id,
                operation_date=operation_date,
                strategy_version=VERSION,
                status=RunStatus.SKIPPED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                failures=["동일 기준일·전략 버전 실행이 이미 완료되었습니다."],
            )
            return OperationResult(skipped, generate_operation_markdown(skipped))

        record = RunRecord(
            run_id=f"{operation_date:%Y%m%dT%H%M%S}_{uuid4().hex[:8]}",
            operation_date=operation_date,
            strategy_version=VERSION,
            status=RunStatus.STARTED,
            started_at=datetime.now(),
            forced=force,
        )
        self.run_repository.save(record)

        for attempt in range(1, self.max_attempts + 1):
            try:
                selection = self.titan_runner.select(operation_date, top_n=top_n)
                record.selection_count = len(selection.selections)
                record.observation_count = len(selection.observations)
                break
            except Exception as error:
                if attempt == self.max_attempts:
                    record.failures.append(
                        f"선정 실패({attempt}회 시도): "
                        f"{type(error).__name__}: {error}"
                    )

        self._validate_due(
            "선정",
            self.selection_repository,
            self.selected_validation_repository,
            self.selected_validation_runner,
            operation_date,
            success_return,
            record,
        )
        self._validate_due(
            "관찰",
            self.observation_repository,
            self.observation_validation_repository,
            self.observation_validation_runner,
            operation_date,
            success_return,
            record,
        )
        fallback_reason = getattr(self.calendar, "last_fallback_reason", None)
        if fallback_reason:
            record.warnings.append(
                "KIS 휴장일 조회에 실패하여 캐시/평일 캘린더를 사용했습니다: "
                f"{fallback_reason}"
            )

        record.completed_at = datetime.now()
        if record.failures:
            record.status = (
                RunStatus.FAILED
                if record.selection_count == 0 and record.validation_count == 0
                else RunStatus.PARTIAL
            )
        else:
            record.status = RunStatus.COMPLETED
        run_path = self.run_repository.save(record)
        self.run_repository.save_failures(record)
        report = generate_operation_markdown(record)
        report_path = self.report_repository.save(
            f"operation_{record.run_id}.md",
            report,
        )
        return OperationResult(record, report, run_path, report_path)

    def _validate_due(
        self,
        label,
        snapshot_repository,
        validation_repository,
        validation_runner,
        as_of,
        success_return,
        record,
    ) -> None:
        for selected_at in snapshot_repository.list_dates():
            elapsed = self.calendar.session_count(selected_at, as_of)
            for horizon in self.HORIZONS:
                if elapsed < horizon:
                    continue
                if validation_repository.exists(selected_at, horizon):
                    record.skipped_validation_count += 1
                    continue
                for attempt in range(1, self.max_attempts + 1):
                    try:
                        validation_runner.run_horizons(
                            selected_at=selected_at,
                            as_of=as_of,
                            holding_days=[horizon],
                            success_return=success_return,
                        )
                        record.validation_count += 1
                        break
                    except Exception as error:
                        if attempt == self.max_attempts:
                            record.failures.append(
                                f"{label} {selected_at.date()} {horizon}일 검증 실패"
                                f"({attempt}회 시도): "
                                f"{type(error).__name__}: {error}"
                            )

from operation.model import RunRecord


def generate_operation_markdown(record: RunRecord) -> str:
    warnings = (
        "\n".join(f"- {warning}" for warning in record.warnings)
        if record.warnings
        else "- 없음"
    )
    failures = (
        "\n".join(f"- {failure}" for failure in record.failures)
        if record.failures
        else "- 없음"
    )
    return (
        "# TITAN Daily Operation Report\n\n"
        f"- 실행 ID: {record.run_id}\n"
        f"- 기준일: {record.operation_date.isoformat()}\n"
        f"- 전략 버전: {record.strategy_version}\n"
        f"- 상태: {record.status.value}\n"
        f"- 선정 종목: {record.selection_count}\n"
        f"- 관찰 종목: {record.observation_count}\n"
        f"- 신규 검증: {record.validation_count}\n"
        f"- 중복 검증 생략: {record.skipped_validation_count}\n"
        f"- 강제 실행: {'예' if record.forced else '아니오'}\n\n"
        "## 경고\n\n"
        f"{warnings}\n\n"
        "## 실패 내역\n\n"
        f"{failures}\n"
    )

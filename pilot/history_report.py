def generate_pilot_readiness_markdown(readiness) -> str:
    lines = [
        "# TITAN KIS Pilot Readiness",
        "",
        f"- 상태: **{readiness.status}**",
        f"- 관찰 거래일: {readiness.observed_days}/{readiness.required_days}",
        f"- 통과 거래일: {readiness.passing_days}",
        f"- 최근 연속 통과: {readiness.consecutive_passing_days}",
        "",
        "## 거래일별 보수적 집계",
        "",
        "| 날짜 | 상태 | 실행 수 | 최소 성공률 | 최대 재시도율 | 최대 제외율 | 오류 유형 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for item in readiness.days:
        errors = ", ".join(
            f"{key}:{value}" for key, value in item.error_types.items()
        ) or "-"
        lines.append(
            f"| {item.date.isoformat()} | {item.status} | {item.run_count} | "
            f"{item.minimum_api_success_rate:.2%} | "
            f"{item.maximum_retry_rate:.2%} | "
            f"{item.maximum_exclusion_rate:.2%} | {errors} |"
        )
    lines.extend(["", "## 미충족 사유", ""])
    lines.extend(f"- {reason}" for reason in readiness.reasons)
    if not readiness.reasons:
        lines.append("- 없음")
    return "\n".join(lines) + "\n"

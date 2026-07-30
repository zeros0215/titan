from monitoring.model import MonitoringSnapshot


def generate_monitoring_markdown(snapshot: MonitoringSnapshot) -> str:
    def percent(value):
        return "N/A" if value is None else f"{value:.2%}"

    lines = [
        "# TITAN KPI Monitoring Report",
        "",
        f"- 생성 시각: {snapshot.generated_at.isoformat()}",
        f"- 종합 상태: **{snapshot.status.value}**",
        f"- 판정 데이터: {snapshot.data_state}",
        f"- 누적 표본: {snapshot.cumulative.sample_count}",
        f"- 최근 표본: {snapshot.recent.sample_count}",
        f"- 누적 순수익률: {percent(snapshot.cumulative.average_net_return)}",
        f"- 누적 초과수익률: {percent(snapshot.cumulative.average_excess_return)}",
        "",
        "## 보유기간별 상태",
        "",
        "| 기간 | 상태 | 데이터 | 최근 표본 | 기준 표본 | 최근 승률 | 승률 변화 | 최근 초과수익 | 초과수익 변화 |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in snapshot.horizons:
        lines.append(
            f"| {item.holding_days}일 | {item.status.value} | {item.data_state} | "
            f"{item.recent.sample_count} | {item.baseline.sample_count} | "
            f"{percent(item.recent.win_rate)} | {percent(item.win_rate_delta)} | "
            f"{percent(item.recent.average_excess_return)} | "
            f"{percent(item.excess_return_delta)} |"
        )

    operation = snapshot.operation
    lines.extend([
        "",
        "## 운영 안정성",
        "",
        f"- 실행 기록: {operation.run_count}",
        f"- 완료: {operation.completed_count}",
        f"- 부분 완료: {operation.partial_count}",
        f"- 실패: {operation.failed_count}",
        f"- 부분 완료·실패율: {operation.failure_rate:.2%}",
        "",
        "## 데이터 품질",
        "",
        f"- 품질 검사 실행: {snapshot.data_quality.run_count}",
        f"- 검사 종목: {snapshot.data_quality.total_count}",
        f"- 유효 종목: {snapshot.data_quality.valid_count}",
        f"- 경고 종목: {snapshot.data_quality.warning_count}",
        f"- 제외 종목: {snapshot.data_quality.excluded_count}",
        f"- 경고율: {snapshot.data_quality.warning_rate:.2%}",
        f"- 제외율: {snapshot.data_quality.exclusion_rate:.2%}",
        "",
        "## 판정 근거",
        "",
    ])
    lines.extend(f"- {reason}" for reason in snapshot.reasons)
    if not snapshot.reasons:
        lines.append("- 이상 징후 없음")

    lines.extend(["", "## Context KPI", ""])
    lines.append("| Context | 표본 | 승률 | 순수익률 | 초과수익률 |")
    lines.append("|---|---:|---:|---:|---:|")
    for item in snapshot.context_rows:
        lines.append(
            f"| {item.regime.value} | {item.total_count} | "
            f"{item.win_rate:.2%} | {item.average_return:.2%} | "
            f"{percent(item.average_excess_return)} |"
        )

    lines.extend(["", "## Feature KPI", ""])
    lines.append("| Feature | 표본 | 승률 | 순수익률 | 초과수익률 |")
    lines.append("|---|---:|---:|---:|---:|")
    for item in snapshot.feature_rows:
        lines.append(
            f"| {item.feature_type.value} | {item.total_count} | "
            f"{item.win_rate:.2%} | {item.average_return:.2%} | "
            f"{percent(item.average_excess_return)} |"
        )

    lines.extend(["", "## 점수 구간 KPI", ""])
    lines.append("| 점수 | 표본 | 승률 | 순수익률 | 초과수익률 |")
    lines.append("|---|---:|---:|---:|---:|")
    for item in snapshot.score_band_rows:
        lines.append(
            f"| {item.label} | {item.total_count} | {item.win_rate:.2%} | "
            f"{item.average_return:.2%} | "
            f"{percent(item.average_excess_return)} |"
        )
    return "\n".join(lines) + "\n"

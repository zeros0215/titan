from strategy_gate.model import StrategyCandidate


def generate_strategy_gate_markdown(candidate: StrategyCandidate) -> str:
    lines = [
        "# TITAN Strategy Change Gate",
        "",
        f"- 후보 버전: {candidate.candidate_version}",
        f"- 기준 버전: {candidate.base_version}",
        f"- 상태: **{candidate.status.value}**",
        f"- 설정 해시: `{candidate.config_hash}`",
        f"- 설명: {candidate.description}",
        f"- 승인자: {candidate.approved_by or '미승인'}",
        "",
        "## Gate checks",
        "",
        "| 항목 | 결과 | 실제값 |",
        "|---|---|---|",
    ]
    for check in candidate.gate_checks:
        lines.append(
            f"| {check['name']} | "
            f"{'PASS' if check['passed'] else 'FAIL'} | "
            f"{check.get('actual', '')} |"
        )
    if not candidate.gate_checks:
        lines.append("| 아직 평가되지 않음 | - | - |")

    comparison = candidate.comparison or {}
    lines.extend([
        "",
        "## 성과 변화",
        "",
        f"- 순수익률 변화: {comparison.get('net_return_delta', 'N/A')}",
        f"- 초과수익률 변화: {comparison.get('excess_return_delta', 'N/A')}",
        f"- 승률 변화: {comparison.get('win_rate_delta', 'N/A')}",
        f"- 개선 폴드 비율: {comparison.get('positive_fold_ratio', 'N/A')}",
        "",
        "## 감사 이력",
        "",
    ])
    lines.extend(
        f"- {event.occurred_at.isoformat()} | {event.action} | "
        f"{event.actor} | {event.details} | hash={event.event_hash[:12]}"
        for event in candidate.audit_events
    )
    lines.extend([
        "",
        "> 승인 상태는 배포 허가 증거이며 현재 실행 전략을 자동 변경하지 않습니다.",
    ])
    return "\n".join(lines) + "\n"

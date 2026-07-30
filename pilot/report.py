def generate_kis_pilot_markdown(result) -> str:
    lines = [
        "# TITAN KIS Read-Only Pilot",
        "",
        f"- 실행 ID: {result.run_id}",
        f"- 기준일: {result.as_of.isoformat()}",
        f"- 상태: **{result.status}**",
        f"- 실행시간: {result.duration_seconds:.2f}초",
        f"- 유니버스: {result.universe_count}",
        f"- 분석 성공: {result.analyzed_count}",
        f"- 선정: {result.selection_count}",
        f"- 관찰: {result.observation_count}",
        f"- 품질 제외: {result.excluded_count} ({result.exclusion_rate:.2%})",
        f"- API 실제 시도: {result.request_count}",
        f"- API 성공: {result.success_count}",
        f"- API 재시도: {result.retry_count}",
        f"- API 재시도율: {result.retry_rate:.2%}",
        f"- API 실패: {result.failure_count}",
        f"- 서버 오류 응답: {result.server_error_count}",
        f"- 전송 오류: {result.transport_error_count}",
        f"- API 성공률: {result.api_success_rate:.2%}",
        f"- 주문 요청: {result.order_request_count}",
        "",
        "## 종목별 조회 실패",
        "",
    ]
    if result.fetch_failures:
        lines.extend(
            f"- {code}: {message}"
            for code, message in sorted(result.fetch_failures.items())
        )
    else:
        lines.append("- 없음")
    lines.extend(["", "## 판정 근거", ""])
    lines.extend(f"- {reason}" for reason in result.reasons)
    if not result.reasons:
        lines.append("- 모든 파일럿 기준 충족")
    _append_candidates(lines, "매수 선정 종목", result.selected_candidates)
    _append_candidates(lines, "관찰 종목", result.observation_candidates)
    return "\n".join(lines) + "\n"


def _append_candidates(lines, title, candidates):
    lines.extend(["", f"## {title}", ""])
    if not candidates:
        lines.append("- 없음")
        return
    lines.extend([
        "| 순위 | 코드 | 종목명 | 총점 | 추세 | 모멘텀 | 거래량 | 가격 | 위험 | Context | 시장 | 강도 |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ])
    for item in candidates:
        strength = item.get("market_strength")
        strength_text = (
            f"{strength:.2%}" if strength is not None else "N/A"
        )
        lines.append(
            f"| {item['rank']} | {item['code']} | {item['name']} | "
            f"{item['total_score']} | {item['trend_score']} | "
            f"{item['momentum_score']} | {item['volume_score']} | "
            f"{item['price_action_score']} | {item['risk_score']} | "
            f"{item['context_score']} | {item['market_trend']} | "
            f"{strength_text} |"
        )
    for item in candidates:
        lines.extend([
            "",
            f"### {item['code']} {item['name']} ({item['total_score']}점)",
            "",
            "- 긍정: " + (
                ", ".join(item.get("positive_factors", [])) or "없음"
            ),
            "- 부정: " + (
                ", ".join(item.get("negative_factors", [])) or "없음"
            ),
        ])

def generate_universe_history_markdown(manifest, validation) -> str:
    lines = [
        "# TITAN Point-in-Time Universe Compilation",
        "",
        f"- COMPLETE: **{manifest['point_in_time_complete']}**",
        f"- 커버리지: {manifest['coverage_start']} ~ {manifest['coverage_end']}",
        f"- 원천: {manifest['source_name']} ({manifest['source_type']})",
        f"- 원천 완전성 선언: {manifest['source_complete']}",
        f"- 레코드: {validation.record_count}",
        f"- 고유 종목: {validation.stock_count}",
        f"- 오류: {len(validation.errors)}",
        f"- 경고: {len(validation.warnings)}",
        f"- 입력 SHA-256: `{manifest['input_sha256']}`",
        "",
        "## 검증 이슈",
        "",
    ]
    if not validation.issues:
        lines.append("- 없음")
    else:
        lines.extend(
            f"- [{item.severity.value}] {item.code}"
            f"{f' ({item.stock_code})' if item.stock_code else ''}: "
            f"{item.message}"
            for item in validation.issues
        )
    lines.extend([
        "",
        "> COMPLETE는 해당 커버리지 범위에만 적용됩니다. "
        "컴파일 결과는 검토 후 운영 리소스로 별도 승격해야 합니다.",
    ])
    return "\n".join(lines) + "\n"

"""Diagnostics for the frozen S80 morning-entry filter."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import mean, median, stdev


CONDITIONS = ("gap_ok", "range_ok", "above_vwap", "recent_lows_stable")


def _summary(rows: list[dict], return_field: str = "baseline_net_return") -> dict:
    values = [float(row[return_field]) for row in rows if row.get(return_field) is not None]
    if not values:
        return {
            "trades": 0, "win_rate": None, "average_return": None,
            "median_return": None, "mean_95_ci": [None, None],
        }
    average = mean(values)
    margin = 0.0 if len(values) < 2 else 1.96 * stdev(values) / math.sqrt(len(values))
    return {
        "trades": len(values),
        "win_rate": sum(value > 0 for value in values) / len(values),
        "average_return": average,
        "median_return": median(values),
        "mean_95_ci": [average - margin, average + margin],
    }


def _market_lookup(universe_dir: Path) -> dict[str, str]:
    result = {}
    for market in ("kospi", "kosdaq"):
        with (universe_dir / f"{market}.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                result[str(row["code"]).zfill(6)] = row["market"]
    return result


def analyze_s80_morning_filter(backtest_path: Path, universe_dir: Path) -> dict:
    """Measure filter lift without changing the frozen condition thresholds.

    Ablations use next-open returns because the stored backtest only computes a
    10:00 exit path for rows that passed every condition.  The fully qualified
    group additionally reports its actual stored 10:00-entry result.
    """
    payload = json.loads(backtest_path.read_text(encoding="utf-8"))
    market_by_code = _market_lookup(universe_dir)
    available = list(payload.get("trades", []))
    eligible = [row for row in available if row.get("baseline_eligible")]
    qualified = [row for row in eligible if row.get("qualified")]

    condition_pass_counts = {
        condition: sum(bool(row.get("conditions", {}).get(condition)) for row in eligible)
        for condition in CONDITIONS
    }
    drop_one = {}
    for removed in CONDITIONS:
        required = [condition for condition in CONDITIONS if condition != removed]
        rows = [
            row for row in eligible
            if all(row.get("conditions", {}).get(condition) for condition in required)
        ]
        drop_one[removed] = _summary(rows)

    by_month = {}
    for month in sorted({row["selection_date"][:7] for row in eligible}):
        by_month[month] = _summary([
            row for row in eligible if row["selection_date"].startswith(month)
        ])

    by_market = {}
    for market in ("KOSPI", "KOSDAQ"):
        rows = [row for row in eligible if market_by_code.get(str(row["code"]).zfill(6)) == market]
        selected = [row for row in qualified if market_by_code.get(str(row["code"]).zfill(6)) == market]
        by_market[market] = {
            "baseline": _summary(rows),
            "qualified_next_open": _summary(selected),
            "qualified_1000": _summary(selected, "stable_net_return"),
        }

    by_score = {}
    for label, lower, upper in (("80-84", 80, 84), ("85-89", 85, 89), ("90+", 90, 10_000)):
        rows = [row for row in eligible if lower <= int(row["score"]) <= upper]
        by_score[label] = _summary(rows)

    rejected = [row for row in eligible if not row.get("qualified")]
    result = {
        "schema_version": 1,
        "status": "RESEARCH_ONLY",
        "strategy_version": payload.get("strategy_version"),
        "period": {
            "first_selection_date": min(row["selection_date"] for row in available),
            "last_selection_date": max(row["selection_date"] for row in available),
        },
        "counts": {
            "manifest_targets": len(available) + int(payload.get("missing_count", 0)),
            "available": len(available),
            "next_open_eligible": len(eligible),
            "fully_qualified": len(qualified),
            "eligible_rejected": len(rejected),
        },
        "baseline_all": _summary(eligible),
        "qualified_next_open": _summary(qualified),
        "qualified_1000": _summary(qualified, "stable_net_return"),
        "rejected_next_open": _summary(rejected),
        "condition_pass_counts": condition_pass_counts,
        "condition_failure_patterns": dict(Counter(
            "+".join(condition for condition in CONDITIONS if not row.get("conditions", {}).get(condition))
            or "NONE"
            for row in eligible
        )),
        "drop_one_condition": drop_one,
        "by_month": by_month,
        "by_market": by_market,
        "by_score": by_score,
        "notes": [
            "Ablations use next-open returns; 10:00 returns only exist for the fully qualified group.",
            "The gap ablation is not identifiable because baseline eligibility already enforces the same 3% gap limit.",
            "Confidence intervals are normal-approximation intervals for the mean and are descriptive only.",
            "No score weights or frozen condition thresholds were changed.",
        ],
    }
    return result


def save_s80_morning_filter_report(backtest_path: Path, universe_dir: Path, output_dir: Path) -> dict:
    result = analyze_s80_morning_filter(backtest_path, universe_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "s80_morning_ablation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "s80_morning_ablation.md").write_text(
        _markdown(result), encoding="utf-8"
    )
    return result


def save_s80_validation_progress(backtest_paths: list[Path], output_dir: Path) -> dict:
    """Combine frozen-rule samples and report progress toward review gates."""
    rows_by_key = {}
    sources = []
    for path in backtest_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        qualified = [
            row for row in payload.get("trades", [])
            if row.get("baseline_eligible") and row.get("qualified")
            and row.get("stable_net_return") is not None
        ]
        for row in qualified:
            key = (row["selection_date"], str(row["code"]).zfill(6))
            rows_by_key[key] = row
        sources.append({
            "path": str(path),
            "available": int(payload.get("available_count", len(payload.get("trades", [])))),
            "missing": int(payload.get("missing_count", 0)),
            "qualified": len(qualified),
        })
    rows = list(rows_by_key.values())
    summary = _summary(rows, "stable_net_return")
    count = summary["trades"]
    if count >= 50:
        status, next_target = "FIRST_REVIEW_READY", None
    elif count >= 30:
        status, next_target = "INTERIM_REVIEW", 50
    else:
        status, next_target = "COLLECTING", 30
    result = {
        "schema_version": 1,
        "status": status,
        "strategy_policy": "FROZEN_S80_MORNING_FILTER",
        "sample_count": count,
        "interim_target": 30,
        "first_review_target": 50,
        "next_target": next_target,
        "remaining_to_next_target": 0 if next_target is None else next_target - count,
        "summary": summary,
        "sources": sources,
        "operational_orders": 0,
        "warning": (
            "These are historical research samples, not live forward-closed trades. "
            "Missing intraday bars may create selection bias."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "s80_validation_progress.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# S80 동결 규칙 검증 진행률", "",
        "> 과거 연구 표본의 누적 현황입니다. 실시간 전진검증 완료 거래와 동일시하지 않습니다.", "",
        f"- 상태: **{status}**",
        f"- 누적 표본: **{count}건**",
        f"- 30건 중간점검까지: **{max(0, 30 - count)}건**",
        f"- 50건 1차 판정까지: **{max(0, 50 - count)}건**",
        f"- 승률: {_pct(summary['win_rate'])}",
        f"- 평균 순수익: {_pct(summary['average_return'])}",
        f"- 평균 95% 기술 구간: {_pct(summary['mean_95_ci'][0])} ~ {_pct(summary['mean_95_ci'][1])}",
        "", "## 입력 자료", "", "|파일|사용 가능|누락|조건 통과|", "|---|---:|---:|---:|",
    ]
    for source in sources:
        lines.append(
            f"|{source['path']}|{source['available']}|{source['missing']}|{source['qualified']}|"
        )
    lines.extend([
        "", "## 판정 규칙", "",
        "- 30건: 중간점검만 수행하며 규칙을 자동 변경하지 않습니다.",
        "- 50건: 평균 순수익·시장 대비 초과수익·최대 낙폭을 함께 검토합니다.",
        "- 현재 자료에는 시장 대비 초과수익과 포트폴리오 최대 낙폭이 없어 최종 승격을 판정하지 않습니다.",
        "- 분봉 누락으로 인한 선택 편향 가능성을 유지합니다.", "",
    ])
    (output_dir / "s80_validation_progress.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    return result


def save_s80_entry_layer_comparison(
    backtest_paths: list[Path], output_dir: Path
) -> dict:
    """Compare the daily S80 core with strict and relaxed 10:00 overlays."""
    strategies = {
        "S80_OPEN": {},
        "S80_10H": {},
        "S80_10L": {},
    }
    sources = []
    for path in backtest_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        available = payload.get("trades", [])
        for row in available:
            if not row.get("baseline_eligible"):
                continue
            key = (row["selection_date"], str(row["code"]).zfill(6))
            strategies["S80_OPEN"][key] = row.get("baseline_net_return")
            conditions = row.get("conditions", {})
            if row.get("qualified") and row.get("morning_net_return") is not None:
                strategies["S80_10H"][key] = row["morning_net_return"]
            if (
                all(conditions.get(name) for name in ("gap_ok", "range_ok", "above_vwap"))
                and row.get("morning_net_return") is not None
            ):
                strategies["S80_10L"][key] = row["morning_net_return"]
        sources.append({
            "path": str(path),
            "available": int(payload.get("available_count", len(available))),
            "missing": int(payload.get("missing_count", 0)),
        })

    summaries = {
        name: _summary([
            {"value": value} for value in values.values() if value is not None
        ], "value")
        for name, values in strategies.items()
    }
    result = {
        "schema_version": 1,
        "status": "RESEARCH_ONLY",
        "strategies": {
            "S80_OPEN": "next-session open; daily-data validation core",
            "S80_10H": "10:00 entry; all four frozen morning conditions",
            "S80_10L": "10:00 entry; recent_lows_stable omitted",
        },
        "summaries": summaries,
        "sources": sources,
        "limitations": [
            "S80_OPEN is the long-history core; the 10:00 overlays only use rows with intraday bars.",
            "Missing intraday bars can create selection bias in S80_10H and S80_10L.",
            "S80_10L was selected after inspecting historical ablations and requires forward validation.",
            "No operational rule or order behavior is changed by this report.",
        ],
        "operational_rule_changed": False,
        "operational_orders": 0,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "s80_entry_layers.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# S80 진입 계층 비교", "",
        "> 일봉 선정 본체와 10시 실행 오버레이를 분리한 연구 보고서입니다. 운영 규칙은 변경하지 않습니다.", "",
        "|전략|진입|거래|승률|평균 순수익|평균 95% 기술 구간|",
        "|---|---|---:|---:|---:|---:|",
    ]
    labels = {
        "S80_OPEN": "다음 거래일 시초가",
        "S80_10H": "10시·4조건",
        "S80_10L": "10시·최근 저점 조건 제외",
    }
    for name in ("S80_OPEN", "S80_10H", "S80_10L"):
        row = summaries[name]
        interval = f"{_pct(row['mean_95_ci'][0])} ~ {_pct(row['mean_95_ci'][1])}"
        lines.append(
            f"|{name}|{labels[name]}|{row['trades']}|{_pct(row['win_rate'])}|"
            f"{_pct(row['average_return'])}|{interval}|"
        )
    lines += [
        "", "## 판정 원칙", "",
        "- S80_OPEN만 장기 일봉 검증의 본체로 사용합니다.",
        "- S80_10H와 S80_10L은 분봉 보유 기간의 실행 오버레이로만 비교합니다.",
        "- S80_10L은 과거 결과를 보고 고른 후보이므로 신규 전진 표본 전에는 승격하지 않습니다.",
        "- 이 보고서는 운영 조건이나 주문을 변경하지 않습니다.", "",
    ]
    (output_dir / "s80_entry_layers.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    return result


def _pct(value) -> str:
    return "—" if value is None else f"{value:.2%}"


def _markdown(result: dict) -> str:
    lines = [
        "# S80 오전 진입 필터 기여도 분석", "",
        "> 연구 전용. 기존 점수와 오전 조건의 임계값은 변경하지 않았습니다.", "",
        f"- 기간: {result['period']['first_selection_date']} ~ {result['period']['last_selection_date']}",
        f"- 사용 가능/시초가 적격/전체 조건 통과: {result['counts']['available']} / "
        f"{result['counts']['next_open_eligible']} / {result['counts']['fully_qualified']}", "",
        "## 핵심 비교", "",
        "|집단|거래|승률|평균|중앙값|평균 95% 구간|", "|---|---:|---:|---:|---:|---:|",
    ]
    for label, key in (
        ("S80 전체·다음 시초가", "baseline_all"),
        ("4조건 통과·다음 시초가", "qualified_next_open"),
        ("4조건 통과·10시", "qualified_1000"),
        ("4조건 탈락·다음 시초가", "rejected_next_open"),
    ):
        row = result[key]
        interval = f"{_pct(row['mean_95_ci'][0])} ~ {_pct(row['mean_95_ci'][1])}"
        lines.append(
            f"|{label}|{row['trades']}|{_pct(row['win_rate'])}|{_pct(row['average_return'])}|"
            f"{_pct(row['median_return'])}|{interval}|"
        )
    lines.extend(["", "## 조건 하나 제거", "", "|제거 조건|거래|승률|평균|", "|---|---:|---:|---:|"])
    for condition in CONDITIONS:
        row = result["drop_one_condition"][condition]
        lines.append(f"|{condition}|{row['trades']}|{_pct(row['win_rate'])}|{_pct(row['average_return'])}|")
    lines.extend(["", "## 조건별 단독 통과 수", "", "|조건|통과|", "|---|---:|"])
    for condition in CONDITIONS:
        lines.append(f"|{condition}|{result['condition_pass_counts'][condition]}|")
    lines.extend(["", "## 점수대별 S80 전체", "", "|점수|거래|승률|평균|", "|---|---:|---:|---:|"])
    for score, row in result["by_score"].items():
        lines.append(f"|{score}|{row['trades']}|{_pct(row['win_rate'])}|{_pct(row['average_return'])}|")
    lines.extend(["", "## 시장별 S80 전체", "", "|시장|거래|승률|평균|조건 통과|10시 평균|", "|---|---:|---:|---:|---:|---:|"])
    for market, values in result["by_market"].items():
        base, qualified = values["baseline"], values["qualified_1000"]
        lines.append(
            f"|{market}|{base['trades']}|{_pct(base['win_rate'])}|{_pct(base['average_return'])}|"
            f"{qualified['trades']}|{_pct(qualified['average_return'])}|"
        )
    lines.extend(["", "## 월별 S80 전체", "", "|월|거래|승률|평균|", "|---|---:|---:|---:|"])
    for month, row in result["by_month"].items():
        lines.append(f"|{month}|{row['trades']}|{_pct(row['win_rate'])}|{_pct(row['average_return'])}|")
    lines.extend(["", "## 해석 주의", "", "- 조건 제거 비교는 모든 사례에 저장된 다음 시초가 수익을 사용합니다.", "- 10시 수익은 네 조건을 모두 통과한 사례에만 저장되어 있습니다.", "- 이 결과는 포트폴리오 수익률이나 독립기간 전진검증 결과가 아닙니다.", ""])
    lines.insert(-1, "- 시초가 적격 자체가 ±3% 갭 제한이므로 `gap_ok` 제거 효과는 이 자료에서 식별할 수 없습니다.")
    return "\n".join(lines)

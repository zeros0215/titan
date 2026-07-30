import hashlib
import json
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from config.constants import VERSION
from config.observation_policy import ObservationPolicy
from config.selection_criteria import (
    CONTEXT_MAX_SCORE,
    MOMENTUM_FEATURE_SCORES,
    MOMENTUM_MAX_SCORE,
    PRICE_ACTION_FEATURE_SCORES,
    PRICE_ACTION_MAX_SCORE,
    RISK_FEATURE_SCORES,
    RISK_MAX_SCORE,
    SELECTION_CRITERIA,
    TREND_FEATURE_SCORES,
    TREND_MAX_SCORE,
    VOLUME_FEATURE_SCORES,
    VOLUME_MAX_SCORE,
)
from config.transaction_costs import transaction_cost_policy_from_env


def _weights(values: dict) -> dict[str, int]:
    return {key.name: value for key, value in sorted(
        values.items(), key=lambda item: item[0].name
    )}


def build_v1_spec() -> dict:
    observation = ObservationPolicy()
    return {
        "schema_version": 1,
        "strategy_version": VERSION,
        "objective": (
            "시장 상황(Context)과 종목 특성(Feature)을 함께 분석하여 "
            "향후 상승 가능성이 높은 종목을 지속적으로 선별하고 검증한다."
        ),
        "selection": {
            "universe": {
                "ranking": "point_in_time_market_cap_desc",
                "market_cap_limit": 500,
                "minimum_daily_trading_value_krw": 5_000_000_000,
                "excluded": [
                    "managed_issues",
                    "spacs",
                    "preferred_shares",
                    "quality_quarantine_intervals",
                ],
            },
            "criteria": asdict(SELECTION_CRITERIA),
            "top_n": 5,
            "ranking": (
                "decision_desc_then_normalized_score_desc_then_"
                "trading_value_desc_then_code_asc"
            ),
        },
        "scoring": {
            "category_caps": {
                "trend": TREND_MAX_SCORE,
                "momentum": MOMENTUM_MAX_SCORE,
                "volume": VOLUME_MAX_SCORE,
                "price_action": PRICE_ACTION_MAX_SCORE,
                "risk": RISK_MAX_SCORE,
                "context": CONTEXT_MAX_SCORE,
            },
            "feature_weights": {
                "trend": _weights(TREND_FEATURE_SCORES),
                "momentum": _weights(MOMENTUM_FEATURE_SCORES),
                "volume": _weights(VOLUME_FEATURE_SCORES),
                "price_action": _weights(PRICE_ACTION_FEATURE_SCORES),
                "risk": _weights(RISK_FEATURE_SCORES),
            },
            "price_action_aggregation": "strongest_signal_only",
        },
        "observation_cohort": asdict(observation),
        "backtest": {
            "holding_days": [5, 10, 20, 40],
            "primary_holding_days": 20,
            "selection_interval_months": 1,
            "success_return": 0.03,
            "walk_forward": "expanding_year_out_of_sample",
            "entry": "next_trading_session_open",
            "exit": "20th_trading_session_close",
            "intraday_execution": "unsupported_without_intraday_candles",
            "transaction_costs": asdict(transaction_cost_policy_from_env()),
            "benchmarks": [],
            "official_benchmark_status": "not_available",
        },
        "data_requirements": {
            "point_in_time_universe": True,
            "adjusted_prices": True,
            "delisted_stocks": True,
            "minimum_history_years": 3,
            "minimum_universe_size": 100,
        },
    }


def spec_hash(spec: dict) -> str:
    canonical = json.dumps(
        spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def freeze_v1(path: Path) -> tuple[dict, str]:
    spec = build_v1_spec()
    digest = spec_hash(spec)
    payload = {
        **spec,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": digest,
    }
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing_spec = {
            key: value for key, value in existing.items()
            if key not in {"frozen_at", "config_sha256"}
        }
        if spec_hash(existing_spec) != digest:
            raise ValueError("existing frozen V1 specification differs from code")
        return existing, digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload, digest


@dataclass(slots=True, frozen=True)
class PreflightResult:
    status: str
    checks: list[tuple[str, bool, str]]


def backtest_preflight(
    spec_path: Path,
    universe_manifest_path: Path,
    stocks_path: Path,
    market_data_dir: Path,
) -> PreflightResult:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    embedded_hash = spec.pop("config_sha256")
    spec.pop("frozen_at", None)
    checks = []
    checks.append((
        "frozen_strategy_hash",
        spec_hash(spec) == embedded_hash,
        embedded_hash,
    ))
    manifest = json.loads(universe_manifest_path.read_text(encoding="utf-8"))
    checks.append((
        "point_in_time_universe",
        manifest.get("point_in_time_complete") is True,
        str(manifest.get("notes", "")),
    ))
    if stocks_path.is_dir():
        stock_codes = set()
        for csv_path in (stocks_path / "kospi.csv", stocks_path / "kosdaq.csv"):
            with csv_path.open(encoding="utf-8") as stock_file:
                stock_codes.update(
                    row["code"] for row in csv.DictReader(stock_file)
                )
        stock_count = len(stock_codes)
    else:
        with stocks_path.open(encoding="utf-8") as stock_file:
            stock_count = max(sum(1 for _ in stock_file) - 1, 0)
    minimum = spec["data_requirements"]["minimum_universe_size"]
    checks.append((
        "minimum_universe_size",
        stock_count >= minimum,
        f"{stock_count}/{minimum}",
    ))
    files = (
        [
            path
            for path in market_data_dir.glob("*.json")
            if path.stem.isalnum() and len(path.stem) == 6
        ]
        if market_data_dir.exists()
        else []
    )
    checks.append((
        "market_data_coverage",
        len(files) >= stock_count and stock_count > 0,
        f"{len(files)}/{stock_count} stock files",
    ))
    required_years = spec["data_requirements"]["minimum_history_years"]
    price_manifest_path = market_data_dir / "price_history_manifest.json"
    price_manifest = (
        json.loads(price_manifest_path.read_text(encoding="utf-8"))
        if price_manifest_path.exists()
        else None
    )
    coverage_days = []
    adjusted_flags = []
    if price_manifest is None:
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            candles = payload.get("candles", [])
            if candles:
                first = datetime.fromisoformat(candles[0]["date"])
                last = datetime.fromisoformat(candles[-1]["date"])
                coverage_days.append((last - first).days)
            adjusted_flags.append(payload.get("adjusted_prices") is True)
    minimum_days = required_years * 365
    if price_manifest is not None:
        first = datetime.fromisoformat(price_manifest["coverage_start"])
        last = datetime.fromisoformat(price_manifest["coverage_end"])
        history_days = (last - first).days
        coverage_days.append(history_days)
        history_detail = (
            f"dataset={history_days} days, required={minimum_days} days"
        )
    else:
        history_days = min(coverage_days, default=0)
        history_detail = (
            f"shortest={history_days} days, required={minimum_days} days"
        )
    checks.append((
        "minimum_price_history",
        bool(coverage_days) and history_days >= minimum_days,
        history_detail,
    ))
    if price_manifest is not None:
        adjusted_flags.append(price_manifest.get("adjusted_prices") is True)
    checks.append((
        "adjusted_price_evidence",
        bool(adjusted_flags) and all(adjusted_flags),
        f"verified={sum(adjusted_flags)}/{len(adjusted_flags)} files",
    ))
    costs = spec["backtest"]["transaction_costs"]
    total_cost = sum(float(value) for value in costs.values())
    checks.append((
        "non_zero_transaction_costs",
        total_cost > 0,
        f"round-trip assumption={total_cost:.4%}",
    ))
    return PreflightResult(
        status="READY" if all(item[1] for item in checks) else "BLOCKED",
        checks=checks,
    )


def preflight_markdown(result: PreflightResult) -> str:
    lines = [
        "# TITAN V1 Backtest Preflight",
        "",
        f"- 상태: **{result.status}**",
        "",
        "| 검사 | 결과 | 근거 |",
        "|---|---|---|",
    ]
    for name, passed, detail in result.checks:
        lines.append(f"| {name} | {'PASS' if passed else 'FAIL'} | {detail} |")
    lines.extend([
        "",
        "FAIL 항목이 있으면 백테스트 결과는 정식 성과 근거로 사용하지 않는다.",
        "",
    ])
    return "\n".join(lines)

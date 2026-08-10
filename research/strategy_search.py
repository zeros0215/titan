"""Bounded candidate generation and out-of-sample result ranking."""

from __future__ import annotations

from dataclasses import asdict
from itertools import product
import json
import math
from pathlib import Path
import statistics

from config.selection_criteria import SelectionCriteria
from config.strategy_profiles import V1_3_S80_N7_TP5_SL10_CANDIDATE

REPRESENTATIVE_IDS = (
    "s80-m60-mom10-t30-r15",
    "s78-m55-mom12-t35-r10",
    "s82-m65-mom8-t25-r20",
    "s80-m60-mom10-t35-r10",
    "s80-m60-mom10-t25-r20",
)


def generate_bounded_candidates(
    baseline: SelectionCriteria | None = None,
    minimum_scores: tuple[int, ...] = (78, 80, 82),
    market_strengths: tuple[float, ...] = (0.55, 0.60, 0.65),
    momentum_caps: tuple[float, ...] = (8.0, 10.0, 12.0),
    weight_profiles: tuple[tuple[int, int], ...] = (
        (30, 15), (35, 10), (25, 20),
    ),
) -> list[dict]:
    """Generate an auditable grid without changing scoring weights."""
    baseline = baseline or V1_3_S80_N7_TP5_SL10_CANDIDATE.criteria
    base = asdict(baseline)
    candidates = []
    for score, strength, momentum, weights in product(
        minimum_scores, market_strengths, momentum_caps, weight_profiles,
    ):
        trend_weight, risk_weight = weights
        config = {
            **base,
            "minimum_score": score,
            "minimum_market_strength": strength,
            "maximum_momentum_5d": momentum,
            "trend_weight": trend_weight,
            "risk_weight": risk_weight,
        }
        candidates.append({
            "research_id": (
                f"s{score}-m{int(strength * 100)}-mom{int(momentum)}"
                f"-t{trend_weight}-r{risk_weight}"
            ),
            "config": config,
        })
    return candidates


def save_candidate_grid(output_dir: Path, candidates: list[dict]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    for candidate in candidates:
        (output_dir / f"{candidate['research_id']}.json").write_text(
            json.dumps(candidate["config"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    manifest = output_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "operational_strategy_unchanged": True,
            "candidate_count": len(candidates),
            "candidates": [item["research_id"] for item in candidates],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def representative_candidates(candidates: list[dict]) -> list[dict]:
    by_id = {item["research_id"]: item for item in candidates}
    return [by_id[item] for item in REPRESENTATIVE_IDS if item in by_id]


def rank_walk_forward_results(
    paths: list[Path], minimum_trades: int = 100,
    objective_kind: str = "absolute",
    minimum_profitable_fold_ratio: float = 0.5,
) -> list[dict]:
    if objective_kind not in {"absolute", "excess"}:
        raise ValueError("objective_kind must be 'absolute' or 'excess'")
    rows = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            folds = payload["folds"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            continue
        fold_rows = []
        for fold in folds:
            count = int(fold.get("total_count") or 0)
            net = _finite(fold.get("average_net_return"))
            excess = _finite(fold.get("average_excess_return"))
            if count:
                fold_rows.append((count, net, excess))
        total = sum(item[0] for item in fold_rows)
        net = _weighted(fold_rows, 1)
        excess = _weighted(fold_rows, 2)
        objective_base = net if objective_kind == "absolute" else excess
        fold_values = [
            item[1] if objective_kind == "absolute" else item[2]
            for item in fold_rows
            if (item[1] if objective_kind == "absolute" else item[2]) is not None
        ]
        instability = statistics.pstdev(fold_values) if len(fold_values) > 1 else 0.0
        downside = max(0.0, -(min(fold_values) if fold_values else 0.0))
        maximum_drawdown = _maximum_drawdown(fold_values)
        objective = (
            objective_base - 0.5 * instability - 0.25 * downside
            - 0.5 * maximum_drawdown
            if objective_base is not None else -math.inf
        )
        profitable_fold_ratio = (
            sum(value > 0 for value in fold_values) / len(fold_values)
            if fold_values else None
        )
        eligible = (
            total >= minimum_trades
            and objective_base is not None
            and objective_base > 0
            and profitable_fold_ratio is not None
            and profitable_fold_ratio >= minimum_profitable_fold_ratio
        )
        metric_name = "NET_RETURN" if objective_kind == "absolute" else "EXCESS_RETURN"
        reason = (
            "ELIGIBLE" if eligible
            else "INSUFFICIENT_TRADES" if total < minimum_trades
            else f"MISSING_{metric_name}" if objective_base is None
            else f"NON_POSITIVE_{metric_name}" if objective_base <= 0
            else "INSUFFICIENT_PROFITABLE_FOLDS"
        )
        rows.append({
            "strategy_version": payload.get("strategy_version", path.stem),
            "path": str(path),
            "trades": total,
            "average_net_return": net,
            "average_excess_return": excess,
            "profitable_fold_ratio": profitable_fold_ratio,
            "fold_instability": instability if fold_values else None,
            "maximum_drawdown": maximum_drawdown if fold_values else None,
            "objective": objective,
            "eligible": eligible,
            "reason": reason,
            "objective_kind": objective_kind,
        })
    return sorted(
        rows,
        key=lambda row: (row["eligible"], row["objective"]),
        reverse=True,
    )


def render_ranking_markdown(rows: list[dict]) -> str:
    objective_kind = rows[0].get("objective_kind", "absolute") if rows else "absolute"
    objective_label = "cost-adjusted absolute net return" if objective_kind == "absolute" else "market-relative excess return"
    lines = [
        "# TITAN Strategy Research Ranking",
        "",
        "> Research only. This report cannot change or approve the operational strategy.",
        f"> Objective: {objective_label}; positive performance must occur in at least half of test folds.",
        "",
        "| Rank | Strategy | Trades | Net | Excess | Max drawdown | Profitable folds | Stability penalty | Gate |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for rank, row in enumerate(rows, 1):
        lines.append(
            f"| {rank} | {row['strategy_version']} | {row['trades']} | "
            f"{_percent(row['average_net_return'])} | "
            f"{_percent(row['average_excess_return'])} | "
            f"{_percent(row['maximum_drawdown'])} | "
            f"{_percent(row['profitable_fold_ratio'])} | "
            f"{_percent(row['fold_instability'])} | {row['reason']} |"
        )
    return "\n".join(lines) + "\n"


def _finite(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _weighted(rows: list[tuple], index: int) -> float | None:
    usable = [row for row in rows if row[index] is not None]
    total = sum(row[0] for row in usable)
    return sum(row[0] * row[index] for row in usable) / total if total else None


def _maximum_drawdown(returns: list[float]) -> float:
    """Compute fold-level compounded drawdown from chronological OOS returns."""
    equity = peak = 1.0
    maximum = 0.0
    for value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        maximum = max(maximum, 1 - equity / peak)
    return maximum


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.2%}"

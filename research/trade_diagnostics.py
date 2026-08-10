"""Research-only entry feature and holding-horizon diagnostics."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path

from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data


def build_trade_diagnostics(
    artifact_dir: Path,
    output: Path,
    horizons: tuple[int, ...] = (5, 10, 20, 40),
) -> Path:
    active_data = Path("output/release/backtest_data.json")
    price_dir = (
        load_active_backtest_data(active_data)[1]
        if active_data.exists() else artifact_dir / "market_data"
    )
    candles = _load_candles(price_dir)
    market_sessions = sorted({date for series in candles.values() for date, _, _ in series})
    trades = []
    costs = transaction_cost_policy_from_env()
    for path in sorted((artifact_dir / "selections").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        selected_at = datetime.fromisoformat(payload["selected_at"])
        for row in payload["selections"]:
            series = candles.get(row["code"], [])
            eligible = [item for item in series if item[0] > selected_at]
            if not eligible:
                continue
            entry_price = eligible[0][1]
            returns = {}
            for horizon in horizons:
                future_sessions = [date for date in market_sessions if date > selected_at]
                if len(future_sessions) >= horizon:
                    target = future_sessions[horizon - 1]
                    exit_rows = [item for item in series if item[0] <= target]
                    if not exit_rows:
                        continue
                    returns[horizon] = costs.net_return(
                        entry_price, exit_rows[-1][2]
                    )
            if returns:
                context = row.get("market_context") or {}
                trades.append({
                    "year": selected_at.year,
                    "rank": int(row["rank"]),
                    "score": int(row["total_score"]),
                    "features": set(row.get("enabled_features", [])),
                    "market_strength": float(context.get("market_strength") or 0),
                    "short_strength": float(context.get("short_market_strength") or 0),
                    "returns": returns,
                })

    lines = [
        "# TITAN Entry and Holding-Horizon Diagnostics", "",
        "> Research only. The same historical entries are re-priced at alternative holding sessions; this is not an independent strategy test.",
        "", "## Holding horizon", "",
        "| Sessions | Trades | Net | Positive years | Year returns |",
        "|---:|---:|---:|---:|---|",
    ]
    for horizon in horizons:
        usable = [row for row in trades if horizon in row["returns"]]
        annual = {
            year: _average([row["returns"][horizon] for row in usable if row["year"] == year])
            for year in sorted({row["year"] for row in usable})
        }
        lines.append(
            f"| {horizon} | {len(usable)} | {_average([row['returns'][horizon] for row in usable]):.2%} | "
            f"{sum(value > 0 for value in annual.values())}/{len(annual)} | "
            + ", ".join(f"{year} {value:.2%}" for year, value in annual.items())
            + " |"
        )

    base_horizon = 20
    base = [row for row in trades if base_horizon in row["returns"]]
    lines += ["", "## Entry characteristics at 20 sessions", ""]
    for title, groups in (
        ("Score band", _groups(base, lambda row: _score_band(row["score"]))),
        ("Rank", _groups(base, lambda row: str(row["rank"]))),
        ("Market strength", _groups(base, lambda row: _strength_band(row["market_strength"]))),
    ):
        lines += [f"### {title}", "", "| Group | Trades | Net |", "|---|---:|---:|"]
        for name, rows in sorted(groups.items()):
            lines.append(
                f"| {name} | {len(rows)} | {_average([row['returns'][base_horizon] for row in rows]):.2%} |"
            )
        lines.append("")

    feature_rows = []
    features = sorted({feature for row in base for feature in row["features"]})
    for feature in features:
        present = [row["returns"][base_horizon] for row in base if feature in row["features"]]
        absent = [row["returns"][base_horizon] for row in base if feature not in row["features"]]
        if present and absent:
            feature_rows.append((
                _average(present) - _average(absent), feature, len(present),
                _average(present), _average(absent),
            ))
    lines += [
        "### Feature separation", "",
        "| Feature | Present | Present net | Absent net | Difference |",
        "|---|---:|---:|---:|---:|",
    ]
    for difference, feature, count, present, absent in sorted(feature_rows, reverse=True):
        lines.append(
            f"| {feature} | {count} | {present:.2%} | {absent:.2%} | {difference:+.2%} |"
        )
    lines += [
        "", "Feature differences are descriptive and overlap with other features. They must be confirmed in a new walk-forward candidate before use.",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _load_candles(
    directory: Path,
) -> dict[str, list[tuple[datetime, float, float]]]:
    result = {}
    for path in directory.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "code" not in payload or "candles" not in payload:
            continue
        result[payload["code"]] = [
            (
                datetime.fromisoformat(row["date"]),
                float(row["open"]),
                float(row["close"]),
            )
            for row in payload["candles"]
        ]
    return result


def _groups(rows, key):
    result = defaultdict(list)
    for row in rows:
        result[key(row)].append(row)
    return result


def _score_band(score: int) -> str:
    return "78-82" if score <= 82 else "83-87" if score <= 87 else "88+"


def _strength_band(value: float) -> str:
    return "<65%" if value < .65 else "65-70%" if value < .70 else ">=70%"


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0

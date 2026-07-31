"""Point-in-time validation of stock strength relative to its industry peers."""

from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from broker.historical import HistoricalFileMarketProvider
from config.sector_groups import SECTOR_GROUPS
from release.backtest_data import load_active_backtest_data


LOOKBACK_WEIGHTS = {20: 0.10, 60: 0.30, 120: 0.30, 240: 0.30}
FORWARD_HORIZONS = (5, 20, 60)


@dataclass(frozen=True)
class IndustryRsObservation:
    signal_date: str
    group: str
    code: str
    name: str
    rs_score: float
    industry_rank: int
    industry_size: int
    relative_strength: float
    industry_momentum: float
    stock_momentum: float
    forward_5d: float | None
    forward_20d: float | None
    forward_60d: float | None


def run_industry_rs_validation(
    active_data_path: Path,
    output_dir: Path,
    start_date: str = "2022-04-01",
    end_date: str = "2023-09-01",
    rebalance_sessions: int = 5,
) -> tuple[dict, dict[str, Path]]:
    """Validate whether industry-relative RS predicts subsequent returns."""
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    if rebalance_sessions < 1:
        raise ValueError("rebalance_sessions must be positive")

    _, price_dir, _ = load_active_backtest_data(active_data_path)
    ranking = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )
    eligible = {
        datetime.fromisoformat(key): set(value)
        for key, value in ranking["sessions"].items()
    }
    sessions = sorted(eligible)
    session_index = {value: index for index, value in enumerate(sessions)}
    provider = HistoricalFileMarketProvider(price_dir)
    candles: dict[str, dict[datetime, object]] = {}
    for members in SECTOR_GROUPS.values():
        for code in members:
            try:
                candles[code] = {c.date: c for c in provider._candles(code)}
            except FileNotFoundError:
                candles[code] = {}

    observations: list[IndustryRsObservation] = []
    validation_dates = [
        value for value in sessions if start <= value <= end
    ][::rebalance_sessions]
    for signal in validation_dates:
        index = session_index[signal]
        raw_rows = _signal_rows(
            signal, index, sessions, eligible[signal], candles
        )
        if not raw_rows:
            continue
        percentiles = _percentile_scores(
            [row["relative_strength"] for row in raw_rows]
        )
        group_values: dict[str, list[float]] = {}
        for row in raw_rows:
            group_values.setdefault(row["group"], []).append(
                row["relative_strength"]
            )
        for row, percentile in zip(raw_rows, percentiles):
            ordered = sorted(
                group_values[row["group"]], reverse=True
            )
            rank = ordered.index(row["relative_strength"]) + 1
            forward = _forward_returns(
                row["code"], signal, index, sessions, candles
            )
            observations.append(IndustryRsObservation(
                signal_date=signal.date().isoformat(),
                group=row["group"],
                code=row["code"],
                name=row["name"],
                rs_score=percentile,
                industry_rank=rank,
                industry_size=len(ordered),
                relative_strength=row["relative_strength"],
                industry_momentum=row["industry_momentum"],
                stock_momentum=row["stock_momentum"],
                forward_5d=forward[5],
                forward_20d=forward[20],
                forward_60d=forward[60],
            ))

    latest_date = max(
        (item.signal_date for item in observations), default=None
    )
    latest = sorted(
        (
            item for item in observations
            if item.signal_date == latest_date
        ),
        key=lambda item: (-item.rs_score, item.code),
    )
    result = {
        "schema_version": 1,
        "feature": "업종 대비 종목 RS",
        "period": {"start": start_date, "end": end_date},
        "lookback_weights": {
            str(key): value for key, value in LOOKBACK_WEIGHTS.items()
        },
        "rebalance_sessions": rebalance_sessions,
        "peer_method": "leave-one-out median return",
        "observation_count": len(observations),
        "validation_date_count": len({
            item.signal_date for item in observations
        }),
        "horizon_summaries": {
            str(horizon): _horizon_summary(observations, horizon)
            for horizon in FORWARD_HORIZONS
        },
        "group_summaries": {
            group: _group_summary(observations, group)
            for group in SECTOR_GROUPS
        },
        "latest_signal_date": latest_date,
        "latest_candidates": [
            _as_dict(item) for item in latest[:20]
        ],
        "observations": [_as_dict(item) for item in observations],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "industry_rs_validation.json"
    csv_path = output_dir / "industry_rs_observations.csv"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        rows = result["observations"]
        writer = csv.DictWriter(
            stream,
            fieldnames=list(rows[0]) if rows else ["signal_date"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return result, {"json": json_path, "csv": csv_path}


def _signal_rows(signal, index, sessions, eligible, candles):
    rows = []
    available = [
        horizon for horizon in LOOKBACK_WEIGHTS if index >= horizon
    ]
    if not available:
        return rows
    total_weight = sum(LOOKBACK_WEIGHTS[value] for value in available)
    for group, members in SECTOR_GROUPS.items():
        member_returns: dict[int, dict[str, float]] = {}
        for horizon in available:
            prior = sessions[index - horizon]
            values = {}
            for code in members:
                first = candles[code].get(prior)
                last = candles[code].get(signal)
                if (
                    code in eligible and first is not None
                    and last is not None and first.close > 0
                ):
                    values[code] = last.close / first.close - 1
            member_returns[horizon] = values
        for code, name in members.items():
            components = []
            stock_components = []
            industry_components = []
            for horizon in available:
                values = member_returns[horizon]
                if code not in values:
                    continue
                peers = [
                    value for peer, value in values.items() if peer != code
                ]
                if len(peers) < 2:
                    continue
                peer_return = statistics.median(peers)
                weight = LOOKBACK_WEIGHTS[horizon] / total_weight
                stock_return = values[code]
                components.append(weight * (stock_return - peer_return))
                stock_components.append(weight * stock_return)
                industry_components.append(weight * peer_return)
            if components:
                rows.append({
                    "group": group,
                    "code": code,
                    "name": name,
                    "relative_strength": sum(components),
                    "stock_momentum": sum(stock_components),
                    "industry_momentum": sum(industry_components),
                })
    return rows


def _percentile_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    if len(values) == 1:
        return [100.0]
    ordered = sorted(values)
    return [
        round(100 * ordered.index(value) / (len(values) - 1), 2)
        for value in values
    ]


def _forward_returns(code, signal, index, sessions, candles):
    start = candles[code].get(signal)
    output = {}
    for horizon in FORWARD_HORIZONS:
        if start is None or start.close <= 0 or index + horizon >= len(sessions):
            output[horizon] = None
            continue
        end = candles[code].get(sessions[index + horizon])
        output[horizon] = (
            end.close / start.close - 1 if end is not None else None
        )
    return output


def _horizon_summary(observations, horizon):
    field = f"forward_{horizon}d"
    buckets = []
    for lower in range(0, 100, 20):
        values = [
            getattr(item, field) for item in observations
            if lower <= item.rs_score
            and (item.rs_score < lower + 20 or lower == 80)
            and getattr(item, field) is not None
        ]
        buckets.append({
            "label": f"{lower}-{lower + 20}",
            "count": len(values),
            "average_return": statistics.mean(values) if values else None,
            "win_rate": (
                sum(value > 0 for value in values) / len(values)
                if values else None
            ),
        })
    bottom = [getattr(item, field) for item in observations
              if item.rs_score <= 20 and getattr(item, field) is not None]
    top = [getattr(item, field) for item in observations
           if item.rs_score >= 80 and getattr(item, field) is not None]
    return {
        "buckets": buckets,
        "top_bottom_spread": (
            statistics.mean(top) - statistics.mean(bottom)
            if top and bottom else None
        ),
        "monotonic": _is_monotonic([
            bucket["average_return"] for bucket in buckets
        ]),
    }


def _group_summary(observations, group):
    members = [item for item in observations if item.group == group]
    top = [item.forward_20d for item in members
           if item.rs_score >= 80 and item.forward_20d is not None]
    return {
        "observations": len(members),
        "top_20_count": len(top),
        "top_20_average_20d": statistics.mean(top) if top else None,
    }


def _is_monotonic(values):
    usable = [value for value in values if value is not None]
    return len(usable) >= 3 and all(
        left <= right for left, right in zip(usable, usable[1:])
    )


def _as_dict(item: IndustryRsObservation) -> dict:
    return {
        key: getattr(item, key)
        for key in item.__dataclass_fields__
    }

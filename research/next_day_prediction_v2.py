"""Grouped cross-sectional scoring for next-open research entries."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
from statistics import median

from broker.historical import HistoricalFileMarketProvider
from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data
from research.next_day_prediction import extract_features


GROUP_WEIGHTS = {
    "momentum": 0.20,
    "trend": 0.15,
    "activity": 0.20,
    "price_strength": 0.20,
    "risk_overheat": 0.25,
}


def percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """Return deterministic 0..1 cross-sectional ranks with averaged ties."""
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    if len(ordered) <= 1:
        return {code: 0.5 for code in values}
    result = {}
    position = 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and ordered[end][1] == ordered[position][1]:
            end += 1
        average_rank = ((position + end - 1) / 2) / (len(ordered) - 1)
        for index in range(position, end):
            result[ordered[index][0]] = average_rank
        position = end
    return result


def grouped_scores(rows: list[dict]) -> list[dict]:
    keys = (
        "return_5d", "relative_return_20d", "ma5_over_ma20", "ma20_over_ma60",
        "distance_high_20d", "directional_volume", "trading_value_log",
        "close_location", "breakout_hold", "upper_wick", "atr_20d",
        "consecutive_up", "return_1d",
    )
    ranks = {
        key: percentile_ranks({row["code"]: row["features"][key] for row in rows})
        for key in keys
    }
    for row in rows:
        code = row["code"]
        momentum = (ranks["return_5d"][code] + ranks["relative_return_20d"][code]) / 2
        trend = (
            ranks["ma5_over_ma20"][code] + ranks["ma20_over_ma60"][code]
            + ranks["distance_high_20d"][code]
        ) / 3
        activity = (ranks["directional_volume"][code] + ranks["trading_value_log"][code]) / 2
        price_strength = (
            ranks["close_location"][code] + ranks["breakout_hold"][code]
            + (1 - ranks["upper_wick"][code])
        ) / 3
        atr_balance = 1 - abs(ranks["atr_20d"][code] - 0.5) * 2
        risk_overheat = (
            atr_balance + (1 - ranks["consecutive_up"][code])
            + (1 - ranks["return_1d"][code])
        ) / 3
        groups = {
            "momentum": momentum, "trend": trend, "activity": activity,
            "price_strength": price_strength, "risk_overheat": risk_overheat,
        }
        row["groups"] = groups
        row["score"] = round(sum(groups[name] * weight for name, weight in GROUP_WEIGHTS.items()) * 100, 4)
    return rows


def run_next_day_prediction_v2(
    active_data_path: Path,
    output_dir: Path,
    start_year: int = 2025,
    universe_size: int = 300,
    prediction_count: int = 5,
    exclude_quarantined: bool = True,
) -> dict:
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    provider = HistoricalFileMarketProvider(price_dir)
    membership = json.loads((price_dir / "market_cap_top500.json").read_text(encoding="utf-8"))["sessions"]
    sessions = sorted(datetime.fromisoformat(key) for key in membership)
    histories, indices, names, stock_meta = {}, {}, {}, {}
    quarantine_rows = json.loads((price_dir / "quality_quarantines.json").read_text(encoding="utf-8"))
    quarantines = defaultdict(list)
    for item in quarantine_rows:
        quarantines[str(item["code"]).zfill(6)].append(item)
    costs = transaction_cost_policy_from_env()

    def history(code):
        if code not in histories:
            histories[code] = provider._candles(code)
            indices[code] = {row.date: i for i, row in enumerate(histories[code])}
            try:
                stock_meta[code] = json.loads((price_dir / f"{code}.json").read_text(encoding="utf-8"))
                names[code] = stock_meta[code].get("name", code)
            except (OSError, json.JSONDecodeError):
                names[code] = code
                stock_meta[code] = {}
        return histories[code]

    samples = defaultdict(list)
    recent = []
    leakage_violations = 0
    for session_pos, feature_date in enumerate(sessions[:-3]):
        if feature_date.year < start_year:
            continue
        trade_date = sessions[session_pos + 1]
        rows = []
        raw_features = []
        for raw_code in membership[feature_date.isoformat()][:universe_size]:
            code = str(raw_code).zfill(6)
            try:
                candles = history(code)
            except FileNotFoundError:
                continue
            feature_index = indices[code].get(feature_date)
            trade_index = indices[code].get(trade_date)
            if feature_index is None or trade_index is None or feature_index < 60:
                continue
            audit_end_index = trade_index + 2
            if audit_end_index >= len(candles):
                continue
            audit_start = candles[feature_index - 60].date
            audit_end = candles[audit_end_index].date
            overlapping_quarantines = [
                item for item in quarantines[code]
                if datetime.fromisoformat(item["start"]) <= audit_end
                and datetime.fromisoformat(item["end"]) >= audit_start
            ]
            if exclude_quarantined and overlapping_quarantines:
                continue
            base = extract_features(candles, feature_index)
            current = candles[feature_index]
            body_return = current.close / current.open - 1 if current.open > 0 else 0
            upper_wick = (current.high - max(current.open, current.close)) / max(1, current.high - current.low)
            consecutive_up = 0
            for idx in range(feature_index, max(0, feature_index - 5), -1):
                if candles[idx].close > candles[idx - 1].close:
                    consecutive_up += 1
                else:
                    break
            features = {
                **base,
                "directional_volume": base["volume_ratio_20d"] * body_return,
                "upper_wick": upper_wick,
                "breakout_hold": current.close / max(row.high for row in candles[feature_index - 20:feature_index]) - 1,
                "consecutive_up": float(consecutive_up),
            }
            raw_features.append(features)
            rows.append({
                "code": code, "features": features, "candles": candles,
                "trade_index": trade_index, "quarantines": overlapping_quarantines,
            })
        if not rows:
            continue
        market_return_20d = median(item["return_20d"] for item in raw_features)
        for row in rows:
            row["features"]["relative_return_20d"] = row["features"]["return_20d"] - market_return_20d
        grouped_scores(rows)
        chosen = sorted(rows, key=lambda row: (-row["score"], row["code"]))[:prediction_count]
        day_selections = []
        for row in chosen:
            candles, entry_index = row["candles"], row["trade_index"]
            entry = candles[entry_index].open
            if entry <= 0 or entry_index + 2 >= len(candles):
                continue
            return_1d = costs.net_return(entry, candles[entry_index].close)
            return_3d = costs.net_return(entry, candles[entry_index + 2].close)
            path = candles[entry_index:entry_index + 3]
            prior_close = candles[entry_index - 1].close
            day_selections.append({
                "code": row["code"], "name": names.get(row["code"], row["code"]),
                "score": row["score"], "groups": row["groups"],
                "return_1d": return_1d, "return_3d": return_3d,
                "entry_date": candles[entry_index].date.date().isoformat(),
                "exit_date": candles[entry_index + 2].date.date().isoformat(),
                "prior_close": prior_close, "entry_open": entry,
                "exit_close": candles[entry_index + 2].close,
                "opening_gap": entry / prior_close - 1 if prior_close > 0 else None,
                "price_path": [
                    {"date": candle.date.date().isoformat(), "open": candle.open,
                     "high": candle.high, "low": candle.low, "close": candle.close,
                     "volume": candle.volume}
                    for candle in path
                ],
                "quarantines": row["quarantines"],
                "adjustment_events": stock_meta.get(row["code"], {}).get("adjustment_events", []),
                "unresolved_large_jumps": stock_meta.get(row["code"], {}).get("unresolved_large_jumps", []),
            })
            samples[(trade_date.year, "trade")].append(return_3d)
            leakage_violations += int(feature_date >= trade_date)
        if not day_selections:
            continue
        cohort_1d = sum(row["return_1d"] for row in day_selections) / prediction_count
        cohort_3d = sum(row["return_3d"] for row in day_selections) / prediction_count
        benchmark_3d_values = []
        for row in rows:
            candles, entry_index = row["candles"], row["trade_index"]
            if entry_index + 2 < len(candles) and candles[entry_index].open > 0:
                benchmark_3d_values.append(costs.net_return(candles[entry_index].open, candles[entry_index + 2].close))
        benchmark_3d = sum(benchmark_3d_values) / len(benchmark_3d_values)
        regime = "상승" if market_return_20d > 0.02 else "하락" if market_return_20d < -0.02 else "횡보"
        record = {
            "feature_date": feature_date.date().isoformat(), "trade_date": trade_date.date().isoformat(),
            "year": trade_date.year, "regime": regime, "average_1d_net_return": cohort_1d,
            "average_3d_net_return": cohort_3d, "benchmark_3d_net_return": benchmark_3d,
            "excess_3d_return": cohort_3d - benchmark_3d, "selections": day_selections,
        }
        samples[(trade_date.year, "cohort")].append(record)
        recent.append(record)

    yearly = [_summarize_year(year, samples[(year, "cohort")], samples[(year, "trade")]) for year in (2025, 2026)]
    validation = next((row for row in yearly if row["year"] == 2026), {})
    verdict = "PROMISING_RESEARCH" if (
        validation.get("average_3d_net_return", 0) > 0
        and validation.get("median_trade_3d_return", 0) > 0
        and validation.get("average_excess_3d_return", 0) > 0
    ) else "NOT_USABLE"
    all_trades = [trade for record in recent for trade in record["selections"]]
    extreme_losses = sorted(all_trades, key=lambda row: row["return_3d"])[:20]
    for trade in extreme_losses:
        trade["audit_classification"] = _classify_extreme_loss(trade)
    result = {
        "schema_version": 1, "status": "RESEARCH_ONLY", "verdict": verdict,
        "objective": "다음 거래일 시가 진입 후 3거래일째 종가 청산 순수익",
        "weights": GROUP_WEIGHTS, "universe_size": universe_size,
        "prediction_count": prediction_count, "leakage_violations": leakage_violations,
        "quarantine_policy_applied": exclude_quarantined,
        "operational_orders": 0, "yearly": yearly,
        "regime": _summarize_regimes(recent),
        "market_filter_experiment": [
            _market_filter_summary(year, [record for record in recent if record["year"] == year])
            for year in (2025, 2026)
        ],
        "year_regime": [
            {"year": year, **row}
            for year in (2025, 2026)
            for row in _summarize_regimes([record for record in recent if record["year"] == year])
        ],
        "recent_predictions": recent[-30:],
        "extreme_losses": extreme_losses,
        "limitations": [
            "업종 시점별 분류 데이터가 없어 업종 상대강도는 제외함",
            "시장 상대강도는 시점별 상위 300종목의 20일 수익률 중앙값을 대용치로 사용함",
            "3일 코호트가 날짜별로 겹치므로 누적복리와 MDD를 실제 포트폴리오 성과로 표시하지 않음",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = "next_day_prediction_v2.json" if exclude_quarantined else "next_day_prediction_v2_raw_audit.json"
    path = output_dir / filename
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["json_path"] = str(path)
    return result


def _summarize_year(year, cohorts, trades):
    cohort_3d = [row["average_3d_net_return"] for row in cohorts]
    return {
        "year": year, "cohorts": len(cohorts), "trades": len(trades),
        "average_1d_net_return": _average([row["average_1d_net_return"] for row in cohorts]),
        "average_3d_net_return": _average(cohort_3d),
        "median_trade_3d_return": median(trades) if trades else None,
        "positive_trade_rate": sum(value > 0 for value in trades) / len(trades) if trades else None,
        "average_excess_3d_return": _average([row["excess_3d_return"] for row in cohorts]),
        "worst_trade_3d_return": min(trades) if trades else None,
        "worst_cohort_3d_return": min(cohort_3d) if cohort_3d else None,
    }


def _summarize_regimes(records):
    result = []
    for regime in ("상승", "횡보", "하락"):
        rows = [row for row in records if row["regime"] == regime]
        result.append({
            "regime": regime, "cohorts": len(rows),
            "average_3d_net_return": _average([row["average_3d_net_return"] for row in rows]),
            "average_excess_3d_return": _average([row["excess_3d_return"] for row in rows]),
        })
    return result


def _market_filter_summary(year, records):
    baseline = [row["average_3d_net_return"] for row in records]
    filtered = [
        row["average_3d_net_return"] if row["regime"] != "하락" else 0.0
        for row in records
    ]
    active = sum(row["regime"] != "하락" for row in records)
    return {
        "year": year, "cohorts": len(records), "active_cohorts": active,
        "active_rate": active / len(records) if records else None,
        "baseline_average_3d_net_return": _average(baseline),
        "filtered_average_3d_net_return": _average(filtered),
        "difference": _average(filtered) - _average(baseline) if records else None,
        "adopted": False,
    }


def _average(values):
    return sum(values) / len(values) if values else None


def _classify_extreme_loss(trade):
    if trade.get("quarantines"):
        return "QUARANTINED_DATA_INTERVAL"
    if trade.get("adjustment_events"):
        entry = datetime.fromisoformat(trade["entry_date"])
        exit_ = datetime.fromisoformat(trade["exit_date"])
        for event in trade["adjustment_events"]:
            raw_date = event.get("date") or event.get("effective_date")
            if raw_date and entry <= datetime.fromisoformat(raw_date) <= exit_:
                return "INFERRED_CORPORATE_ACTION"
    if any(row["volume"] == 0 for row in trade["price_path"]):
        return "ZERO_VOLUME_OR_SUSPENSION"
    if trade.get("opening_gap") is not None and abs(trade["opening_gap"]) >= 0.30:
        return "EXTREME_OPENING_GAP"
    closes = [trade["prior_close"]] + [row["close"] for row in trade["price_path"]]
    if any(closes[index] / closes[index - 1] - 1 <= -0.30 for index in range(1, len(closes))):
        return "PRICE_DISCONTINUITY_OR_LIMIT_CRASH"
    return "OBSERVED_MARKET_LOSS"

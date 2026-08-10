"""Research-only prior-close features for next-session open-to-close winners."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import math
from pathlib import Path

from broker.historical import HistoricalFileMarketProvider
from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data


FEATURE_COUNT = 15
HOLDING_PERIODS = (1, 2, 3, 5)
GAP_CAPS = (None, 0.00, 0.02, 0.03, 0.05)


def run_next_day_prediction(
    active_data_path: Path,
    output_dir: Path,
    start_year: int = 2025,
    universe_size: int = 300,
    label_top_n: int = 30,
    prediction_count: int = 5,
    minimum_label_return: float = 0.02,
) -> dict:
    if universe_size <= 0 or label_top_n <= 0 or prediction_count <= 0:
        raise ValueError("universe and selection sizes must be positive")
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    provider = HistoricalFileMarketProvider(price_dir)
    membership = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )["sessions"]
    sessions = sorted(datetime.fromisoformat(key) for key in membership)
    histories: dict[str, tuple] = {}
    indices: dict[str, dict[datetime, int]] = {}
    names: dict[str, str] = {}
    costs = transaction_cost_policy_from_env()

    def history(code: str):
        if code not in histories:
            rows = provider._candles(code)
            histories[code] = rows
            indices[code] = {row.date: i for i, row in enumerate(rows)}
            try:
                names[code] = json.loads(
                    (price_dir / f"{code}.json").read_text(encoding="utf-8")
                ).get("name", code)
            except (OSError, json.JSONDecodeError):
                names[code] = code
        return histories[code]

    feature_stats = {
        name: {"present": 0, "present_labels": 0, "absent": 0, "absent_labels": 0}
        for name in _feature_conditions()
    }
    predictions, yearly_daily = [], defaultdict(list)
    holding_samples = defaultdict(list)
    total_rows = total_labels = 0
    leakage_violations = 0
    for position, selected_at in enumerate(sessions[:-1]):
        if selected_at.year < start_year:
            continue
        next_date = sessions[position + 1]
        codes = [str(code).zfill(6) for code in membership[selected_at.isoformat()]][:universe_size]
        rows = []
        for code in codes:
            try:
                candles = history(code)
            except FileNotFoundError:
                continue
            index = indices[code].get(selected_at)
            next_index = indices[code].get(next_date)
            if index is None or next_index is None or index < 60:
                continue
            features = extract_features(candles, index)
            next_candle = candles[next_index]
            if next_candle.open <= 0:
                continue
            horizon_returns = {}
            for holding_days in HOLDING_PERIODS:
                exit_index = next_index + holding_days - 1
                if exit_index < len(candles):
                    horizon_returns[str(holding_days)] = costs.net_return(
                        next_candle.open, candles[exit_index].close
                    )
            raw_return = next_candle.close / next_candle.open - 1
            rows.append({"date": selected_at, "next_date": next_date, "code": code,
                         "features": features, "raw_return": raw_return,
                         "net_return": costs.net_return(next_candle.open, next_candle.close),
                         "opening_gap": next_candle.open / candles[index].close - 1,
                         "horizon_returns": horizon_returns})
        if not rows:
            continue
        label_codes = {
            row["code"] for row in sorted(rows, key=lambda item: item["raw_return"], reverse=True)[:label_top_n]
            if row["raw_return"] >= minimum_label_return
        }
        for row in rows:
            row["label"] = row["code"] in label_codes
            row["score"] = score_features(row["features"])
            total_rows += 1
            total_labels += int(row["label"])
            leakage_violations += int(row["date"] >= row["next_date"])
            for name, predicate in _feature_conditions().items():
                key = "present" if predicate(row["features"]) else "absent"
                feature_stats[name][key] += 1
                feature_stats[name][key + "_labels"] += int(row["label"])
        chosen = sorted(rows, key=lambda item: (-item["score"], item["code"]))[:prediction_count]
        for holding_days in HOLDING_PERIODS:
            # Do not mix incomplete end-of-sample cohorts into a longer horizon.
            if position + holding_days >= len(sessions):
                continue
            for gap_cap in GAP_CAPS:
                accepted = [
                    row for row in chosen
                    if (gap_cap is None or row["opening_gap"] <= gap_cap)
                    and str(holding_days) in row["horizon_returns"]
                ]
                # Empty or rejected slots remain cash; denominator stays at five.
                cohort_return = sum(
                    row["horizon_returns"][str(holding_days)] for row in accepted
                ) / prediction_count
                holding_samples[(holding_days, gap_cap)].append({
                    "year": next_date.year,
                    "return": cohort_return,
                    "accepted": len(accepted),
                })
        daily_net = sum(row["net_return"] for row in chosen) / len(chosen)
        benchmark = sum(row["raw_return"] for row in rows) / len(rows)
        yearly_daily[str(next_date.year)].append(daily_net)
        predictions.append({
            "feature_date": selected_at.date().isoformat(),
            "trade_date": next_date.date().isoformat(),
            "label_count": len(label_codes),
            "hits": sum(row["label"] for row in chosen),
            "precision_at_5": sum(row["label"] for row in chosen) / len(chosen),
            "average_net_return": daily_net,
            "benchmark_return": benchmark,
            "excess_return": daily_net - benchmark,
            "selections": [{"rank": rank, "code": row["code"], "name": names.get(row["code"], row["code"]),
                            "score": row["score"], "label": row["label"],
                            "net_return": row["net_return"]}
                           for rank, row in enumerate(chosen, 1)],
        })
    feature_rows = []
    base_rate = total_labels / total_rows if total_rows else None
    for name, values in feature_stats.items():
        present_rate = values["present_labels"] / values["present"] if values["present"] else None
        absent_rate = values["absent_labels"] / values["absent"] if values["absent"] else None
        feature_rows.append({"feature": name, **values, "present_label_rate": present_rate,
                             "absent_label_rate": absent_rate,
                             "lift": present_rate / base_rate if present_rate is not None and base_rate else None})
    daily_returns = [row["average_net_return"] for row in predictions]
    curve, peak, maximum_drawdown = 1.0, 1.0, 0.0
    for value in daily_returns:
        curve *= 1 + value
        peak = max(peak, curve)
        maximum_drawdown = max(maximum_drawdown, 1 - curve / peak)
    summary = {
        "start_year": start_year, "end_date": predictions[-1]["trade_date"] if predictions else None,
        "universe_size": universe_size, "label_top_n": label_top_n,
        "minimum_label_return": minimum_label_return, "prediction_count": prediction_count,
        "feature_count": FEATURE_COUNT, "trading_days": len(predictions),
        "dataset_rows": total_rows, "positive_labels": total_labels,
        "base_rate": base_rate,
        "precision_at_5": _average([row["precision_at_5"] for row in predictions]),
        "average_daily_net_return": _average(daily_returns),
        "average_excess_return": _average([row["excess_return"] for row in predictions]),
        "compounded_return": curve - 1 if predictions else None,
        "maximum_drawdown": maximum_drawdown if predictions else None,
        "positive_day_rate": sum(value > 0 for value in daily_returns) / len(daily_returns) if daily_returns else None,
        "leakage_violations": leakage_violations, "operational_orders": 0,
    }
    yearly = [{"year": year, "days": len(values), "average_daily_net_return": _average(values),
               "positive_day_rate": sum(v > 0 for v in values) / len(values),
               "compounded_return": _compound(values)} for year, values in sorted(yearly_daily.items())]
    holding_comparison = _summarize_holding_samples(holding_samples, prediction_count)
    training_rows = [row for row in holding_comparison if row["train_2025"]["cohorts"]]
    selected_configuration = max(
        training_rows,
        key=lambda row: (
            row["train_2025"]["average_cohort_net_return"],
            -row["train_2025"]["maximum_drawdown"],
        ),
        default=None,
    )
    latest_date = sessions[-1]
    current_scored = []
    for raw_code in membership[latest_date.isoformat()][:universe_size]:
        code = str(raw_code).zfill(6)
        try:
            candles = history(code)
        except FileNotFoundError:
            continue
        index = indices[code].get(latest_date)
        if index is None or index < 60:
            continue
        current_scored.append({"code": code, "name": names.get(code, code),
                               "score": score_features(extract_features(candles, index))})
    current_forecast = {
        "feature_date": latest_date.date().isoformat(),
        "status": "AWAITING_NEXT_SESSION",
        "selections": [{"rank": rank, **row} for rank, row in enumerate(
            sorted(current_scored, key=lambda row: (-row["score"], row["code"]))[:prediction_count], 1
        )],
    }
    result = {"schema_version": 2, "status": "RESEARCH_ONLY", "verdict": "NOT_USABLE",
              "summary": summary,
              "features": sorted(feature_rows, key=lambda row: row["lift"] or 0, reverse=True),
              "yearly": yearly, "holding_comparison": holding_comparison,
              "selected_configuration": selected_configuration,
              "current_forecast": current_forecast,
              "recent_predictions": predictions[-30:]}
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "next_day_prediction.json"
    markdown_path = output_dir / "next_day_prediction.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(result), encoding="utf-8")
    result.update(json_path=str(json_path), markdown_path=str(markdown_path))
    return result


def extract_features(candles, index: int) -> dict[str, float]:
    if index < 60:
        raise ValueError("at least 61 candles are required")
    current = candles[index]
    close = current.close
    window5, window20, window60 = candles[index - 4:index + 1], candles[index - 19:index + 1], candles[index - 59:index + 1]
    prior20 = candles[index - 20:index]
    true_ranges = [
        max(row.high - row.low, abs(row.high - candles[i - 1].close), abs(row.low - candles[i - 1].close))
        for i, row in enumerate(candles[index - 19:index + 1], start=index - 19)
    ]
    average_range5 = sum((row.high - row.low) / row.close for row in window5 if row.close > 0) / 5
    average_range20 = sum((row.high - row.low) / row.close for row in window20 if row.close > 0) / 20
    return {
        "return_1d": close / candles[index - 1].close - 1,
        "return_3d": close / candles[index - 3].close - 1,
        "return_5d": close / candles[index - 5].close - 1,
        "return_10d": close / candles[index - 10].close - 1,
        "return_20d": close / candles[index - 20].close - 1,
        "volume_ratio_5d": current.volume / max(1, sum(row.volume for row in window5) / 5),
        "volume_ratio_20d": current.volume / max(1, sum(row.volume for row in window20) / 20),
        "trading_value_log": math.log1p(close * current.volume),
        "close_location": (close - current.low) / max(1, current.high - current.low),
        "distance_high_20d": close / max(row.high for row in prior20) - 1,
        "distance_high_60d": close / max(row.high for row in window60[:-1]) - 1,
        "ma5_over_ma20": (sum(row.close for row in window5) / 5) / (sum(row.close for row in window20) / 20) - 1,
        "ma20_over_ma60": (sum(row.close for row in window20) / 20) / (sum(row.close for row in window60) / 60) - 1,
        "atr_20d": (sum(true_ranges) / len(true_ranges)) / close,
        "range_contraction_5v20": average_range5 / max(1e-9, average_range20),
    }


def score_features(f: dict[str, float]) -> float:
    clamp = lambda value, low=0.0, high=1.0: max(low, min(high, value))
    score = (
        .12 * clamp((f["return_5d"] + .05) / .15)
        + .08 * clamp((f["return_20d"] + .10) / .30)
        + .12 * clamp(f["volume_ratio_20d"] / 3)
        + .10 * clamp(f["close_location"])
        + .15 * clamp((f["distance_high_20d"] + .15) / .15)
        + .08 * clamp((f["distance_high_60d"] + .25) / .25)
        + .08 * clamp((f["ma5_over_ma20"] + .05) / .15)
        + .07 * clamp((f["ma20_over_ma60"] + .10) / .25)
        + .05 * clamp((f["trading_value_log"] - 20) / 6)
        + .08 * (1.0 if .02 <= f["atr_20d"] <= .08 else .25)
        + .07 * (1.0 if -.02 <= f["return_1d"] <= .05 else .25)
    )
    return round(score * 100, 4)


def _feature_conditions():
    return {
        "5일 수익률 양수": lambda f: f["return_5d"] > 0,
        "20일 수익률 양수": lambda f: f["return_20d"] > 0,
        "20일 거래량 대비 1.5배": lambda f: f["volume_ratio_20d"] >= 1.5,
        "종가가 당일 범위 상위 20%": lambda f: f["close_location"] >= .8,
        "20일 고가 3% 이내": lambda f: f["distance_high_20d"] >= -.03,
        "5일선이 20일선 위": lambda f: f["ma5_over_ma20"] > 0,
        "20일선이 60일선 위": lambda f: f["ma20_over_ma60"] > 0,
        "ATR 2~8%": lambda f: .02 <= f["atr_20d"] <= .08,
        "최근 5일 변동폭 수축": lambda f: f["range_contraction_5v20"] < .8,
    }


def _average(values):
    return sum(values) / len(values) if values else None


def _compound(values):
    result = 1.0
    for value in values:
        result *= 1 + value
    return result - 1


def _maximum_drawdown(values):
    curve = peak = 1.0
    maximum = 0.0
    for value in values:
        curve *= 1 + value
        peak = max(peak, curve)
        maximum = max(maximum, 1 - curve / peak)
    return maximum


def _period_summary(samples, prediction_count):
    returns = [row["return"] for row in samples]
    accepted = sum(row["accepted"] for row in samples)
    return {
        "cohorts": len(samples),
        "accepted_trades": accepted,
        "slot_fill_rate": accepted / (len(samples) * prediction_count) if samples else None,
        "average_cohort_net_return": _average(returns),
        "positive_cohort_rate": sum(value > 0 for value in returns) / len(returns) if returns else None,
        "compounded_cohort_return": _compound(returns) if returns else None,
        "maximum_drawdown": _maximum_drawdown(returns) if returns else None,
    }


def _summarize_holding_samples(samples_by_configuration, prediction_count):
    rows = []
    for holding_days in HOLDING_PERIODS:
        for gap_cap in GAP_CAPS:
            samples = samples_by_configuration[(holding_days, gap_cap)]
            rows.append({
                "holding_days": holding_days,
                "gap_cap": gap_cap,
                "gap_label": "제한 없음" if gap_cap is None else f"+{gap_cap:.0%}",
                "train_2025": _period_summary(
                    [row for row in samples if row["year"] == 2025], prediction_count
                ),
                "validation_2026": _period_summary(
                    [row for row in samples if row["year"] == 2026], prediction_count
                ),
                "all": _period_summary(samples, prediction_count),
            })
    return rows


def _markdown(result: dict) -> str:
    s = result["summary"]
    pct = lambda value: "—" if value is None else f"{value:.2%}"
    lines = ["# 다음 날 상승 예측 1차 검증", "",
             "> 전일 장 마감 정보만 사용하고 다음 거래일 시가에 진입해 종가에 청산하는 연구입니다. 실제 주문은 없습니다.", "",
             "## 요약", "",
             f"- 기간: {s['start_year']} ~ {s['end_date']}",
             f"- 거래일 / 데이터 행: {s['trading_days']}일 / {s['dataset_rows']:,}행",
             f"- 정답 기본비율: {pct(s['base_rate'])}",
             f"- 상위 5 적중률: {pct(s['precision_at_5'])}",
             f"- 일평균 순수익 / 초과수익: {pct(s['average_daily_net_return'])} / {pct(s['average_excess_return'])}",
             f"- 단순 복리 / MDD: {pct(s['compounded_return'])} / {pct(s['maximum_drawdown'])}",
             f"- 미래정보 순서 위반: {s['leakage_violations']}건", "",
             "## 특징 진단", "", "|전일 특징|표본|정답률|기본 대비 배수|", "|---|---:|---:|---:|"]
    for row in result["features"]:
        lines.append(f"|{row['feature']}|{row['present']}|{pct(row['present_label_rate'])}|{row['lift']:.2f}x|" if row["lift"] is not None else f"|{row['feature']}|{row['present']}|—|—|")
    lines += ["", "## 연도별", "", "|연도|거래일|일평균 순수익|양(+)의 날|단순 복리|", "|---|---:|---:|---:|---:|"]
    for row in result["yearly"]:
        lines.append(f"|{row['year']}|{row['days']}|{pct(row['average_daily_net_return'])}|{pct(row['positive_day_rate'])}|{pct(row['compounded_return'])}|")
    lines += ["", "- 복리 수치는 매일 상위 5개에 전액 재투자한 진단값이며 실전 가능성을 뜻하지 않습니다.",
              "- 공식 수정주가가 아닌 잠정 조정 데이터이므로 연구 전용입니다.", ""]
    return "\n".join(lines)

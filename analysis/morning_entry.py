"""Build and evaluate next-session 10:00 entry research data."""

from __future__ import annotations

import csv
import json
import statistics
from datetime import date, datetime, time
from pathlib import Path

from broker.historical import HistoricalFileMarketProvider
from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data


def build_collection_manifest(
    runs_dir: Path,
    sessions: list[datetime],
    output: Path,
    strategy_version: str,
    candidate_field: str = "selected_candidates",
    minimum_score: float | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Create a deduplicated list of stocks requiring intraday bars."""
    next_session = {
        value.date().isoformat(): sessions[index + 1].date().isoformat()
        for index, value in enumerate(sessions[:-1])
    }
    targets: dict[tuple[str, str], dict] = {}
    for path in sorted(runs_dir.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if row.get("strategy_version") != strategy_version:
            continue
        selection_date = datetime.fromisoformat(row["as_of"]).date().isoformat()
        selection_day = date.fromisoformat(selection_date)
        if start_date is not None and selection_day < start_date:
            continue
        if end_date is not None and selection_day > end_date:
            continue
        entry_date = next_session.get(selection_date)
        if entry_date is None:
            continue
        candidate_fields = (
            ("selected_candidates", "observation_candidates")
            if candidate_field == "all_candidates"
            else (candidate_field,)
        )
        candidates = [
            candidate
            for field in candidate_fields
            for candidate in row.get(field, [])
        ]
        for candidate in candidates:
            score = candidate.get("total_score", candidate.get("score"))
            if minimum_score is not None and (
                score is None or float(score) < minimum_score
            ):
                continue
            code = str(candidate["code"]).zfill(6)
            targets[(entry_date, code)] = {
                "selection_date": selection_date,
                "entry_date": entry_date,
                "code": code,
                "name": candidate.get("name", ""),
                "rank": candidate.get("rank"),
                "score": score,
            }
    payload = {
        "strategy_version": strategy_version,
        "candidate_field": candidate_field,
        "bar_interval_minutes": 5,
        "required_window": "09:00-10:00",
        "required_fields": [
            "timestamp", "code", "open", "high", "low", "close",
            "volume", "trading_value",
        ],
        "target_count": len(targets),
        "targets": sorted(
            targets.values(), key=lambda item: (item["entry_date"], item["code"])
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def build_daily_collection_manifest(
    runs_dir: Path,
    output: Path,
    strategy_version: str,
    entry_date: date,
) -> dict:
    """Use the most recent prior selection run for today's collection."""
    candidates = []
    for path in runs_dir.glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            selected_at = datetime.fromisoformat(row["as_of"]).date()
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        if (
            row.get("strategy_version") == strategy_version
            and selected_at < entry_date
            and (entry_date - selected_at).days <= 4
        ):
            candidates.append((selected_at, row))
    latest_date = max((item[0] for item in candidates), default=None)
    latest_rows = [
        row for selected_at, row in candidates if selected_at == latest_date
    ]
    targets: dict[str, dict] = {}
    for row in latest_rows:
        for candidate in row.get("selected_candidates", []):
            code = str(candidate["code"]).zfill(6)
            targets[code] = {
                "selection_date": latest_date.isoformat(),
                "entry_date": entry_date.isoformat(),
                "code": code,
                "name": candidate.get("name", ""),
                "rank": candidate.get("rank"),
                "score": candidate.get("total_score", candidate.get("score")),
            }
    payload = {
        "strategy_version": strategy_version,
        "bar_interval_minutes": 5,
        "required_window": "09:00-10:00",
        "target_count": len(targets),
        "targets": sorted(targets.values(), key=lambda item: item["code"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def evaluate_morning_bars(
    bars_path: Path,
    previous_close: float,
    maximum_gap: float = 0.03,
    maximum_range: float = 0.04,
    maximum_spread: float | None = None,
) -> dict:
    """Evaluate completed 5-minute bars from 09:00 through 09:59."""
    if previous_close <= 0:
        raise ValueError("previous_close must be positive")
    rows = _read_bars(bars_path)
    morning = [
        row for row in rows
        if time(9, 0) <= row["timestamp"].time() < time(10, 0)
    ]
    if len(morning) < 12:
        raise ValueError("twelve completed 5-minute bars are required")
    morning = morning[-12:]
    open_price = morning[0]["open"]
    entry_price = morning[-1]["close"]
    high = max(row["high"] for row in morning)
    low = min(row["low"] for row in morning)
    total_volume = sum(row["volume"] for row in morning)
    if total_volume <= 0:
        raise ValueError("morning volume must be positive")
    vwap = sum(
        (
            row["trading_value"]
            if row["trading_value"] is not None
            else row["close"] * row["volume"]
        )
        for row in morning
    ) / total_volume
    gap = open_price / previous_close - 1.0
    intraday_range = high / low - 1.0
    recent_lows = [row["low"] for row in morning[-3:]]
    conditions = {
        "gap_ok": abs(gap) <= maximum_gap,
        "range_ok": intraday_range <= maximum_range,
        "above_vwap": entry_price >= vwap,
        "recent_lows_stable": recent_lows[1] >= recent_lows[0]
        and recent_lows[2] >= recent_lows[1],
    }
    spreads = [row["spread"] for row in morning if row["spread"] is not None]
    if maximum_spread is not None:
        conditions["spread_ok"] = bool(spreads) and spreads[-1] <= maximum_spread
    return {
        "qualified": all(conditions.values()),
        "entry_time": morning[-1]["timestamp"].isoformat(),
        "entry_price": entry_price,
        "opening_gap": gap,
        "morning_range": intraday_range,
        "morning_high": high,
        "morning_low": low,
        "vwap": vwap,
        "conditions": conditions,
    }


def run_morning_entry_backtest(
    manifest_path: Path,
    bars_dir: Path,
    active_data_path: Path,
    output_dir: Path,
    profit_target: float = 0.05,
    stop_loss: float = 0.10,
    maximum_holding_sessions: int = 20,
) -> dict:
    """Compare next-open entry with qualified 10:00 entry."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    top500 = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )
    sessions = sorted(datetime.fromisoformat(value) for value in top500["sessions"])
    session_index = {value.date(): index for index, value in enumerate(sessions)}
    provider = HistoricalFileMarketProvider(price_dir)
    costs = transaction_cost_policy_from_env()
    candle_cache = {}
    trades = []
    missing = []
    for target in manifest["targets"]:
        bar_path = (
            bars_dir / target["entry_date"] / f"{target['code']}.csv"
        )
        if not bar_path.exists():
            missing.append(target)
            continue
        code = target["code"]
        if code not in candle_cache:
            candle_cache[code] = {
                candle.date.date(): candle for candle in provider._candles(code)
            }
        candles = candle_cache[code]
        selection_date = date.fromisoformat(target["selection_date"])
        entry_date = date.fromisoformat(target["entry_date"])
        previous = candles.get(selection_date)
        entry_candle = candles.get(entry_date)
        index = session_index.get(entry_date)
        if previous is None or entry_candle is None or index is None:
            missing.append(target)
            continue
        signal = evaluate_morning_bars(bar_path, previous.close)
        baseline_entry = entry_candle.open
        baseline_gap = baseline_entry / previous.close - 1.0
        baseline_exit = _daily_exit(
            sessions, index, candles, baseline_entry, profit_target,
            stop_loss, maximum_holding_sessions, include_entry_day=True,
        )
        baseline_net = costs.net_return(baseline_entry, baseline_exit["price"])
        row = {
            **target,
            "baseline_eligible": abs(baseline_gap) <= 0.03,
            "qualified": signal["qualified"],
            "conditions": signal["conditions"],
            "opening_gap": baseline_gap,
            "baseline_entry": baseline_entry,
            "baseline_exit": baseline_exit,
            "baseline_net_return": baseline_net,
        }
        if signal["qualified"]:
            stable_entry = signal["entry_price"]
            stable_exit = _daily_exit(
                sessions, index, candles, stable_entry, profit_target,
                stop_loss, maximum_holding_sessions, include_entry_day=True,
                morning_high=signal["morning_high"],
                morning_low=signal["morning_low"],
            )
            row.update({
                "stable_entry": stable_entry,
                "stable_exit": stable_exit,
                "stable_net_return": costs.net_return(
                    stable_entry, stable_exit["price"]
                ),
            })
        trades.append(row)
    baseline_all = [
        row["baseline_net_return"] for row in trades
        if row["baseline_eligible"]
    ]
    baseline_qualified = [
        row["baseline_net_return"] for row in trades if row["qualified"]
    ]
    stable = [
        row["stable_net_return"] for row in trades if row["qualified"]
    ]
    result = {
        "strategy_version": manifest["strategy_version"],
        "profit_target": profit_target,
        "stop_loss": stop_loss,
        "maximum_holding_sessions": maximum_holding_sessions,
        "available_count": len(trades),
        "missing_count": len(missing),
        "qualified_count": len(stable),
        "rejected_count": len(trades) - len(stable),
        "exit_resolution": "DAILY_OHLC_AMBIGUOUS_AFTER_1000_ENTRY",
        "intraday_exit_simulator_ready": False,
        "intraday_exit_warning": (
            "Stored bars end at 09:55. Profit-target and stop-loss ordering "
            "after the 10:00 entry cannot be determined from daily OHLC."
        ),
        "summaries": {
            "BASELINE_ALL": _return_summary(baseline_all),
            "BASELINE_QUALIFIED": _return_summary(baseline_qualified),
            "STABLE_1000": _return_summary(stable),
        },
        "missing": missing,
        "trades": trades,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "morning_entry_backtest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def audit_intraday_exit_coverage(
    manifest_paths: list[Path],
    bars_dir: Path,
    output_dir: Path,
) -> dict:
    """Measure whether stored bars can resolve exits after a 10:00 entry."""
    targets = {}
    for manifest_path in manifest_paths:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in manifest.get("targets", []):
            key = (row["entry_date"], str(row["code"]).zfill(6))
            targets[key] = row
    available = complete_morning = after_entry = full_day = 0
    first_timestamp = last_timestamp = None
    missing = []
    for (entry_date, code), target in sorted(targets.items()):
        path = bars_dir / entry_date / f"{code}.csv"
        if not path.exists():
            missing.append(target)
            continue
        rows = _read_bars(path)
        if not rows:
            missing.append(target)
            continue
        available += 1
        first_timestamp = min(first_timestamp, rows[0]["timestamp"]) if first_timestamp else rows[0]["timestamp"]
        last_timestamp = max(last_timestamp, rows[-1]["timestamp"]) if last_timestamp else rows[-1]["timestamp"]
        morning = [row for row in rows if time(9) <= row["timestamp"].time() < time(10)]
        complete_morning += int(len(morning) >= 12)
        after = [row for row in rows if row["timestamp"].time() >= time(10)]
        after_entry += int(bool(after))
        full_day += int(bool(after) and rows[-1]["timestamp"].time() >= time(15, 20))
    result = {
        "schema_version": 1,
        "status": "READY" if available and full_day == available else "NOT_READY",
        "entry_time": "10:00",
        "target_count": len(targets),
        "available_count": available,
        "missing_count": len(missing),
        "complete_morning_count": complete_morning,
        "after_entry_count": after_entry,
        "full_day_count": full_day,
        "first_timestamp": first_timestamp.isoformat() if first_timestamp else None,
        "last_timestamp": last_timestamp.isoformat() if last_timestamp else None,
        "can_resolve_same_day_target_stop_order": bool(available and full_day == available),
        "score_and_weights_changed": False,
        "operational_orders": 0,
        "conclusion": (
            "10시 이후 분봉이 충분하여 최초 도달 순서를 판정할 수 있습니다."
            if available and full_day == available
            else "10시 이후 분봉이 없어 익절·손절 최초 도달 순서를 판정할 수 없습니다."
        ),
        "missing": missing,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "intraday_exit_coverage.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# S80 분봉 청산 검증 준비도", "",
        f"- 상태: {result['status']}",
        f"- 대상/보유 파일/누락: {len(targets)} / {available} / {len(missing)}",
        f"- 09:00~09:55 완성: {complete_morning}",
        f"- 10시 이후 포함: {after_entry}",
        f"- 장 마감 근처까지 포함: {full_day}",
        f"- 최초 익절·손절 순서 판정 가능: {result['can_resolve_same_day_target_stop_order']}",
        "", result["conclusion"], "",
        "> 점수·가중치·종목 수는 변경하지 않았고 실제 주문은 0건입니다.", "",
    ]
    (output_dir / "intraday_exit_coverage.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    return result


def run_s80_exit_bounds_backtest(
    manifest_paths: list[Path],
    bars_dir: Path,
    active_data_path: Path,
    output_dir: Path,
    profit_target: float = 0.05,
    stop_loss: float = 0.10,
    maximum_holding_sessions: int = 20,
) -> dict:
    """Bound 10:00-entry performance when post-entry intraday order is unknown."""
    targets = {}
    for path in manifest_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("targets", []):
            targets[(row["entry_date"], str(row["code"]).zfill(6))] = row
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    sessions_payload = json.loads((price_dir / "market_cap_top500.json").read_text(encoding="utf-8"))
    sessions = sorted(datetime.fromisoformat(value) for value in sessions_payload["sessions"])
    session_index = {value.date(): index for index, value in enumerate(sessions)}
    provider = HistoricalFileMarketProvider(price_dir)
    costs = transaction_cost_policy_from_env()
    candle_cache = {}
    trades, missing, rejected = [], [], []
    for (entry_date_raw, code), target in sorted(targets.items()):
        bars_path = bars_dir / entry_date_raw / f"{code}.csv"
        if not bars_path.exists():
            missing.append(target)
            continue
        if code not in candle_cache:
            candle_cache[code] = {row.date.date(): row for row in provider._candles(code)}
        candles = candle_cache[code]
        selection_date = date.fromisoformat(target["selection_date"])
        entry_date = date.fromisoformat(entry_date_raw)
        previous = candles.get(selection_date)
        entry_index = session_index.get(entry_date)
        if previous is None or entry_index is None:
            missing.append(target)
            continue
        try:
            signal = evaluate_morning_bars(bars_path, previous.close)
        except (OSError, ValueError):
            missing.append(target)
            continue
        if not signal["qualified"]:
            rejected.append({**target, "conditions": signal["conditions"]})
            continue
        scenario = {}
        for policy in ("PESSIMISTIC", "OPTIMISTIC"):
            exit_row = _bounded_daily_exit(
                sessions, entry_index, candles, signal["entry_price"],
                profit_target, stop_loss, maximum_holding_sessions,
                signal["morning_high"], signal["morning_low"], policy,
            )
            scenario[policy] = {
                **exit_row,
                "net_return": costs.net_return(signal["entry_price"], exit_row["price"]),
            }
        trades.append({
            **target, "entry_time": signal["entry_time"],
            "entry_price": signal["entry_price"], "conditions": signal["conditions"],
            "pessimistic": scenario["PESSIMISTIC"],
            "optimistic": scenario["OPTIMISTIC"],
            "same_result": scenario["PESSIMISTIC"] == scenario["OPTIMISTIC"],
        })
    result = {
        "schema_version": 1, "status": "RESEARCH_ONLY",
        "profit_target": profit_target, "stop_loss": stop_loss,
        "maximum_holding_sessions": maximum_holding_sessions,
        "target_count": len(targets), "available_count": len(targets) - len(missing),
        "qualified_count": len(trades), "rejected_count": len(rejected),
        "missing_count": len(missing),
        "ambiguous_trade_count": sum(not row["same_result"] for row in trades),
        "pessimistic": _exit_bound_summary([row["pessimistic"] for row in trades]),
        "optimistic": _exit_bound_summary([row["optimistic"] for row in trades]),
        "score_and_weights_changed": False, "operational_orders": 0,
        "conclusion": _bounds_conclusion(trades),
        "trades": trades, "missing": missing, "rejected": rejected,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "s80_exit_bounds.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "s80_exit_bounds.md").write_text(_exit_bounds_markdown(result), encoding="utf-8")
    return result


def run_s80_no_progress_backtest(
    exit_bounds_path: Path,
    bars_dir: Path,
    active_data_path: Path,
    output_dir: Path,
    progress_rate: float = 0.02,
    checkpoint_sessions: int = 5,
) -> dict:
    """Compare the frozen S80 exit with a five-session no-progress exit."""
    baseline = json.loads(exit_bounds_path.read_text(encoding="utf-8"))
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    sessions_payload = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )
    sessions = sorted(
        datetime.fromisoformat(value) for value in sessions_payload["sessions"]
    )
    session_index = {value.date(): index for index, value in enumerate(sessions)}
    provider = HistoricalFileMarketProvider(price_dir)
    costs = transaction_cost_policy_from_env()
    candle_cache = {}
    trades = []
    for trade in baseline.get("trades", []):
        code = str(trade["code"]).zfill(6)
        if code not in candle_cache:
            candle_cache[code] = {
                row.date.date(): row for row in provider._candles(code)
            }
        candles = candle_cache[code]
        selection_date = date.fromisoformat(trade["selection_date"])
        entry_date = date.fromisoformat(trade["entry_date"])
        previous = candles.get(selection_date)
        entry_index = session_index.get(entry_date)
        bars_path = bars_dir / trade["entry_date"] / f"{code}.csv"
        if previous is None or entry_index is None or not bars_path.exists():
            continue
        signal = evaluate_morning_bars(bars_path, previous.close)
        scenarios = {}
        for key, count_uncertain in (
            ("conservative", True),
            ("aggressive", False),
        ):
            exit_row = _no_progress_daily_exit(
                sessions, entry_index, candles, signal["entry_price"],
                baseline["profit_target"], baseline["stop_loss"],
                baseline["maximum_holding_sessions"],
                signal["morning_high"], signal["morning_low"],
                progress_rate, checkpoint_sessions, count_uncertain,
            )
            scenarios[key] = {
                **exit_row,
                "net_return": costs.net_return(
                    signal["entry_price"], exit_row["price"]
                ),
            }
        baseline_exit = trade["pessimistic"]
        trades.append({
            "selection_date": trade["selection_date"],
            "entry_date": trade["entry_date"],
            "code": code,
            "name": trade.get("name", ""),
            "entry_price": signal["entry_price"],
            "baseline": baseline_exit,
            **scenarios,
        })

    def scenario_summary(key):
        rows = [row[key] for row in trades]
        summary = _exit_bound_summary(rows)
        deltas = [
            row[key]["net_return"] - row["baseline"]["net_return"]
            for row in trades
        ]
        summary.update({
            "average_delta": statistics.fmean(deltas) if deltas else None,
            "improved_count": sum(value > 1e-12 for value in deltas),
            "worsened_count": sum(value < -1e-12 for value in deltas),
            "unchanged_count": sum(abs(value) <= 1e-12 for value in deltas),
            "no_progress_exit_count": sum(
                row[key]["reason"] == "NO_PROGRESS_EXIT" for row in trades
            ),
        })
        return summary

    result = {
        "schema_version": 1,
        "status": "RESEARCH_ONLY",
        "rule": {
            "progress_rate": progress_rate,
            "checkpoint_sessions": checkpoint_sessions,
            "checkpoint_close_must_be_at_or_below_entry": True,
        },
        "trade_count": len(trades),
        "baseline": _exit_bound_summary(
            [row["baseline"] for row in trades]
        ),
        "conservative": scenario_summary("conservative"),
        "aggressive": scenario_summary("aggressive"),
        "score_and_weights_changed": False,
        "operational_rule_changed": False,
        "operational_orders": 0,
        "trades": trades,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "s80_no_progress.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "s80_no_progress.md").write_text(
        _no_progress_markdown(result), encoding="utf-8"
    )
    return result


def _no_progress_markdown(result):
    pct = lambda value: "—" if value is None else f"{value:.2%}"
    lines = [
        "# S80 5거래일 무진전 청산 연구", "",
        "- 규칙: 5거래일까지 +2%에 도달하지 못하고 5일째 종가가 진입가 이하이면 청산",
        "- 기존 S80 점수·운영 청산 규칙은 변경하지 않음",
        "- 진입일 +2% 도달 여부가 일봉상 불확실한 경우 보수·공격 경계로 분리", "",
        "|구분|거래|승률|평균 순수익|중앙값|평균 손실|기존 대비|무진전 청산|개선/악화|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    base = result["baseline"]
    lines.append(
        f"|기존 S80|{base['trades']}|{pct(base['win_rate'])}|"
        f"{pct(base['average_return'])}|{pct(base['median_return'])}|"
        f"{pct(base['average_loss'])}|—|—|—|"
    )
    for key, label in (("conservative", "보수 경계"), ("aggressive", "공격 경계")):
        row = result[key]
        lines.append(
            f"|{label}|{row['trades']}|{pct(row['win_rate'])}|"
            f"{pct(row['average_return'])}|{pct(row['median_return'])}|"
            f"{pct(row['average_loss'])}|{pct(row['average_delta'])}|"
            f"{row['no_progress_exit_count']}|"
            f"{row['improved_count']}/{row['worsened_count']}|"
        )
    lines += ["", "> 이 결과는 기존 25건에서 만든 가설의 동일 표본 재검사입니다. 좋아 보여도 운영 승격 근거가 아니며 신규 표본에서 전진 검증해야 합니다.", ""]
    return "\n".join(lines)


def _bounded_daily_exit(
    sessions, entry_index, candles, entry_price, target_rate, stop_rate,
    maximum_holding, morning_high, morning_low, policy,
):
    target, stop = entry_price * (1 + target_rate), entry_price * (1 - stop_rate)
    final = None
    ambiguity_count = 0
    for offset in range(maximum_holding):
        if entry_index + offset >= len(sessions):
            break
        value = sessions[entry_index + offset].date()
        candle = candles.get(value)
        if candle is None:
            continue
        final = candle
        if offset > 0 and candle.open <= stop:
            return {"date": value.isoformat(), "price": candle.open, "reason": "STOP_GAP_OPEN",
                    "holding_sessions": offset + 1, "ambiguity_count": ambiguity_count}
        if offset > 0 and candle.open >= target:
            return {"date": value.isoformat(), "price": target, "reason": "TARGET_GAP_OPEN",
                    "holding_sessions": offset + 1, "ambiguity_count": ambiguity_count}
        target_hit, stop_hit = candle.high >= target, candle.low <= stop
        if offset == 0:
            target_confirmed = target_hit and morning_high < target
            stop_confirmed = stop_hit and morning_low > stop
            target_uncertain = target_hit and not target_confirmed
            stop_uncertain = stop_hit and not stop_confirmed
            ambiguity_count += int(target_uncertain or stop_uncertain)
            if policy == "PESSIMISTIC":
                target_hit, stop_hit = target_confirmed, stop_confirmed or stop_uncertain
            else:
                target_hit, stop_hit = target_confirmed or target_uncertain, stop_confirmed
        if target_hit and stop_hit:
            ambiguity_count += 1
            if policy == "PESSIMISTIC":
                return {"date": value.isoformat(), "price": stop, "reason": "BOTH_STOP_FIRST",
                        "holding_sessions": offset + 1, "ambiguity_count": ambiguity_count}
            return {"date": value.isoformat(), "price": target, "reason": "BOTH_TARGET_FIRST",
                    "holding_sessions": offset + 1, "ambiguity_count": ambiguity_count}
        if stop_hit:
            return {"date": value.isoformat(), "price": stop, "reason": "STOP_LOSS",
                    "holding_sessions": offset + 1, "ambiguity_count": ambiguity_count}
        if target_hit:
            return {"date": value.isoformat(), "price": target, "reason": "PROFIT_TARGET",
                    "holding_sessions": offset + 1, "ambiguity_count": ambiguity_count}
    if final is None:
        raise ValueError("no exit candle is available")
    return {"date": final.date.date().isoformat(), "price": final.close, "reason": "MAX_HOLD",
            "holding_sessions": maximum_holding, "ambiguity_count": ambiguity_count}


def _no_progress_daily_exit(
    sessions, entry_index, candles, entry_price, target_rate, stop_rate,
    maximum_holding, morning_high, morning_low, progress_rate=.02,
    checkpoint_sessions=5, count_uncertain_entry_progress=True,
):
    """Apply a preregistered no-progress exit on top of the S80 baseline.

    The position exits at the checkpoint close only when it has never reached
    ``progress_rate`` and that close is not above entry.  An entry-day daily
    high can contain movement before the 09:55 research entry, so callers can
    count that uncertain hit as progress (conservative intervention) or ignore
    it (aggressive intervention).  Target/stop handling otherwise follows the
    pessimistic daily-bar boundary used by the baseline audit.
    """
    target = entry_price * (1 + target_rate)
    stop = entry_price * (1 - stop_rate)
    progress = entry_price * (1 + progress_rate)
    progress_hit = False
    final = None
    ambiguity_count = 0
    for offset in range(maximum_holding):
        if entry_index + offset >= len(sessions):
            break
        value = sessions[entry_index + offset].date()
        candle = candles.get(value)
        if candle is None:
            continue
        final = candle
        if offset > 0 and candle.open <= stop:
            return {"date": value.isoformat(), "price": candle.open,
                    "reason": "STOP_GAP_OPEN", "holding_sessions": offset + 1,
                    "ambiguity_count": ambiguity_count,
                    "progress_hit": progress_hit}
        if offset > 0 and candle.open >= target:
            return {"date": value.isoformat(), "price": target,
                    "reason": "TARGET_GAP_OPEN", "holding_sessions": offset + 1,
                    "ambiguity_count": ambiguity_count,
                    "progress_hit": True}

        target_hit = candle.high >= target
        stop_hit = candle.low <= stop
        daily_progress_hit = candle.high >= progress
        if offset == 0:
            target_confirmed = target_hit and morning_high < target
            stop_confirmed = stop_hit and morning_low > stop
            target_uncertain = target_hit and not target_confirmed
            stop_uncertain = stop_hit and not stop_confirmed
            ambiguity_count += int(target_uncertain or stop_uncertain)
            target_hit = target_confirmed
            stop_hit = stop_confirmed or stop_uncertain

            progress_confirmed = daily_progress_hit and morning_high < progress
            progress_uncertain = daily_progress_hit and not progress_confirmed
            if progress_uncertain:
                ambiguity_count += 1
            daily_progress_hit = progress_confirmed or (
                progress_uncertain and count_uncertain_entry_progress
            )

        progress_hit = progress_hit or daily_progress_hit
        if target_hit and stop_hit:
            ambiguity_count += 1
            return {"date": value.isoformat(), "price": stop,
                    "reason": "BOTH_STOP_FIRST", "holding_sessions": offset + 1,
                    "ambiguity_count": ambiguity_count,
                    "progress_hit": progress_hit}
        if stop_hit:
            return {"date": value.isoformat(), "price": stop,
                    "reason": "STOP_LOSS", "holding_sessions": offset + 1,
                    "ambiguity_count": ambiguity_count,
                    "progress_hit": progress_hit}
        if target_hit:
            return {"date": value.isoformat(), "price": target,
                    "reason": "PROFIT_TARGET", "holding_sessions": offset + 1,
                    "ambiguity_count": ambiguity_count,
                    "progress_hit": True}
        if (
            offset + 1 == checkpoint_sessions
            and not progress_hit
            and candle.close <= entry_price
        ):
            return {"date": value.isoformat(), "price": candle.close,
                    "reason": "NO_PROGRESS_EXIT", "holding_sessions": offset + 1,
                    "ambiguity_count": ambiguity_count,
                    "progress_hit": False}
    if final is None:
        raise ValueError("no exit candle is available")
    return {"date": final.date.date().isoformat(), "price": final.close,
            "reason": "MAX_HOLD", "holding_sessions": maximum_holding,
            "ambiguity_count": ambiguity_count,
            "progress_hit": progress_hit}


def _exit_bound_summary(rows):
    returns = [row["net_return"] for row in rows]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    reasons = {}
    for row in rows:
        reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    average_win = statistics.fmean(wins) if wins else None
    average_loss = statistics.fmean(losses) if losses else None
    break_even = (
        abs(average_loss) / (average_win + abs(average_loss))
        if average_win is not None and average_loss is not None else None
    )
    return {
        **_return_summary(returns), "average_win": average_win,
        "average_loss": average_loss, "break_even_win_rate": break_even,
        "exit_reasons": reasons,
    }


def _bounds_conclusion(trades):
    if not trades:
        return "표본 부족"
    pessimistic = statistics.fmean(row["pessimistic"]["net_return"] for row in trades)
    optimistic = statistics.fmean(row["optimistic"]["net_return"] for row in trades)
    if optimistic <= 0:
        return "낙관 경계도 비양수이므로 현재 청산 규칙의 추가 연구 가치가 낮습니다."
    if pessimistic > 0:
        return "비관 경계도 양수이므로 분봉 추가 수집 가치가 있습니다."
    return "비관·낙관 경계의 부호가 달라 10시 이후 분봉 없이는 결론을 낼 수 없습니다."


def _exit_bounds_markdown(result):
    pct = lambda value: "—" if value is None else f"{value:.2%}"
    lines = ["# S80 익절·손절 경계 백테스트", "",
             f"- 대상/사용 가능/조건 통과: {result['target_count']} / {result['available_count']} / {result['qualified_count']}",
             f"- 순서 또는 진입 전 접촉 영향 표본: {result['ambiguous_trade_count']}", "",
             "|경계|거래|승률|평균 순수익|중앙값|평균 이익|평균 손실|손익분기 승률|", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for key, label in (("pessimistic", "비관"), ("optimistic", "낙관")):
        row = result[key]
        lines.append(f"|{label}|{row['trades']}|{pct(row['win_rate'])}|{pct(row['average_return'])}|{pct(row['median_return'])}|{pct(row['average_win'])}|{pct(row['average_loss'])}|{pct(row['break_even_win_rate'])}|")
    lines += ["", result["conclusion"], "",
              "> 진입 당일의 10시 이전 접촉과 같은 일봉 내 익절·손절 순서를 경계로 계산했습니다. 실제 주문은 0건입니다.", ""]
    return "\n".join(lines)


def _read_bars(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            rows.append({
                "timestamp": datetime.fromisoformat(raw["timestamp"]),
                "open": float(raw["open"]),
                "high": float(raw["high"]),
                "low": float(raw["low"]),
                "close": float(raw["close"]),
                "volume": float(raw["volume"]),
                "trading_value": (
                    float(raw["trading_value"])
                    if raw.get("trading_value") else None
                ),
                "spread": float(raw["spread"]) if raw.get("spread") else None,
            })
    return sorted(rows, key=lambda row: row["timestamp"])


def _daily_exit(
    sessions, entry_index, candles, entry_price, target_rate, stop_rate,
    maximum_holding, include_entry_day=False, morning_high=None, morning_low=None,
):
    target = entry_price * (1 + target_rate)
    stop = entry_price * (1 - stop_rate)
    final = None
    for offset in range(maximum_holding):
        value = sessions[entry_index + offset].date()
        candle = candles.get(value)
        if candle is None:
            continue
        final = candle
        stop_hit = candle.low <= stop
        target_hit = candle.high >= target
        if offset == 0 and not include_entry_day:
            stop_hit = target_hit = False
        if offset == 0 and morning_low is not None:
            stop_hit = stop_hit and morning_low > stop
            target_hit = target_hit and morning_high < target
        if stop_hit:
            return {"date": value.isoformat(), "price": stop,
                    "reason": "STOP_LOSS_10", "holding_sessions": offset + 1}
        if target_hit:
            return {"date": value.isoformat(), "price": target,
                    "reason": "PROFIT_TARGET_5", "holding_sessions": offset + 1}
    if final is None:
        raise ValueError("no exit candle is available")
    return {"date": final.date.date().isoformat(), "price": final.close,
            "reason": "MAX_HOLD_20", "holding_sessions": maximum_holding}


def _return_summary(values: list[float]) -> dict:
    if not values:
        return {"trades": 0, "win_rate": None, "average_return": None,
                "median_return": None}
    return {
        "trades": len(values),
        "win_rate": sum(value >= 0 for value in values) / len(values),
        "average_return": statistics.fmean(values),
        "median_return": statistics.median(values),
    }

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

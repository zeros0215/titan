"""Point-in-time scanner for volatility-contraction breakout candidates."""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from broker.historical import HistoricalFileMarketProvider
from config.sector_groups import SECTOR_GROUPS
from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data


@dataclass(frozen=True)
class PreBreakoutTrade:
    signal_date: str
    entry_date: str
    exit_date: str
    code: str
    name: str
    score: float
    entry_price: float
    exit_price: float
    holding_sessions: int
    exit_reason: str
    gross_return: float
    net_return: float
    win: bool
    initial_stop_rate: float
    industry_rs_score: float | None
    industry_momentum_score: float | None
    market_breadth: float
    market_breadth_change_5d: float
    conditions: dict[str, bool]
    grade: str
    market_regime: str
    profit_target_rate: float


def run_pre_breakout_monthly_validation(
    active_data_path: Path,
    output_dir: Path,
    month: str,
    profit_target: float = 0.10,
    stop_loss: float = 0.08,
    maximum_holding_sessions: int = 20,
    minimum_entry_gap: float = -0.01,
    maximum_entry_gap: float = 0.02,
) -> tuple[dict, Path]:
    month_start = datetime.strptime(month, "%Y-%m")
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    top500 = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )
    sessions = sorted(datetime.fromisoformat(value) for value in top500["sessions"])
    signal_dates = [
        value for value in sessions
        if value.strftime("%Y-%m") == month_start.strftime("%Y-%m")
    ]
    if not signal_dates:
        raise ValueError(f"{month}에 사용할 수 있는 거래일이 없습니다.")
    costs = transaction_cost_policy_from_env()
    trades: list[PreBreakoutTrade] = []
    signal_count = qualified_count = gap_excluded = duplicate_excluded = 0
    confirmation_excluded = 0
    busy_until: dict[str, datetime] = {}
    daily_dir = output_dir / "_daily"
    for signal in signal_dates:
        scan, _ = run_pre_breakout_scan(
            active_data_path, daily_dir, signal.date().isoformat()
        )
        qualified = [row for row in scan["candidates"] if row["qualified"]]
        signal_count += 1
        qualified_count += len(qualified)
        signal_index = sessions.index(signal)
        if signal_index + 2 >= len(sessions):
            continue
        confirmation_date = sessions[signal_index + 1]
        entry_date = sessions[signal_index + 2]
        for candidate in qualified:
            code = candidate["code"]
            if busy_until.get(code, datetime.min) >= entry_date:
                duplicate_excluded += 1
                continue
            candles = {
                item.date: item
                for item in _cached_candles(str(price_dir), code)
            }
            signal_candle = candles.get(signal)
            confirmation_candle = candles.get(confirmation_date)
            entry_candle = candles.get(entry_date)
            if (
                signal_candle is None or confirmation_candle is None
                or entry_candle is None
            ):
                continue
            prior_volumes = [
                candles.get(value).volume
                for value in sessions[max(0, signal_index - 19):signal_index + 1]
                if candles.get(value) is not None
            ]
            average_volume = (
                statistics.mean(prior_volumes) if prior_volumes else 0
            )
            if (
                confirmation_candle.close <= signal_candle.high
                or not average_volume
                or confirmation_candle.volume < average_volume * 1.5
                or confirmation_candle.volume > average_volume * 2.0
                or _close_location(confirmation_candle) < 0.70
            ):
                confirmation_excluded += 1
                continue
            entry_price = entry_candle.open
            entry_gap = entry_price / confirmation_candle.close - 1
            if not minimum_entry_gap <= entry_gap <= maximum_entry_gap:
                gap_excluded += 1
                continue
            exit_result = _monthly_exit(
                sessions, signal_index + 2, candles, entry_price,
                candidate["profit_target"], stop_loss,
                maximum_holding_sessions,
            )
            if exit_result is None:
                continue
            exit_date, exit_price, holding, reason, initial_stop_rate = exit_result
            gross = exit_price / entry_price - 1
            net = costs.net_return(entry_price, exit_price)
            trades.append(PreBreakoutTrade(
                signal_date=signal.date().isoformat(),
                entry_date=entry_date.date().isoformat(),
                exit_date=exit_date.date().isoformat(),
                code=code,
                name=candidate["name"],
                score=candidate["pre_breakout_score"],
                entry_price=entry_price,
                exit_price=exit_price,
                holding_sessions=holding,
                exit_reason=reason,
                gross_return=gross,
                net_return=net,
                win=net > 0,
                initial_stop_rate=initial_stop_rate,
                industry_rs_score=candidate["industry_rs_score"],
                industry_momentum_score=(
                    candidate["industry_momentum_score"]
                ),
                market_breadth=candidate["market_breadth"],
                market_breadth_change_5d=(
                    candidate["market_breadth_change_5d"]
                ),
                conditions=candidate["conditions"],
                grade=candidate["grade"],
                market_regime=candidate["market_regime"],
                profit_target_rate=candidate["profit_target"],
            ))
            busy_until[code] = exit_date
    returns = [trade.net_return for trade in trades]
    by_reason = {
        reason: sum(trade.exit_reason == reason for trade in trades)
        for reason in ("PROFIT_TARGET", "STOP_LOSS", "MA20_BREAK", "MAX_HOLD")
    }
    by_grade = {
        grade: {
            "trades": sum(trade.grade == grade for trade in trades),
            "wins": sum(
                trade.grade == grade and trade.win for trade in trades
            ),
        }
        for grade in ("A", "B")
    }
    for values in by_grade.values():
        values["win_rate"] = (
            values["wins"] / values["trades"]
            if values["trades"] else None
        )
    result = {
        "schema_version": 3,
        "engine": "PRE_BREAKOUT_REGIME_MONTHLY_V5",
        "month": month,
        "rules": {
            "confirmation": (
                "next session close above signal high; volume 1.5x-2.0x; "
                "close in upper 30% of daily range"
            ),
            "entry": (
                "session after confirmation open; gap from confirmation "
                "close between -1% and +2%"
            ),
            "profit_target": {
                "STRONG_UP": 0.12,
                "UP": profit_target,
                "SIDEWAYS": 0.07,
                "DOWN": None,
            },
            "stop_loss": (
                f"min({stop_loss:.0%}, 1.5 x entry ATR20), "
                "bounded to 4%-8%"
            ),
            "trend_exit": "close below MA20",
            "maximum_holding_sessions": maximum_holding_sessions,
            "same_stock_overlap": "disabled",
            "same_day_target_and_stop": "stop loss first (conservative)",
        },
        "signal_dates": signal_count,
        "qualified_signals": qualified_count,
        "gap_excluded": gap_excluded,
        "confirmation_excluded": confirmation_excluded,
        "duplicate_excluded": duplicate_excluded,
        "summary": {
            "trades": len(trades),
            "wins": sum(trade.win for trade in trades),
            "win_rate": (
                sum(trade.win for trade in trades) / len(trades)
                if trades else None
            ),
            "average_net_return": statistics.mean(returns) if returns else None,
            "median_net_return": statistics.median(returns) if returns else None,
            "total_compound_return": _compound(returns),
            "average_holding_sessions": (
                statistics.mean(trade.holding_sessions for trade in trades)
                if trades else None
            ),
            "exit_reasons": by_reason,
            "grades": by_grade,
        },
        "trades": [asdict(trade) for trade in trades],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pre_breakout_monthly.json"
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    archive_path = output_dir / f"pre_breakout_monthly_{month}.json"
    archive_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result, path


def _monthly_exit(
    sessions, entry_index, candles, entry_price,
    profit_target, stop_loss, maximum_holding_sessions,
):
    final_index = min(
        entry_index + maximum_holding_sessions - 1,
        len(sessions) - 1,
    )
    if final_index - entry_index + 1 < maximum_holding_sessions:
        return None
    target_price = entry_price * (1 + profit_target)
    entry_history = [
        candles.get(value)
        for value in sessions[max(0, entry_index - 20):entry_index + 1]
    ]
    entry_history = [item for item in entry_history if item is not None]
    atr20 = (
        statistics.mean(_true_ranges(entry_history))
        if len(entry_history) >= 20 else entry_price * stop_loss
    )
    adaptive_stop = min(stop_loss, max(0.04, 1.5 * atr20 / entry_price))
    stop_price = entry_price * (1 - adaptive_stop)
    for index in range(entry_index, final_index + 1):
        date = sessions[index]
        candle = candles.get(date)
        if candle is None:
            continue
        holding = index - entry_index + 1
        if candle.low <= stop_price:
            return date, stop_price, holding, "STOP_LOSS", adaptive_stop
        if candle.high >= target_price:
            return date, target_price, holding, "PROFIT_TARGET", adaptive_stop
        history = [
            candles.get(value) for value in sessions[max(0, index - 19):index + 1]
        ]
        history = [item for item in history if item is not None]
        if len(history) == 20:
            ma20 = statistics.mean(item.close for item in history)
            if candle.close < ma20:
                return date, candle.close, holding, "MA20_BREAK", adaptive_stop
    final = candles.get(sessions[final_index])
    if final is None:
        return None
    return (
        sessions[final_index], final.close, maximum_holding_sessions,
        "MAX_HOLD", adaptive_stop,
    )


def _compound(values):
    capital = 1.0
    for value in values:
        capital *= 1 + value
    return capital - 1


def _close_location(candle) -> float:
    spread = candle.high - candle.low
    return (candle.close - candle.low) / spread if spread > 0 else 1.0


def run_pre_breakout_scan(
    active_data_path: Path,
    output_dir: Path,
    as_of: str,
    surge_threshold: float = 0.15,
    forward_sessions: int = 10,
) -> tuple[dict, Path]:
    target = datetime.fromisoformat(as_of)
    universe_dir, price_dir, _ = load_active_backtest_data(active_data_path)
    top500 = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )
    sessions = sorted(datetime.fromisoformat(value) for value in top500["sessions"])
    if target not in sessions:
        raise ValueError(f"{target.date()}은 사용할 수 있는 로컬 거래일이 아닙니다.")
    session_index = sessions.index(target)
    eligible = set(top500["sessions"][target.isoformat()])
    names = _stock_names(price_dir, eligible)
    histories = {}
    for code in eligible:
        try:
            histories[code] = _cached_candles(str(price_dir), code)
        except FileNotFoundError:
            continue
    industry_context = _industry_context(
        target, session_index, sessions, histories
    )
    market_breadth = _market_breadth(target, histories)
    prior_breadth = (
        _market_breadth(sessions[session_index - 5], histories)
        if session_index >= 5 else market_breadth
    )
    breadth_change_5d = market_breadth - prior_breadth
    market_breadth60 = _market_above_ma(target, histories, 60)
    market_regime = _classify_market_regime(
        market_breadth, market_breadth60, breadth_change_5d
    )
    regime_rules = {
        "STRONG_UP": {"minimum_score": 65, "limit": 15, "target": 0.12},
        "UP": {"minimum_score": 70, "limit": 10, "target": 0.10},
        "SIDEWAYS": {"minimum_score": 80, "limit": 3, "target": 0.07},
        "DOWN": {"minimum_score": 100, "limit": 0, "target": 0.07},
    }
    active_regime_rule = regime_rules[market_regime]
    candidates = []
    for code, candles in histories.items():
        row = _candidate(
            code, names.get(code, code), candles, target,
            forward_sessions, surge_threshold,
            industry_context.get(code),
        )
        if row is not None:
            row["market_breadth"] = market_breadth
            precision_industry_ok = (
                row["industry_rs_score"] is None
                or (
                    row["industry_rs_score"] >= 60
                    and row["industry_momentum_score"] >= 50
                )
            )
            precision_market_ok = (
                market_breadth >= 0.55 and breadth_change_5d >= 0
            )
            balanced_market_ok = market_regime != "DOWN"
            row["market_regime_passed"] = balanced_market_ok
            row["market_breadth_change_5d"] = breadth_change_5d
            row["industry_regime_passed"] = precision_industry_ok
            row["precision_qualified"] = (
                row["precision_structure_qualified"]
                and precision_market_ok
                and precision_industry_ok
            )
            row["grade"] = (
                "A" if row["pre_breakout_score"] >= 80
                else "B" if row["pre_breakout_score"]
                >= active_regime_rule["minimum_score"]
                else "WATCH"
            )
            row["market_regime"] = market_regime
            row["profit_target"] = active_regime_rule["target"]
            row["qualified"] = (
                row["balanced_structure_qualified"]
                and balanced_market_ok
                and row["pre_breakout_score"]
                >= active_regime_rule["minimum_score"]
            )
            candidates.append(row)
    candidates.sort(
        key=lambda row: (
            not row["qualified"],
            -row["pre_breakout_score"],
            row["code"],
        )
    )
    accepted = 0
    for row in candidates:
        if not row["qualified"]:
            continue
        accepted += 1
        row["regime_rank"] = accepted
        if accepted > active_regime_rule["limit"]:
            row["qualified"] = False
            row["limit_excluded"] = True
    qualified = [row for row in candidates if row["qualified"]]
    validated = [
        row for row in qualified if row["future_max_return"] is not None
    ]
    result = {
        "schema_version": 4,
        "engine": "PRE_BREAKOUT_MARKET_REGIME_V5",
        "as_of": target.date().isoformat(),
        "universe_count": len(eligible),
        "analyzed_count": len(candidates),
        "qualified_count": len(qualified),
        "market_breadth": market_breadth,
        "market_breadth_change_5d": breadth_change_5d,
        "market_breadth_60d": market_breadth60,
        "market_regime": market_regime,
        "market_regime_rule": active_regime_rule,
        "rules": {
            "qualification": (
                "Market regime adjusts minimum score, candidate limit, and "
                "profit target. Mandatory trend, turnover, overheat, gap, risk. "
                "Industry strength and long-term highs are score features. "
                "Precision V4 remains available as precision_qualified."
            ),
            "close_above_ma20": True,
            "ma20_rising_sessions": 5,
            "distance_to_60d_high": [-0.03, 0.0],
            "return_5d": [-0.02, 0.08],
            "atr_5d_to_20d_max": 0.75,
            "prior_volume_5d_to_20d_max": 0.70,
            "current_volume_to_20d": [1.50, 2.50],
            "maximum_daily_return": 0.07,
            "maximum_atr20_to_close": 0.06,
            "turnover_to_20d": [1.50, 3.00],
            "distance_to_120d_high": [-0.05, 0.0],
            "distance_to_250d_high": [-0.10, 0.0],
            "maximum_gap": 0.04,
            "maximum_upper_wick_ratio": 0.35,
            "maximum_20d_drawdown": -0.12,
            "surge_definition": (
                f"next {forward_sessions} sessions maximum return "
                f">= {surge_threshold:.0%}"
            ),
        },
        "validation": {
            "sample_count": len(validated),
            "hits": sum(row["surge_hit"] for row in validated),
            "hit_rate": (
                sum(row["surge_hit"] for row in validated) / len(validated)
                if validated else None
            ),
            "average_future_max_return": (
                statistics.mean(row["future_max_return"] for row in validated)
                if validated else None
            ),
            "average_future_max_drawdown": (
                statistics.mean(row["future_max_drawdown"] for row in validated)
                if validated else None
            ),
        },
        "candidates": candidates[:100],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pre_breakout_scan.json"
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result, path


def _candidate(
    code, name, candles, target, forward_sessions,
    surge_threshold, industry_context,
):
    ordered = list(candles)
    positions = {candle.date: index for index, candle in enumerate(ordered)}
    index = positions.get(target)
    if index is None or index < 120:
        return None
    window = ordered[max(0, index - 250):index + 1]
    current = window[-1]
    closes = [item.close for item in window]
    volumes = [item.volume for item in window]
    returns = [
        closes[pos] / closes[pos - 1] - 1
        for pos in range(1, len(closes))
        if closes[pos - 1] > 0
    ]
    ma20 = statistics.mean(closes[-20:])
    prior_ma20 = statistics.mean(closes[-25:-5])
    ma5 = statistics.mean(closes[-5:])
    high60 = max(closes[-60:])
    distance_high = current.close / high60 - 1
    high120 = max(closes[-120:])
    distance_high120 = current.close / high120 - 1
    distance_high250 = (
        current.close / max(closes[-250:]) - 1
        if len(closes) >= 250 else None
    )
    return5 = current.close / closes[-6] - 1
    atr5 = statistics.mean(_true_ranges(window[-6:]))
    atr20 = statistics.mean(_true_ranges(window[-21:]))
    avg_volume20 = statistics.mean(volumes[-21:-1])
    dry_ratio = (
        statistics.mean(volumes[-6:-1]) / avg_volume20
        if avg_volume20 else 0
    )
    volume_ratio = current.volume / avg_volume20 if avg_volume20 else 0
    turnovers = [item.close * item.volume for item in window]
    avg_turnover20 = statistics.mean(turnovers[-21:-1])
    turnover_ratio = (
        turnovers[-1] / avg_turnover20 if avg_turnover20 else 0
    )
    daily_return = current.close / closes[-2] - 1
    gap_return = current.open / closes[-2] - 1
    spread = current.high - current.low
    upper_wick_ratio = (
        (current.high - current.close) / spread if spread > 0 else 0
    )
    high20 = max(closes[-20:])
    drawdown20 = current.close / high20 - 1
    conditions = {
        "close_above_ma20": current.close > ma20,
        "ma5_above_ma20": ma5 > ma20,
        "ma20_rising": ma20 > prior_ma20,
        "near_60d_high": -0.03 <= distance_high <= 0,
        "controlled_5d_return": -0.02 <= return5 <= 0.08,
        "atr_contraction": atr20 > 0 and atr5 / atr20 <= 0.75,
        "volume_dry_up": dry_ratio <= 0.70,
        "early_volume_expansion": 1.50 <= volume_ratio <= 2.50,
        "not_already_surged": daily_return < 0.07,
        "risk_contained": atr20 / current.close <= 0.06,
        "turnover_expansion": 1.50 <= turnover_ratio <= 3.00,
        "near_120d_high": -0.05 <= distance_high120 <= 0,
        "near_250d_high": (
            distance_high250 is None or -0.10 <= distance_high250 <= 0
        ),
        "gap_contained": gap_return <= 0.04,
        "upper_wick_contained": upper_wick_ratio <= 0.35,
        "drawdown_contained": drawdown20 >= -0.12,
    }
    weights = {
        "close_above_ma20": 10,
        "ma5_above_ma20": 5,
        "ma20_rising": 10,
        "near_60d_high": 15,
        "controlled_5d_return": 10,
        "atr_contraction": 15,
        "volume_dry_up": 10,
        "early_volume_expansion": 15,
        "not_already_surged": 5,
        "risk_contained": 5,
        "turnover_expansion": 15,
        "near_120d_high": 10,
        "near_250d_high": 5,
        "gap_contained": 5,
        "upper_wick_contained": 5,
        "drawdown_contained": 5,
    }
    score = 100 * (
        sum(weights[key] for key, passed in conditions.items() if passed)
        / sum(weights.values())
    )
    industry_rs_score = (
        industry_context["stock_rs"] if industry_context is not None else None
    )
    industry_momentum_score = (
        industry_context["industry_momentum"]
        if industry_context is not None else None
    )
    if industry_rs_score is not None:
        score = min(
            100,
            score * 0.85
            + industry_rs_score * 0.10
            + industry_momentum_score * 0.05,
        )
    future = ordered[index + 1:index + forward_sessions + 1]
    future_max = (
        max(item.high for item in future) / current.close - 1
        if len(future) == forward_sessions else None
    )
    future_drawdown = (
        min(item.low for item in future) / current.close - 1
        if len(future) == forward_sessions else None
    )
    precision_structure_qualified = (
        sum(conditions.values()) >= 12
        and conditions["close_above_ma20"]
        and conditions["ma5_above_ma20"]
        and conditions["ma20_rising"]
        and conditions["early_volume_expansion"]
        and conditions["not_already_surged"]
        and conditions["risk_contained"]
        and conditions["turnover_expansion"]
        and conditions["near_120d_high"]
        and conditions["gap_contained"]
        and conditions["upper_wick_contained"]
        and conditions["drawdown_contained"]
    )
    balanced_structure_qualified = (
        conditions["close_above_ma20"]
        and conditions["ma20_rising"]
        and conditions["turnover_expansion"]
        and conditions["not_already_surged"]
        and conditions["risk_contained"]
        and conditions["gap_contained"]
        and conditions["drawdown_contained"]
    )
    return {
        "code": code,
        "name": name,
        "pre_breakout_score": round(score, 2),
        "qualified": False,
        "balanced_structure_qualified": balanced_structure_qualified,
        "precision_structure_qualified": precision_structure_qualified,
        "conditions_passed": sum(conditions.values()),
        "conditions_total": len(conditions),
        "conditions": conditions,
        "close": current.close,
        "return_5d": return5,
        "distance_to_60d_high": distance_high,
        "distance_to_120d_high": distance_high120,
        "distance_to_250d_high": distance_high250,
        "atr_5d_to_20d": atr5 / atr20 if atr20 else None,
        "prior_volume_5d_to_20d": dry_ratio,
        "current_volume_to_20d": volume_ratio,
        "turnover_to_20d": turnover_ratio,
        "gap_return": gap_return,
        "upper_wick_ratio": upper_wick_ratio,
        "drawdown_20d": drawdown20,
        "industry_rs_score": industry_rs_score,
        "industry_momentum_score": industry_momentum_score,
        "future_max_return": future_max,
        "future_max_drawdown": future_drawdown,
        "surge_hit": (
            future_max >= surge_threshold if future_max is not None else None
        ),
    }


def _true_ranges(candles):
    output = []
    for previous, current in zip(candles, candles[1:]):
        output.append(max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        ))
    return output


def _industry_context(target, index, sessions, histories):
    if index < 20:
        return {}
    prior = sessions[index - 20]
    relative = {}
    group_momentum = {}
    stock_group = {}
    for group, members in SECTOR_GROUPS.items():
        values = {}
        for code in members:
            candles = {item.date: item for item in histories.get(code, ())}
            first, last = candles.get(prior), candles.get(target)
            if first is not None and last is not None and first.close > 0:
                values[code] = last.close / first.close - 1
                stock_group[code] = group
        if len(values) >= 3:
            group_momentum[group] = statistics.median(values.values())
        for code, value in values.items():
            peers = [item for peer, item in values.items() if peer != code]
            if len(peers) >= 2:
                relative[code] = value - statistics.median(peers)
    if len(relative) < 2 or not group_momentum:
        return {}
    ordered = sorted(relative.values())
    momentum_ordered = sorted(group_momentum.values())
    output = {}
    for code, value in relative.items():
        group = stock_group[code]
        momentum = group_momentum[group]
        output[code] = {
            "stock_rs": round(
                100 * ordered.index(value) / (len(ordered) - 1), 2
            ),
            "industry_momentum": round(
                100 * momentum_ordered.index(momentum)
                / max(1, len(momentum_ordered) - 1),
                2,
            ),
        }
    return output


def _market_breadth(target, histories):
    return _market_above_ma(target, histories, 20)


def _market_above_ma(target, histories, horizon):
    passed = total = 0
    for candles in histories.values():
        ordered = list(candles)
        positions = {item.date: index for index, item in enumerate(ordered)}
        index = positions.get(target)
        if index is None or index < horizon - 1:
            continue
        total += 1
        passed += ordered[index].close > statistics.mean(
            item.close
            for item in ordered[index - horizon + 1:index + 1]
        )
    return passed / total if total else 0.0


def _classify_market_regime(breadth20, breadth60, change5):
    if breadth20 >= 0.60 and breadth60 >= 0.55 and change5 >= 0:
        return "STRONG_UP"
    if breadth20 >= 0.50 and breadth60 >= 0.45:
        return "UP"
    if breadth20 >= 0.40:
        return "SIDEWAYS"
    return "DOWN"


def _stock_names(price_dir, eligible):
    names = {}
    for code in eligible:
        path = price_dir / f"{code}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            names[code] = payload.get("name") or code
    return names


@lru_cache(maxsize=2048)
def _cached_candles(price_dir: str, code: str):
    """Reuse immutable price histories during month/year validation."""
    provider = HistoricalFileMarketProvider(Path(price_dir))
    return tuple(provider._candles(code))

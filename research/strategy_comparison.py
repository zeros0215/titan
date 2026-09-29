"""Research-only comparison of independent stock-selection algorithms."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from config.transaction_costs import transaction_cost_policy_from_env
from release.backtest_data import load_active_backtest_data


ROOT = Path(__file__).resolve().parent.parent
ACTIVE_DATA = ROOT / "output" / "release" / "backtest_data.json"
OUTPUT = ROOT / "output" / "strategy_comparison"
S80_RUNS = ROOT / "output" / "kis_manual_tests" / "runs"
STRATEGIES = {
    "S80": "현재 S80",
    "RS_PULLBACK_V1": "상대강도 + 단기 눌림목",
    "VOLUME_BREAKOUT_V1": "거래량 + 가격 돌파",
    "TREND_REVERSION_V1": "추세 필터 + 평균회귀",
}


def run_strategy_comparison(year: int = 2026) -> dict:
    """Run a frozen, point-in-time comparison without changing operations."""
    _, price_dir, _ = load_active_backtest_data(ACTIVE_DATA)
    top = json.loads((price_dir / "market_cap_top500.json").read_text(encoding="utf-8"))
    sessions = sorted(str(value)[:10] for value in top["sessions"])
    signal_dates = [value for value in sessions if value.startswith(f"{year}-")]
    codes = {
        str(code).zfill(6)
        for value in signal_dates
        for code in (top["sessions"].get(value) or top["sessions"].get(value + "T00:00:00") or [])[:300]
    }
    histories = _load_histories(price_dir, codes)
    s80 = _load_s80_candidates(year)
    trades = defaultdict(list)
    ranks = defaultdict(lambda: defaultdict(list))
    candidate_days = defaultdict(int)
    for signal_date in signal_dates:
        session_index = sessions.index(signal_date)
        if session_index + 1 >= len(sessions):
            continue
        universe = [
            str(code).zfill(6)
            for code in (top["sessions"].get(signal_date) or top["sessions"].get(signal_date + "T00:00:00") or [])[:300]
        ]
        feature_rows = [row for code in universe if (row := _features(code, signal_date, histories))]
        ranked = {
            "S80": s80.get(signal_date, []),
            "RS_PULLBACK_V1": _rank(feature_rows, _rs_pullback),
            "VOLUME_BREAKOUT_V1": _rank(feature_rows, _volume_breakout),
            "TREND_REVERSION_V1": _rank(feature_rows, _trend_reversion),
        }
        for strategy, rows in ranked.items():
            if rows:
                candidate_days[strategy] += 1
            for rank, row in enumerate(rows[:50], 1):
                _collect_rank_returns(ranks[strategy], rank, row["code"], signal_date, sessions, histories)
            for row in rows[:5]:
                trade = _simulate_trade(row["code"], signal_date, sessions, histories)
                if trade:
                    trades[strategy].append(trade)
    payload = {
        "schema_version": 1,
        "research_only": True,
        "operational_strategy_unchanged": True,
        "version": "V1-RESEARCH",
        "year": year,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "coverage_end": sessions[-1] if sessions else None,
        "common_rules": {
            "universe": "POINT_IN_TIME_MARKET_CAP_TOP_300",
            "maximum_candidates": 5,
            "entry": "NEXT_SESSION_OPEN",
            "maximum_absolute_gap": 0.03,
            "profit_target": 0.05,
            "stop_loss": 0.10,
            "maximum_holding_sessions": 20,
        },
        "strategies": [
            {
                "id": key,
                "label": label,
                "candidate_days": candidate_days[key],
                **_summary(trades[key]),
                "rank_buckets": _rank_summary(ranks[key]),
            }
            for key, label in STRATEGIES.items()
        ],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"{year}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def _load_histories(price_dir: Path, codes: set[str]) -> dict:
    result = {}
    for code in codes:
        path = price_dir / f"{code}.json"
        try:
            candles = json.loads(path.read_text(encoding="utf-8"))["candles"]
        except (OSError, KeyError, json.JSONDecodeError):
            continue
        rows = [{**item, "date": str(item["date"])[:10]} for item in candles]
        result[code] = {"rows": rows, "index": {row["date"]: i for i, row in enumerate(rows)}}
    return result


def _load_s80_candidates(year: int) -> dict[str, list[dict]]:
    latest = {}
    for path in S80_RUNS.glob(f"LOCAL_{year}*_H20_V1_3_S80_N7_TP5_SL10_CANDIDATE_TP5_SL10.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        date = str(row.get("as_of", ""))[:10]
        if not date or (date in latest and latest[date][0] >= path.stat().st_mtime):
            continue
        candidates = (row.get("selected_candidates") or []) + (row.get("observation_candidates") or [])
        latest[date] = (path.stat().st_mtime, sorted(
            ({"code": str(item["code"]).zfill(6), "score": float(item.get("total_score") or 0)} for item in candidates),
            key=lambda item: item["score"], reverse=True,
        ))
    return {date: value[1] for date, value in latest.items()}


def _features(code: str, date: str, histories: dict) -> dict | None:
    history = histories.get(code)
    index = history and history["index"].get(date)
    if index is None or index < 120:
        return None
    rows = history["rows"]
    window = rows[index - 120:index + 1]
    closes = [float(row["close"]) for row in window]
    volumes = [float(row["volume"]) for row in window]
    current = window[-1]
    high, low, close = map(float, (current["high"], current["low"], current["close"]))
    true_ranges = [
        max(float(window[i]["high"]) - float(window[i]["low"]), abs(float(window[i]["high"]) - closes[i-1]), abs(float(window[i]["low"]) - closes[i-1]))
        for i in range(1, len(window))
    ]
    gains = [max(0.0, closes[i] - closes[i-1]) for i in range(-14, 0)]
    losses = [max(0.0, closes[i-1] - closes[i]) for i in range(-14, 0)]
    avg_gain, avg_loss = statistics.mean(gains), statistics.mean(losses)
    rsi = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    span = high - low
    average_volume20 = statistics.mean(volumes[-21:-1])
    pullback_volume20 = statistics.mean(volumes[-20:])
    return {
        "code": code, "close": close,
        "ma20": statistics.mean(closes[-20:]), "ma60": statistics.mean(closes[-60:]),
        "ret3": close / closes[-4] - 1, "ret60": close / closes[-61] - 1,
        "ret120": close / closes[0] - 1, "rsi14": rsi,
        "atr20": statistics.mean(true_ranges[-20:]),
        "high20_prior": max(float(row["high"]) for row in window[-21:-1]),
        "high60": max(float(row["high"]) for row in window[-60:]),
        "volume_ratio": volumes[-1] / average_volume20 if average_volume20 else 0.0,
        "pullback_volume_ratio": statistics.mean(volumes[-3:]) / pullback_volume20 if pullback_volume20 else 0.0,
        "trading_value": close * volumes[-1],
        "close_location": (close - low) / span if span else 0.5,
        "upper_wick": (high - close) / span if span else 0.0,
    }


def _rank(rows, scorer):
    scored = [value for row in rows if (value := scorer(row)) is not None]
    return sorted(scored, key=lambda item: item["score"], reverse=True)


def _rs_pullback(row):
    if not (row["ma20"] > row["ma60"] and row["close"] > row["ma60"] and -.06 <= row["ret3"] <= -.01 and row["pullback_volume_ratio"] <= .90 and row["close"] >= row["high60"] * .85):
        return None
    return {"code": row["code"], "score": .6 * row["ret60"] + .4 * row["ret120"]}


def _volume_breakout(row):
    if not (row["close"] >= row["high20_prior"] and row["close"] >= row["high60"] * .97 and row["volume_ratio"] >= 1.5 and row["trading_value"] >= 5_000_000_000 and row["close_location"] >= .70 and row["upper_wick"] <= .25):
        return None
    return {"code": row["code"], "score": row["volume_ratio"] + row["close_location"]}


def _trend_reversion(row):
    oversold = row["ret3"] <= -.04 or (-row["ret3"] * row["close"] >= 1.5 * row["atr20"])
    if not (row["ma20"] > row["ma60"] and row["close"] > row["ma60"] and row["rsi14"] <= 40 and oversold and row["close"] >= row["high60"] * .80 and row["trading_value"] >= 5_000_000_000):
        return None
    return {"code": row["code"], "score": -row["ret3"] + (40 - row["rsi14"]) / 100}


def _simulate_trade(code, signal_date, sessions, histories):
    history = histories.get(code)
    signal_index = sessions.index(signal_date)
    entry_date = sessions[signal_index + 1]
    entry_row = history and history["rows"][history["index"].get(entry_date)] if history and entry_date in history["index"] else None
    signal_row = history and history["rows"][history["index"].get(signal_date)] if history and signal_date in history["index"] else None
    if not entry_row or not signal_row:
        return None
    entry = float(entry_row["open"])
    if abs(entry / float(signal_row["close"]) - 1) > .03:
        return None
    target, stop = entry * 1.05, entry * .90
    available = min(20, len(sessions) - signal_index - 1)
    final_row = None
    final_date = None
    for offset in range(1, available + 1):
        date = sessions[signal_index + offset]
        if date not in history["index"]:
            continue
        row = history["rows"][history["index"][date]]
        final_row, final_date = row, date
        if float(row["low"]) <= stop:
            return _trade(entry, stop, signal_date, date)
        if float(row["high"]) >= target:
            return _trade(entry, target, signal_date, date)
    if available == 20 and final_row is not None:
        return _trade(entry, float(final_row["close"]), signal_date, final_date)
    return None


def _trade(entry, exit_price, signal_date, exit_date):
    net = transaction_cost_policy_from_env().net_return(entry, exit_price)
    return {"signal_date": signal_date, "exit_date": exit_date, "net_return": net}


def _collect_rank_returns(target, rank, code, signal_date, sessions, histories):
    bucket = "1-5" if rank <= 5 else "6-10" if rank <= 10 else "11-20" if rank <= 20 else "21-50"
    history, signal_index = histories.get(code), sessions.index(signal_date)
    if not history or signal_index + 1 >= len(sessions):
        return
    entry_date = sessions[signal_index + 1]
    if entry_date not in history["index"]:
        return
    entry = float(history["rows"][history["index"][entry_date]]["open"])
    values = {}
    for horizon in (1, 5, 10, 20):
        if signal_index + horizon >= len(sessions):
            continue
        date = sessions[signal_index + horizon]
        if date in history["index"]:
            values[str(horizon)] = float(history["rows"][history["index"][date]]["close"]) / entry - 1
    target[bucket].append(values)


def _summary(trades):
    returns = [row["net_return"] for row in trades]
    wins, losses = [x for x in returns if x > 0], [x for x in returns if x < 0]
    daily = defaultdict(list)
    for row in trades:
        daily[row["signal_date"]].append(row["net_return"])
    equity = peak = 1.0
    drawdown = 0.0
    for date in sorted(daily):
        equity *= 1 + statistics.mean(daily[date])
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
    return {
        "trades": len(returns), "win_rate": len(wins) / len(returns) if returns else None,
        "average_net_return": statistics.mean(returns) if returns else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "payoff_ratio": statistics.mean(wins) / abs(statistics.mean(losses)) if wins and losses else None,
        "maximum_drawdown": drawdown if returns else None,
    }


def _rank_summary(buckets):
    result = []
    for label in ("1-5", "6-10", "11-20", "21-50"):
        rows = buckets[label]
        result.append({"bucket": label, "samples": len(rows), **{
            f"return_{horizon}d": statistics.mean(values) if (values := [row[str(horizon)] for row in rows if str(horizon) in row]) else None
            for horizon in (1, 5, 10, 20)
        }})
    return result

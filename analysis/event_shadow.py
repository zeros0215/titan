"""Performance tracking for saved 10:00 event-candidate snapshots."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path


def load_event_runs(run_dir: Path) -> list[dict]:
    runs = []
    if not run_dir.exists():
        return runs
    for path in sorted(run_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            datetime.fromisoformat(payload["executed_at"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        runs.append(payload)
    return runs


def summarize_event_shadow(
    runs: list[dict],
    price_dir: Path | None,
    profit_target: float = 0.05,
    stop_loss: float = 0.10,
    maximum_sessions: int = 20,
) -> dict:
    """Track one closest-to-10:00 ENTRY snapshot per date and symbol.

    Daily candles cannot prove whether an entry-day high/low happened before or
    after 10:00, so exits begin on the following session. This deliberately
    avoids look-ahead contamination.
    """
    chosen: dict[tuple[str, str], tuple[float, dict, dict]] = {}
    for run in runs:
        if run.get("snapshot_phase") != "ENTRY":
            continue
        executed = datetime.fromisoformat(run["executed_at"])
        distance = abs(
            executed.hour * 3600
            + executed.minute * 60
            + executed.second
            - 10 * 3600
        )
        for candidate in run.get("candidates", []):
            key = (executed.date().isoformat(), str(candidate["code"]).zfill(6))
            previous = chosen.get(key)
            if previous is None or distance < previous[0]:
                chosen[key] = (distance, run, candidate)

    trades = []
    for (entry_date, code), (_, run, candidate) in sorted(chosen.items()):
        entry_price = _number(candidate.get("close"))
        candles = _candles(price_dir, code)
        if entry_price is None:
            continue
        future = [
            candle for candle in candles
            if str(candle.get("date", ""))[:10] > entry_date
        ][:maximum_sessions]
        exit_price = None
        exit_date = None
        exit_reason = "TRACKING"
        for candle in future:
            low = _number(candle.get("low"))
            high = _number(candle.get("high"))
            # Conservative ordering when both thresholds occur in one daily bar.
            if low is not None and low <= entry_price * (1 - stop_loss):
                exit_price = entry_price * (1 - stop_loss)
                exit_reason = "STOP_LOSS"
            elif high is not None and high >= entry_price * (1 + profit_target):
                exit_price = entry_price * (1 + profit_target)
                exit_reason = "TAKE_PROFIT"
            if exit_price is not None:
                exit_date = str(candle["date"])[:10]
                break
        if exit_price is None and len(future) >= maximum_sessions:
            exit_price = _number(future[-1].get("close"))
            exit_date = str(future[-1]["date"])[:10]
            exit_reason = "TIME_EXIT"
        latest_price = (
            _number(future[-1].get("close")) if future else entry_price
        )
        completed = exit_price is not None
        net_return = exit_price / entry_price - 1 if completed else None
        trades.append({
            "entry_date": entry_date,
            "entry_time": run["executed_at"],
            "code": code,
            "name": candidate.get("name", code),
            "cohort": candidate.get("cohort", "SELECTED"),
            "selection_date": candidate.get("selection_date"),
            "hypothetical_entry": bool(candidate.get("hypothetical_entry")),
            "entry_price": entry_price,
            "latest_price": latest_price,
            "exit_date": exit_date,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "net_return": net_return,
            "win": bool(completed and net_return > 0),
            "headline_count": candidate.get("headline_count", 0),
            "prefilter": candidate.get("prefilter"),
        })

    completed = [trade for trade in trades if trade["net_return"] is not None]
    wins = sum(trade["win"] for trade in completed)
    return {
        "strategy": {
            "entry": "09:50~10:10 저장 스냅샷 중 10시에 가장 가까운 가격",
            "profit_target": profit_target,
            "stop_loss": stop_loss,
            "maximum_sessions": maximum_sessions,
            "same_day_exit_evaluation": False,
        },
        "snapshots": len(runs),
        "entry_candidates": len(trades),
        "completed": len(completed),
        "wins": wins,
        "win_rate": wins / len(completed) if completed else None,
        "average_net_return": (
            sum(trade["net_return"] for trade in completed) / len(completed)
            if completed else None
        ),
        "trades": trades,
    }


def summarize_operational_shadow(
    runs: list[dict],
    price_dir: Path | None,
    profit_target: float = 0.05,
    stop_loss: float = 0.10,
    maximum_sessions: int = 20,
) -> dict:
    """Track only S80 quotes that passed the entry-gap rule."""
    normalized = [{
        **run,
        "candidates": [
            {**candidate, "close": candidate.get("entry_price")}
            for candidate in run.get("candidates", [])
            if candidate.get("entry_allowed") is True
            and candidate.get("cohort", "SELECTED") == "SELECTED"
        ],
    } for run in runs]
    summary = summarize_event_shadow(
        normalized, price_dir, profit_target, stop_loss, maximum_sessions,
    )
    summary["strategy"]["entry"] = (
        "S80 선정군의 09:50~10:10 저장 가격 중 10시에 가장 가까운 값"
    )
    return summary


def summarize_observation_shadow(
    runs: list[dict],
    price_dir: Path | None,
    profit_target: float = 0.05,
    stop_loss: float = 0.10,
    maximum_sessions: int = 20,
) -> dict:
    """Track observation names as hypothetical 09:50~10:10 entries only."""
    normalized = [{
        **run,
        "candidates": [
            {**candidate, "close": candidate.get("entry_price")}
            for candidate in run.get("candidates", [])
            if candidate.get("cohort") == "OBSERVATION"
            and candidate.get("hypothetical_entry") is True
        ],
    } for run in runs]
    summary = summarize_event_shadow(
        normalized, price_dir, profit_target, stop_loss, maximum_sessions,
    )
    summary["strategy"]["entry"] = (
        "observation quote from 09:50~10:10 used as hypothetical entry"
    )
    summary["research_only"] = True
    summary["operational_orders"] = 0
    return summary


def _candles(price_dir: Path | None, code: str) -> list[dict]:
    if price_dir is None:
        return []
    path = price_dir / f"{code}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("candles", [])
    except (OSError, TypeError, json.JSONDecodeError):
        return []


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

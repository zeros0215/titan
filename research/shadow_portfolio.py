"""Forward-only, no-order shadow operation for the frozen A/C portfolio."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from benchmark.equal_weight import HistoricalEqualWeightBenchmarkProvider
from broker.historical import HistoricalFileMarketProvider
from config.selection_criteria import SelectionCriteria
from config.transaction_costs import transaction_cost_policy_from_env
from domain.enums import MarketType
from release.backtest_data import load_active_backtest_data
from runner.factory import create_walk_forward_engine


def run_shadow_portfolio(
    as_of: datetime,
    active_data_path: Path,
    freeze_path: Path,
    state_path: Path,
    create_signals: bool = True,
) -> dict:
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    _verify_freeze(freeze)
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    provider = HistoricalFileMarketProvider(price_dir)
    benchmark = HistoricalEqualWeightBenchmarkProvider(price_dir)
    sessions_payload = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )["sessions"]
    sessions = [
        datetime.fromisoformat(value) for value in sorted(sessions_payload)
        if datetime.fromisoformat(value) <= as_of
    ]
    if not sessions:
        raise ValueError("no market session on or before as_of")
    signal_at = sessions[-1]
    state = _load_state(state_path, freeze)
    _mature_positions(
        state["positions"], signal_at, provider, benchmark, sessions,
    )
    if create_signals and signal_at.isoformat() not in state["run_dates"]:
        selections = _select_frozen_candidates(
            signal_at, active_data_path, freeze,
        )
        _allocate(state["positions"], selections, freeze, signal_at)
        state["run_dates"].append(signal_at.isoformat())
    state["updated_at"] = as_of.isoformat()
    state["summary"] = _summary(state["positions"])
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return state


def save_weekly_snapshot(state: dict, output_dir: Path) -> dict:
    """Save a one-page, no-order progress snapshot for forward validation."""
    updated_at = datetime.fromisoformat(state["updated_at"])
    positions = state.get("positions", [])
    signal_date = state.get("run_dates", [updated_at.isoformat()])[-1][:10]
    live = [row for row in positions if row["status"] in {"PENDING_ENTRY", "OPEN"}]
    closed = [row for row in positions if row["status"] == "CLOSED"]
    current_signals = [
        row for row in positions
        if row.get("selected_at", "")[:10] == signal_date
        and row["status"] != "SKIPPED"
    ]
    by_source = {}
    for source in ("A", "C"):
        rows = [row for row in closed if row["source"] == source]
        returns = [float(row["net_return"]) for row in rows]
        excess = [float(row["excess_return"]) for row in rows]
        positive = [max(0.0, value) for value in returns]
        by_source[source] = {
            "closed": len(rows),
            "win_rate": sum(value > 0 for value in returns) / len(returns) if returns else None,
            "average_net_return": sum(returns) / len(returns) if returns else None,
            "average_excess_return": sum(excess) / len(excess) if excess else None,
            "top3_positive_contribution": (
                sum(sorted(positive, reverse=True)[:3]) / sum(positive)
                if sum(positive) else None
            ),
        }
    recent_cutoff = (updated_at - timedelta(days=365)).date().isoformat()
    recent = [row for row in closed if row.get("exit_date", "")[:10] >= recent_cutoff]
    recent_returns = [float(row["net_return"]) for row in recent]
    closed_count = len(closed)
    promotion_status = (
        "REVIEW_READY" if closed_count >= 100
        else "WATCH" if closed_count >= 30 else "NOT_ELIGIBLE"
    )
    snapshot = {
        "schema_version": 1,
        "as_of": updated_at.isoformat(),
        "signal_date": signal_date,
        "promotion_status": promotion_status,
        "progress": {"closed": closed_count, "interim_target": 30, "review_target": 100},
        "new_signals": current_signals,
        "live_positions": live,
        "by_source": by_source,
        "horizons": state.get("summary", {}).get("horizons", {}),
        "recent_12_months": {
            "closed": len(recent),
            "average_net_return": (
                sum(recent_returns) / len(recent_returns) if recent_returns else None
            ),
        },
        "operational_orders": 0,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    dated_path = output_dir / f"{updated_at.date().isoformat()}.md"
    latest_path = output_dir / "latest.md"
    json_path = output_dir / "latest.json"
    report = _weekly_snapshot_markdown(snapshot)
    dated_path.write_text(report, encoding="utf-8")
    latest_path.write_text(report, encoding="utf-8")
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshot.update(markdown_path=str(dated_path), latest_path=str(latest_path), json_path=str(json_path))
    return snapshot


def _weekly_snapshot_markdown(snapshot: dict) -> str:
    pct = lambda value: "—" if value is None else f"{value * 100:.2f}%"
    progress = snapshot["progress"]
    lines = ["# A4/C3 주간 전진 검증 스냅숏", "",
             f"> 실행일 {snapshot['as_of'][:10]} · 검색일 {snapshot['signal_date']} · 상태 **{snapshot['promotion_status']}** · 실주문 0", "",
             f"- 완료: {progress['closed']} / 중간 검토 {progress['interim_target']} / 승격 심사 {progress['review_target']}",
             f"- 신규 신호: {len(snapshot['new_signals'])}건", f"- 체결 대기·보유: {len(snapshot['live_positions'])}건",
             f"- 최근 12개월 완료/평균: {snapshot['recent_12_months']['closed']} / {pct(snapshot['recent_12_months']['average_net_return'])}",
             "", "## A/C 분리 성과", "", "|전략|완료|승률|평균 순수익|평균 초과수익|상위3 기여|", "|---|---:|---:|---:|---:|---:|"]
    for source, row in snapshot["by_source"].items():
        lines.append(f"|{source}|{row['closed']}|{pct(row['win_rate'])}|{pct(row['average_net_return'])}|{pct(row['average_excess_return'])}|{pct(row['top3_positive_contribution'])}|")
    lines.extend(["", "## 보유기간 경로", "", "|거래일|표본|승률|평균 순수익|평균 초과수익|", "|---:|---:|---:|---:|---:|"])
    for horizon in ("10", "20", "40", "60"):
        row = snapshot["horizons"].get(horizon, {})
        lines.append(f"|{horizon}|{row.get('count', 0)}|{pct(row.get('win_rate'))}|{pct(row.get('average_net_return'))}|{pct(row.get('average_excess_return'))}|")
    lines.extend(["", "## 신규 신호", ""])
    if snapshot["new_signals"]:
        lines.extend(f"- {row['source']} · {row['code']} {row['name']} · {row['status']}" for row in snapshot["new_signals"])
    else:
        lines.append("- 없음")
    lines.extend(["", "- 규칙 동결 상태에서만 전진 표본으로 인정합니다.", "- 이 보고서는 주문을 생성하거나 전송하지 않습니다.", ""])
    return "\n".join(lines)


def replay_shadow_month(
    month: str,
    cadence: str,
    active_data_path: Path,
    freeze_path: Path,
    state_path: Path,
) -> dict:
    """Replay one historical month into an isolated no-order state file."""
    try:
        month_start = datetime.strptime(month, "%Y-%m")
    except ValueError as error:
        raise ValueError("month must use YYYY-MM format") from error
    if cadence not in {"weekly", "daily"}:
        raise ValueError("cadence must be weekly or daily")
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    raw_sessions = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )["sessions"]
    all_sessions = [datetime.fromisoformat(value) for value in sorted(raw_sessions)]
    sessions = [
        value for value in all_sessions
        if value.year == month_start.year and value.month == month_start.month
    ]
    if not sessions:
        raise ValueError(f"no market sessions found for {month}")
    if cadence == "weekly":
        by_week = {}
        for value in sessions:
            by_week[value.isocalendar()[:2]] = value
        signal_dates = list(by_week.values())
    else:
        signal_dates = sessions
    state = None
    for signal_at in signal_dates:
        state = run_shadow_portfolio(
            signal_at, active_data_path, freeze_path, state_path,
        )
    last_index = all_sessions.index(signal_dates[-1])
    evaluation_index = min(last_index + 60, len(all_sessions) - 1)
    state = run_shadow_portfolio(
        all_sessions[evaluation_index], active_data_path, freeze_path,
        state_path, create_signals=False,
    )
    state["replay"] = {
        "month": month,
        "cadence": cadence,
        "signal_dates": [value.isoformat() for value in signal_dates],
        "evaluation_as_of": all_sessions[evaluation_index].isoformat(),
        "isolated": True,
    }
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return state


def replay_weekday_sensitivity(
    start_month: str,
    end_month: str,
    active_data_path: Path,
    freeze_path: Path,
    output_dir: Path,
) -> dict:
    """Replay the same frozen rules independently for each weekday."""
    try:
        start = datetime.strptime(start_month, "%Y-%m")
        end = datetime.strptime(end_month, "%Y-%m")
    except ValueError as error:
        raise ValueError("start-month and end-month must use YYYY-MM format") from error
    if (start.year, start.month) > (end.year, end.month):
        raise ValueError("start-month must not be after end-month")
    _, price_dir, _ = load_active_backtest_data(active_data_path)
    raw_sessions = json.loads(
        (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
    )["sessions"]
    all_sessions = [datetime.fromisoformat(value) for value in sorted(raw_sessions)]
    eligible = [
        value for value in all_sessions
        if (start.year, start.month) <= (value.year, value.month)
        <= (end.year, end.month)
    ]
    if not eligible:
        raise ValueError("no market sessions in requested month range")
    output_dir.mkdir(parents=True, exist_ok=True)
    labels = ("monday", "tuesday", "wednesday", "thursday", "friday")
    rows = []
    for weekday, label in enumerate(labels):
        signal_dates = [value for value in eligible if value.weekday() == weekday]
        if not signal_dates:
            continue
        state_path = output_dir / f"{start_month}_{end_month}-{label}.json"
        state = _replay_signal_dates(
            signal_dates, all_sessions, active_data_path, freeze_path,
            state_path,
        )
        closed = [
            row for row in state["positions"] if row["status"] == "CLOSED"
        ]
        returns = [float(row["net_return"]) for row in closed]
        excess = [float(row["excess_return"]) for row in closed]
        without_best = sorted(returns, reverse=True)[1:]
        rows.append({
            "weekday": label,
            "signal_dates": len(signal_dates),
            "closed": len(closed),
            "win_rate": (
                sum(value > 0 for value in returns) / len(returns)
                if returns else None
            ),
            "average_net_return": (
                sum(returns) / len(returns) if returns else None
            ),
            "average_excess_return": (
                sum(excess) / len(excess) if excess else None
            ),
            "average_without_best": (
                sum(without_best) / len(without_best)
                if without_best else None
            ),
            "state": state_path.name,
        })
    result = {
        "schema_version": 1,
        "program_version": "research-ac43-portfolio-v1",
        "period": {"start": start_month, "end": end_month},
        "rows": rows,
        "operational_orders": 0,
    }
    result_path = output_dir / f"{start_month}_{end_month}-summary.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _save_weekday_markdown(
        result, output_dir / f"{start_month}_{end_month}-summary.md"
    )
    return result


def _replay_signal_dates(
    signal_dates, all_sessions, active_data_path, freeze_path, state_path,
):
    state = None
    for signal_at in signal_dates:
        state = run_shadow_portfolio(
            signal_at, active_data_path, freeze_path, state_path,
        )
    last_index = all_sessions.index(signal_dates[-1])
    evaluation_index = min(last_index + 60, len(all_sessions) - 1)
    state = run_shadow_portfolio(
        all_sessions[evaluation_index], active_data_path, freeze_path,
        state_path, create_signals=False,
    )
    state["replay"] = {
        "signal_dates": [value.isoformat() for value in signal_dates],
        "evaluation_as_of": all_sessions[evaluation_index].isoformat(),
        "isolated": True,
    }
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return state


def _save_weekday_markdown(result, output):
    lines = [
        "# TITAN A/C Weekday Sensitivity", "",
        "> Frozen rules; exact weekdays only; no holiday substitution; no orders.",
        "", "| Weekday | Search dates | Closed | Win rate | Average net | Average excess | Excluding best |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    percent = lambda value: "—" if value is None else f"{value:.2%}"
    for row in result["rows"]:
        lines.append(
            f"| {row['weekday']} | {row['signal_dates']} | {row['closed']} | "
            f"{percent(row['win_rate'])} | {percent(row['average_net_return'])} | "
            f"{percent(row['average_excess_return'])} | "
            f"{percent(row['average_without_best'])} |"
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verify_freeze(payload: dict) -> None:
    expected = payload.get("specification_sha256")
    specification = {
        key: value for key, value in payload.items()
        if key != "specification_sha256"
    }
    actual = hashlib.sha256(json.dumps(
        specification, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if not expected or actual != expected:
        raise ValueError("challenger freeze hash mismatch")


def _load_state(path: Path, freeze: dict) -> dict:
    if not path.exists():
        return {
            "schema_version": 1,
            "program_version": freeze["program_version"],
            "specification_sha256": freeze["specification_sha256"],
            "run_dates": [], "positions": [], "summary": {},
        }
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("specification_sha256") != freeze["specification_sha256"]:
        raise ValueError("shadow state was created by a different specification")
    return state


def _select_frozen_candidates(signal_at, active_data_path, freeze):
    output = {}
    mapping = {
        "A": "challenger-a-breakout-h40",
        "C": "challenger-c-pullback-h40",
    }
    for source, strategy_id in mapping.items():
        spec = freeze["strategies"][strategy_id]
        engine = create_walk_forward_engine(
            strategy_version=f"shadow-{strategy_id}",
            criteria=SelectionCriteria(**spec["config"]),
            strategy_config_hash=freeze["specification_sha256"],
            active_data_path=active_data_path,
        )
        run = engine.selection_runner.select(signal_at, top_n=spec["top_n"])
        output[source] = run.selections
    return output


def _allocate(positions, selections, freeze, signal_at):
    slot_limits = freeze["portfolio"]["slot_limits"]
    source_ids = {
        "A": "challenger-a-breakout-h40",
        "C": "challenger-c-pullback-h40",
    }
    occupied_codes = {
        row["code"] for row in positions
        if row["status"] in {"PENDING_ENTRY", "OPEN"}
    }
    for source in ("A", "C"):
        limit = int(slot_limits[source_ids[source]])
        occupied = sum(
            row["source"] == source
            and row["status"] in {"PENDING_ENTRY", "OPEN"}
            for row in positions
        )
        for selection in selections[source]:
            reason = None
            if selection.code in occupied_codes:
                reason = "DUPLICATE_CODE"
            elif occupied >= limit:
                reason = "SOURCE_CAPACITY"
            if reason:
                positions.append(_position(selection, source, signal_at, "SKIPPED", reason))
                continue
            positions.append(_position(selection, source, signal_at, "PENDING_ENTRY", None))
            occupied_codes.add(selection.code)
            occupied += 1


def _position(selection, source, signal_at, status, exclusion_reason):
    analysis = selection.analysis
    return {
        "source": source, "code": selection.code, "name": selection.name,
        "market": analysis.market.value if analysis.market else None,
        "rank": selection.rank, "score": analysis.score.normalized_score,
        "selected_at": signal_at.isoformat(), "status": status,
        "exclusion_reason": exclusion_reason,
        "enabled_features": [row.type.value for row in analysis.features.enabled()],
        "market_strength": (
            analysis.context.market_strength if analysis.context else None
        ),
        "entry_date": None, "entry_price": None,
        "exit_date": None, "exit_price": None,
        "net_return": None, "benchmark_return": None, "excess_return": None,
        "horizon_evaluations": {},
    }


def _mature_positions(positions, as_of, provider, benchmark, sessions):
    costs = transaction_cost_policy_from_env()
    for row in positions:
        if row["status"] == "SKIPPED":
            continue
        candles = provider._candles(row["code"])
        selected_at = datetime.fromisoformat(row["selected_at"])
        if row["status"] == "PENDING_ENTRY":
            entry = next((c for c in candles if selected_at < c.date <= as_of), None)
            if entry is None:
                continue
            row["entry_date"] = entry.date.isoformat()
            row["entry_price"] = entry.open
            row["status"] = "OPEN"
        market = MarketType(row["market"])
        future_sessions = [value for value in sessions if value > selected_at]
        evaluations = row.setdefault("horizon_evaluations", {})
        for horizon in (10, 20, 40, 60):
            key = str(horizon)
            if key in evaluations or len(future_sessions) < horizon:
                continue
            evaluation_date = future_sessions[horizon - 1]
            if evaluation_date > as_of:
                continue
            exit_candle = next((c for c in candles if c.date == evaluation_date), None)
            if exit_candle is None:
                continue
            net_return = costs.net_return(row["entry_price"], exit_candle.close)
            benchmark_return = benchmark.get_returns(
                {market}, selected_at, evaluation_date,
            )[market.value]
            evaluations[key] = {
                "evaluation_date": evaluation_date.isoformat(),
                "exit_price": exit_candle.close,
                "net_return": net_return,
                "benchmark_return": benchmark_return,
                "excess_return": net_return - benchmark_return,
            }
        if "40" in evaluations and row["status"] != "CLOSED":
            result = evaluations["40"]
            row["exit_date"] = result["evaluation_date"]
            row["exit_price"] = result["exit_price"]
            row["net_return"] = result["net_return"]
            row["benchmark_return"] = result["benchmark_return"]
            row["excess_return"] = result["excess_return"]
            row["status"] = "CLOSED"


def _summary(positions):
    closed = [row for row in positions if row["status"] == "CLOSED"]
    net = [row["net_return"] for row in closed]
    excess = [row["excess_return"] for row in closed]
    horizon_summary = {}
    for horizon in (10, 20, 40, 60):
        values = [
            row.get("horizon_evaluations", {}).get(str(horizon))
            for row in positions
        ]
        values = [value for value in values if value]
        horizon_summary[str(horizon)] = {
            "count": len(values),
            "win_rate": (
                sum(value["net_return"] > 0 for value in values) / len(values)
                if values else None
            ),
            "average_net_return": (
                sum(value["net_return"] for value in values) / len(values)
                if values else None
            ),
            "average_excess_return": (
                sum(value["excess_return"] for value in values) / len(values)
                if values else None
            ),
        }
    return {
        "pending": sum(row["status"] == "PENDING_ENTRY" for row in positions),
        "open": sum(row["status"] == "OPEN" for row in positions),
        "closed": len(closed),
        "skipped": sum(row["status"] == "SKIPPED" for row in positions),
        "progress_target": 100,
        "progress_ratio": min(1.0, len(closed) / 100),
        "win_rate": sum(value > 0 for value in net) / len(net) if net else None,
        "average_net_return": sum(net) / len(net) if net else None,
        "average_excess_return": sum(excess) / len(excess) if excess else None,
        "horizons": horizon_summary,
        "operational_orders": 0,
    }

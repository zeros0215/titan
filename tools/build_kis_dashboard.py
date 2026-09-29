import json
from datetime import datetime
from pathlib import Path

from pilot.history import PilotHistoryRepository, PilotReadinessEvaluator
from analysis.event_shadow import (
    load_event_runs,
    summarize_event_shadow,
)


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output" / "kis_v1_1"
MANUAL_OUTPUT = ROOT / "output" / "kis_manual_tests"
INDUSTRY_RS_OUTPUT = ROOT / "output" / "industry_rs"
PRE_BREAKOUT_OUTPUT = ROOT / "output" / "pre_breakout"
EVENT_OUTPUT = ROOT / "output" / "event_candidates" / "runs"
STRATEGY_COMPARISON_OUTPUT = ROOT / "output" / "strategy_comparison"
TEMPLATE = ROOT / "dashboard" / "index.template.html"
SITE_INDEX = ROOT / "dashboard" / "index.html"
LOCAL_INDEX = OUTPUT / "dashboard.html"


def _load_latest_prices(
    price_dir: Path | None, codes: set[str]
) -> dict[str, dict[str, object]]:
    """Load the most recent two closes for dashboard candidate symbols."""
    if price_dir is None:
        return {}
    result = {}
    for code in sorted(codes):
        path = price_dir / f"{code}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            candles = payload.get("candles") or []
            latest = candles[-1]
            previous = candles[-2] if len(candles) > 1 else None
            close = float(latest["close"])
            previous_close = (
                float(previous["close"]) if previous is not None else None
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
        result[code] = {
            "date": str(latest["date"])[:10],
            "close": close,
            "change_rate": (
                close / previous_close - 1
                if previous_close not in (None, 0)
                else None
            ),
        }
    return result


def _load_market_breadth(price_dir: Path | None, limit: int = 100) -> dict:
    """Summarize the latest session for a point-in-time market-cap cohort."""
    if price_dir is None:
        return {}
    ranking_path = price_dir / "market_cap_top500.json"
    try:
        ranking = json.loads(ranking_path.read_text(encoding="utf-8"))
        sessions = ranking["sessions"]
        session_key = sorted(sessions)[-1]
        codes = list(sessions[session_key])[:limit]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return {}
    returns = []
    for raw_code in codes:
        path = price_dir / f"{str(raw_code).zfill(6)}.json"
        try:
            candles = json.loads(path.read_text(encoding="utf-8"))["candles"]
            current, previous = candles[-1], candles[-2]
            if str(current["date"])[:10] != str(session_key)[:10]:
                continue
            returns.append(float(current["close"]) / float(previous["close"]) - 1)
        except (
            OSError, IndexError, KeyError, TypeError, ValueError,
            ZeroDivisionError, json.JSONDecodeError,
        ):
            continue
    if not returns:
        return {}
    ordered = sorted(returns)
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2
    )
    up = sum(value > 0 for value in returns)
    down = sum(value < 0 for value in returns)
    flat = len(returns) - up - down
    up_rate = up / len(returns)
    average = sum(returns) / len(returns)
    state = (
        "BROAD_RALLY" if up_rate >= 0.70 and average >= 0.015
        else "BROAD_DECLINE" if up_rate <= 0.30 and average <= -0.015
        else "NORMAL"
    )
    return {
        "date": str(session_key)[:10],
        "cohort": f"MARKET_CAP_TOP_{limit}",
        "valid_count": len(returns),
        "up": up,
        "down": down,
        "flat": flat,
        "up_rate": up_rate,
        "equal_weight_return": average,
        "median_return": median,
        "state": state,
    }


def _load_selection_and_entry_prices(
    price_dir: Path | None, runs: list[dict]
) -> tuple[dict[str, float], dict[str, dict[str, object]]]:
    """Load the selection close and the following session's opening price."""
    if price_dir is None:
        return {}, {}
    requested: dict[str, set[str]] = {}
    for run in runs:
        selection_date = str(run.get("as_of") or "")[:10]
        if not selection_date:
            continue
        for field in ("selected_candidates", "observation_candidates"):
            for candidate in run.get(field) or []:
                code = str(candidate.get("code") or "").zfill(6)
                if code:
                    requested.setdefault(code, set()).add(selection_date)
    selection_prices = {}
    entry_prices = {}
    for code, dates in requested.items():
        path = price_dir / f"{code}.json"
        try:
            candles = json.loads(path.read_text(encoding="utf-8")).get(
                "candles", []
            )
        except (OSError, TypeError, json.JSONDecodeError):
            continue
        for index, candle in enumerate(candles):
            candle_date = str(candle.get("date") or "")[:10]
            if candle_date not in dates:
                continue
            try:
                key = f"{candle_date}|{code}"
                selection_prices[key] = float(candle["close"])
                if index + 1 < len(candles):
                    following = candles[index + 1]
                    entry_prices[key] = {
                        "date": str(following["date"])[:10],
                        "open": float(following["open"]),
                    }
            except (KeyError, TypeError, ValueError):
                pass
    return selection_prices, entry_prices


def main() -> None:
    official_runs = PilotHistoryRepository(OUTPUT / "runs").load_all()
    manual_runs = PilotHistoryRepository(MANUAL_OUTPUT / "runs").load_all()
    operational_version = "V1.3-S80-N7-TP5-SL10-CANDIDATE"
    operational_official_runs = [
        run for run in official_runs
        if run.get("strategy_version") == operational_version
    ]
    readiness = PilotReadinessEvaluator(5).evaluate(
        [
            run for run in operational_official_runs
            if run.get("source", "KIS") == "KIS"
        ]
    )
    for item in official_runs:
        item["run_type"] = "OFFICIAL"
    for item in manual_runs:
        item["run_type"] = "MANUAL"
    runs = sorted(
        official_runs + manual_runs,
        key=lambda item: (
            item.get("as_of", ""),
            item.get("_file_mtime", 0),
            item.get("run_type", ""),
        ),
    )
    for item in runs:
        if item.get("_file_mtime"):
            item["executed_at"] = datetime.fromtimestamp(
                item["_file_mtime"]
            ).astimezone().isoformat(timespec="seconds")
        item.pop("_file_mtime", None)
    historical_trades = []
    for run in runs:
        if run.get("source") != "LOCAL_KRX":
            continue
        for trade in run.get("trades", []):
            historical_trades.append({
                **trade,
                "_run_id": run.get("run_id"),
                "_executed_at": run.get("executed_at"),
            })
    # Trades are rendered from ``historical.trades`` below. Keeping the same
    # arrays inside every run duplicates several megabytes in the HTML.
    for run in runs:
        run.pop("trades", None)
    run_fields = (
        "as_of", "status", "api_success_rate", "retry_rate",
        "exclusion_rate", "analyzed_count", "selection_count",
        "order_request_count", "strategy_version", "holding_sessions",
        "profit_target", "stop_loss",
        "entry_mode", "entry_limit", "entry_minimum",
        "run_id", "executed_at",
        "market_regime", "run_type", "source",
        "request_count", "fetch_failures",
    )
    candidate_fields = (
        "rank", "code", "name", "total_score", "trend_score",
        "momentum_score", "volume_score", "price_action_score",
        "risk_score", "context_score", "market_trend", "market_strength",
    )
    runs = [
        {
            **{key: run.get(key) for key in run_fields},
            "selected_candidates": [
                {key: item.get(key) for key in candidate_fields}
                for item in run.get("selected_candidates", [])
            ],
            "observation_candidates": [
                {key: item.get(key) for key in candidate_fields}
                for item in run.get("observation_candidates", [])
            ],
        }
        for run in runs
    ]
    completed_trades = len(historical_trades)
    winning_trades = sum(bool(trade.get("win")) for trade in historical_trades)
    baseline_runs = [
        run
        for run in runs
        if run.get("strategy_version", "V1.1") == "V1.1"
    ]
    active_data_path = ROOT / "output" / "release" / "backtest_data.json"
    active_data = (
        json.loads(active_data_path.read_text(encoding="utf-8"))
        if active_data_path.exists()
        else {}
    )
    price_manifest_path = (
        Path(active_data["price_dir"]) / "price_history_manifest.json"
        if active_data.get("price_dir")
        else None
    )
    price_manifest = (
        json.loads(price_manifest_path.read_text(encoding="utf-8"))
        if price_manifest_path and price_manifest_path.exists()
        else {}
    )
    latest_run = (
        operational_official_runs[-1]
        if operational_official_runs else None
    )
    latest_candidate_codes = {
        str(candidate.get("code", "")).zfill(6)
        for run in runs
        for field in ("selected_candidates", "observation_candidates")
        for candidate in (run.get(field) or [])
        if candidate.get("code")
    }
    active_price_dir = (
        Path(active_data["price_dir"]) if active_data.get("price_dir") else None
    )
    latest_prices = _load_latest_prices(
        active_price_dir,
        latest_candidate_codes,
    )
    market_breadth = _load_market_breadth(active_price_dir)
    latest_excess_returns = {
        code: price["change_rate"] - market_breadth["equal_weight_return"]
        for code, price in latest_prices.items()
        if (
            price.get("date") == market_breadth.get("date")
            and price.get("change_rate") is not None
            and market_breadth.get("equal_weight_return") is not None
        )
    }
    selection_prices, selection_entry_prices = _load_selection_and_entry_prices(
        active_price_dir,
        runs,
    )
    industry_rs_path = INDUSTRY_RS_OUTPUT / "industry_rs_validation.json"
    industry_rs = (
        json.loads(industry_rs_path.read_text(encoding="utf-8"))
        if industry_rs_path.exists()
        else None
    )
    if industry_rs is not None:
        industry_rs.pop("observations", None)
    pre_breakout_path = PRE_BREAKOUT_OUTPUT / "pre_breakout_scan.json"
    pre_breakout = (
        json.loads(pre_breakout_path.read_text(encoding="utf-8"))
        if pre_breakout_path.exists()
        else None
    )
    pre_breakout_monthly_path = (
        PRE_BREAKOUT_OUTPUT / "pre_breakout_monthly.json"
    )
    pre_breakout_monthly = (
        json.loads(pre_breakout_monthly_path.read_text(encoding="utf-8"))
        if pre_breakout_monthly_path.exists()
        else None
    )
    event_runs = load_event_runs(EVENT_OUTPUT)
    event_shadow = summarize_event_shadow(
        event_runs,
        active_price_dir,
    )
    research_manifest_path = (
        ROOT / "output" / "strategy_research" / "candidates" / "manifest.json"
    )
    research_manifest = (
        json.loads(research_manifest_path.read_text(encoding="utf-8"))
        if research_manifest_path.exists() else {}
    )
    research_ranking_path = ROOT / "output" / "strategy_research" / "ranking.md"
    research_ranking = (
        research_ranking_path.read_text(encoding="utf-8")
        if research_ranking_path.exists() else ""
    )
    strategy_comparison_path = STRATEGY_COMPARISON_OUTPUT / "2026.json"
    strategy_comparison = (
        json.loads(strategy_comparison_path.read_text(encoding="utf-8"))
        if strategy_comparison_path.exists() else {}
    )
    data = {
        "generated_at": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "data_status": {
            "coverage_end": price_manifest.get("coverage_end"),
            "promoted_at": active_data.get("promoted_at"),
        },
        "market_breadth": market_breadth,
        "latest_excess_returns": latest_excess_returns,
        "readiness": {
            "status": readiness.status,
            "observed_days": readiness.observed_days,
            "passing_days": readiness.passing_days,
            "consecutive_passing_days": readiness.consecutive_passing_days,
            "reasons": readiness.reasons,
        },
        "latest": latest_run,
        "operational_strategy": {
            "version": operational_version,
            "label": "S80 모의 운영",
            "summary": "80점 이상 · 최대 7종목 · 다음 거래일 시가 · 시가 갭 ±3% 이내 · 익절 +5% · 손절 -10% · 최대 20거래일",
        },
        "latest_prices": latest_prices,
        "selection_prices": selection_prices,
        "selection_entry_prices": selection_entry_prices,
        "runs": runs,
        "operational_runs": [
            run for run in runs
            if (
                run.get("run_type") == "OFFICIAL"
                and run.get("strategy_version") == operational_version
            )
        ],
        "historical": {
            "trades": historical_trades,
            "total": completed_trades,
            "wins": winning_trades,
            "win_rate": (
                winning_trades / completed_trades
                if completed_trades
                else None
            ),
            "average_net_return": (
                sum(
                    float(trade["net_return"])
                    for trade in historical_trades
                ) / completed_trades
                if completed_trades
                else None
            ),
            "holding_sessions": 1,
        },
        "industry_rs": industry_rs,
        "pre_breakout": pre_breakout,
        "pre_breakout_monthly": pre_breakout_monthly,
        "event_shadow": event_shadow,
        "strategy_comparison": strategy_comparison,
    }
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "__TITAN_DATA__",
        json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
    )
    SITE_INDEX.write_text(html, encoding="utf-8")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    LOCAL_INDEX.write_text(html, encoding="utf-8")
    print(LOCAL_INDEX)


if __name__ == "__main__":
    main()

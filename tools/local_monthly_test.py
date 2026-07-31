"""Run a calendar month of V1 selections from promoted local KRX data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter

from broker.historical import HistoricalFileMarketProvider
from config.transaction_costs import transaction_cost_policy_from_env
from config.strategy_profiles import get_strategy_profile
from data.quarantine import QualityQuarantinePolicy
from pilot.runner import KisPilotRunner
from release.backtest_data import load_active_backtest_data
from repository.market_cap_stock_repository import MarketCapStockRepository
from repository.stock_repository import StockRepository
from runner.factory import create_titan_runner
from analysis.morning_entry import evaluate_morning_bars


ROOT = Path(__file__).resolve().parent.parent
ACTIVE_DATA = ROOT / "output" / "release" / "backtest_data.json"
OUTPUT = ROOT / "output" / "kis_manual_tests"
MORNING_BARS = ROOT / "output" / "morning_entry" / "historical_bars"


def run_month(
    month: str,
    top_n: int | None = None,
    holding_sessions: int = 1,
    strategy_version: str = "V1.1",
    profit_target: float | None = None,
    stop_loss: float | None = None,
    entry_mode: str = "OPEN",
    entry_limit: float = 0.03,
    entry_minimum: float | None = None,
) -> list[dict[str, object]]:
    try:
        month_start = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("월은 YYYY-MM 형식이어야 합니다.") from exc

    return _run_period(
        f"{month_start:%Y-%m}",
        top_n,
        holding_sessions,
        strategy_version,
        profit_target=profit_target,
        stop_loss=stop_loss,
        entry_mode=entry_mode,
        entry_limit=entry_limit,
        entry_minimum=entry_minimum,
    )


def run_year(
    year: str,
    top_n: int | None = None,
    holding_sessions: int = 1,
    strategy_version: str = "V1.1",
    profit_target: float | None = None,
    stop_loss: float | None = None,
    entry_mode: str = "OPEN",
    entry_limit: float = 0.03,
    entry_minimum: float | None = None,
) -> list[dict[str, object]]:
    try:
        year_start = datetime.strptime(year, "%Y")
    except ValueError as exc:
        raise ValueError("연도는 YYYY 형식이어야 합니다.") from exc
    return _run_period(
        f"{year_start:%Y}",
        top_n,
        holding_sessions,
        strategy_version,
        profit_target=profit_target,
        stop_loss=stop_loss,
        entry_mode=entry_mode,
        entry_limit=entry_limit,
        entry_minimum=entry_minimum,
    )


def run_date(
    value: str,
    top_n: int | None = None,
    holding_sessions: int = 1,
    strategy_version: str = "V1.1",
    profit_target: float | None = None,
    stop_loss: float | None = None,
    entry_mode: str = "OPEN",
    entry_limit: float = 0.03,
    entry_minimum: float | None = None,
) -> dict[str, object]:
    try:
        as_of = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.") from exc
    results = _run_period(
        f"{as_of:%Y-%m}",
        top_n,
        holding_sessions,
        strategy_version,
        exact_date=as_of,
        profit_target=profit_target,
        stop_loss=stop_loss,
        entry_mode=entry_mode,
        entry_limit=entry_limit,
        entry_minimum=entry_minimum,
    )
    return results[0]


def _run_period(
    period: str,
    top_n: int | None,
    holding_sessions: int,
    strategy_version: str,
    exact_date: datetime | None = None,
    profit_target: float | None = None,
    stop_loss: float | None = None,
    entry_mode: str = "OPEN",
    entry_limit: float = 0.03,
    entry_minimum: float | None = None,
) -> list[dict[str, object]]:
    if holding_sessions <= 0:
        raise ValueError("보유기간은 1거래일 이상이어야 합니다.")
    profile = get_strategy_profile(strategy_version)
    if (profit_target is None) != (stop_loss is None):
        raise ValueError("profit_target and stop_loss must be provided together")
    if profit_target is not None and not 0 < profit_target <= 1:
        raise ValueError("profit_target must be greater than 0 and at most 1")
    if stop_loss is not None and not 0 < stop_loss <= 1:
        raise ValueError("stop_loss must be greater than 0 and at most 1")
    if entry_mode not in {"OPEN", "KIS_1000_LIMIT"}:
        raise ValueError(f"unsupported entry_mode: {entry_mode}")
    if not 0 <= entry_limit <= 1:
        raise ValueError("entry_limit must be between 0 and 1")
    if entry_minimum is not None and not -1 <= entry_minimum <= 0:
        raise ValueError("entry_minimum must be between -1 and 0")
    effective_profit_target = (
        profit_target if profit_target is not None else profile.profit_target
    )
    effective_stop_loss = (
        stop_loss if stop_loss is not None else profile.stop_loss
    )
    selection_limit = top_n if top_n is not None else profile.selection_limit
    if (
        profile.version in {
            "V1.2-5D-CANDIDATE",
            "V1.3-RISK-5D-CANDIDATE",
            "V1.3-S78-N7-CANDIDATE",
            "V1.3-S78-N7-TP5-SL10-CANDIDATE",
            "V1.3-S80-N7-TP5-SL10-CANDIDATE",
            "V1.3-S79-N2-TP5-SL10-CANDIDATE",
            "V1.3-DUAL-5D-S80-N7-TP5-SL10-CANDIDATE",
        }
        and holding_sessions != profile.recommended_holding_sessions
    ):
        raise ValueError(
            f"{profile.version}은 "
            f"{profile.recommended_holding_sessions}거래일 검증만 지원합니다."
        )
    universe_dir, price_dir, _ = load_active_backtest_data(ACTIVE_DATA)
    top500_path = price_dir / "market_cap_top500.json"
    top500 = json.loads(top500_path.read_text(encoding="utf-8"))
    all_session_dates = sorted(
        datetime.fromisoformat(value)
        for value in top500["sessions"]
    )
    session_dates = [
        value
        for value in all_session_dates
        if value.isoformat().startswith(f"{period}-")
        and (exact_date is None or value.date() == exact_date.date())
    ]
    if not session_dates:
        target = exact_date.date().isoformat() if exact_date else period
        raise ValueError(f"{target}에 사용할 수 있는 로컬 거래일 데이터가 없습니다.")

    artifact_root = (
        OUTPUT / "artifacts" / strategy_version.replace(".", "_") / period
    )
    provider = HistoricalFileMarketProvider(price_dir)
    runner = create_titan_runner(
        artifact_root=artifact_root,
        market_provider=provider,
        stock_repository=MarketCapStockRepository(
            StockRepository(universe_dir),
            top500_path,
        ),
        quality_quarantine_policy=QualityQuarantinePolicy.from_file(
            price_dir / "quality_quarantines.json"
        ),
        criteria=profile.criteria,
        strategy_version=profile.version,
    )
    results = []
    run_dir = OUTPUT / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    for as_of in session_dates:
        started = perf_counter()
        selection = runner.select(as_of, top_n=selection_limit)
        regime_candidates = (
            selection.selections or selection.observations
        )
        market_regime = (
            runner.filter_engine.market_regime(
                regime_candidates[0].analysis
            )
            if (
                profile.criteria.use_market_regime_rules
                and regime_candidates
            )
            else None
        )
        quality = selection.quality_summary
        universe_count = quality.total_count if quality else 0
        excluded_count = quality.excluded_count if quality else universe_count
        trades = []
        cost_policy = transaction_cost_policy_from_env()
        session_index = all_session_dates.index(as_of)
        if session_index + holding_sessions >= len(all_session_dates):
            future_buy_date = None
            future_sell_date = None
        else:
            future_buy_date = all_session_dates[session_index + 1]
            future_sell_date = all_session_dates[
                session_index + holding_sessions
            ]
        for cohort, candidates in (
            ("SELECTED", selection.selections),
            ("OBSERVATION", selection.observations),
        ):
            for selected in candidates:
                if future_buy_date is None or future_sell_date is None:
                    continue
                candles_by_date = {
                    candle.date: candle
                    for candle in provider._candles(selected.code)
                }
                buy_candle = candles_by_date.get(future_buy_date)
                exit_candle = candles_by_date.get(future_sell_date)
                if buy_candle is None or exit_candle is None:
                    continue
                selected_close = candles_by_date.get(as_of)
                buy_price = buy_candle.open
                morning_signal = None
                if entry_mode == "KIS_1000_LIMIT":
                    bar_path = (
                        MORNING_BARS / future_buy_date.date().isoformat()
                        / f"{selected.code}.csv"
                    )
                    if not bar_path.exists() or selected_close is None:
                        continue
                    morning_signal = evaluate_morning_bars(
                        bar_path, selected_close.close
                    )
                    buy_price = morning_signal["entry_price"]
                    if buy_price > selected_close.close * (1 + entry_limit):
                        continue
                    if (
                        entry_minimum is not None
                        and buy_price
                        < selected_close.close * (1 + entry_minimum)
                    ):
                        continue
                sell_price = exit_candle.close
                trade_holding_sessions = holding_sessions
                exit_reason = "FIXED_HOLD"
                entry_gap = (
                    buy_price / selected_close.close - 1.0
                    if selected_close is not None
                    else None
                )
                opening_gap = (
                    buy_candle.open / selected_close.close - 1.0
                    if selected_close is not None
                    else None
                )
                if (
                    profile.maximum_entry_gap is not None
                    and opening_gap is not None
                    and abs(opening_gap) > profile.maximum_entry_gap
                ):
                    continue
                if effective_profit_target is not None:
                    maximum_holding = (
                        profile.maximum_holding_sessions
                        or holding_sessions
                    )
                    (
                        exit_candle,
                        sell_price,
                        trade_holding_sessions,
                        exit_reason,
                    ) = _target_stop_exit(
                        all_session_dates,
                        session_index,
                        candles_by_date,
                        buy_price,
                        effective_profit_target,
                        effective_stop_loss,
                        maximum_holding,
                        morning_high=(
                            morning_signal["morning_high"]
                            if morning_signal else None
                        ),
                        morning_low=(
                            morning_signal["morning_low"]
                            if morning_signal else None
                        ),
                    )
                gross_return = sell_price / buy_price - 1.0
                net_return = cost_policy.net_return(
                    buy_price,
                    sell_price,
                )
                trades.append({
                    "cohort": cohort,
                    "strategy_version": profile.version,
                    "profit_target": effective_profit_target,
                    "stop_loss": effective_stop_loss,
                    "entry_gap": entry_gap,
                    "opening_gap": opening_gap,
                    "entry_mode": entry_mode,
                    "entry_limit": entry_limit,
                    "entry_minimum": entry_minimum,
                    "selection_date": as_of.date().isoformat(),
                    "trade_date": exit_candle.date.date().isoformat(),
                    "buy_date": buy_candle.date.date().isoformat(),
                    "sell_date": exit_candle.date.date().isoformat(),
                    "holding_sessions": trade_holding_sessions,
                    "evaluation_horizon": holding_sessions,
                    "exit_reason": exit_reason,
                    "code": selected.code,
                    "name": selected.name,
                    "rank": selected.rank,
                    "score": selected.analysis.score.normalized_score,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "gross_return": gross_return,
                    "net_return": net_return,
                    "win": net_return >= 0.0,
                })
        row = {
            "run_id": f"LOCAL_{as_of:%Y%m%d}",
            "as_of": as_of.isoformat(),
            "status": "PASS" if not selection.fetch_failures else "PARTIAL",
            "source": "LOCAL_KRX",
            "strategy_version": profile.version,
            "profit_target": effective_profit_target,
            "stop_loss": effective_stop_loss,
            "entry_mode": entry_mode,
            "entry_limit": entry_limit,
            "entry_minimum": entry_minimum,
            "market_regime": market_regime,
            "duration_seconds": perf_counter() - started,
            "universe_count": universe_count,
            "analyzed_count": quality.valid_count if quality else 0,
            "selection_count": len(selection.selections),
            "observation_count": len(selection.observations),
            "excluded_count": excluded_count,
            "exclusion_rate": (
                excluded_count / universe_count if universe_count else 0.0
            ),
            "fetch_failures": selection.fetch_failures,
            "request_count": 0,
            "success_count": 0,
            "retry_count": 0,
            "retry_rate": None,
            "failure_count": 0,
            "server_error_count": 0,
            "transport_error_count": 0,
            "api_success_rate": None,
            "order_request_count": 0,
            "selected_candidates": KisPilotRunner._candidate_rows(
                selection.selections
            ),
            "observation_candidates": KisPilotRunner._candidate_rows(
                selection.observations
            ),
            "snapshot_path": str(selection.snapshot_path),
            "reasons": [],
            "holding_sessions": holding_sessions,
            "trades": trades,
        }
        suffix = "" if holding_sessions == 1 else f"_H{holding_sessions}"
        if profile.version != "V1.1":
            suffix += "_" + profile.version.replace(".", "_").replace("-", "_")
        if profit_target is not None:
            suffix += (
                f"_TP{profit_target * 100:g}"
                f"_SL{stop_loss * 100:g}"
            ).replace(".", "_")
        if entry_mode != "OPEN":
            suffix += f"_{entry_mode}_L{entry_limit * 100:g}".replace(".", "_")
            if entry_minimum is not None:
                suffix += (
                    f"_MIN{abs(entry_minimum) * 100:g}"
                ).replace(".", "_")
        (run_dir / f"LOCAL_{as_of:%Y%m%d}{suffix}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        results.append(row)
        print(
            f"{as_of:%Y-%m-%d}: analyzed={row['analyzed_count']} "
            f"selected={row['selection_count']}"
        )
    return results


def _target_stop_exit(
    sessions,
    signal_index,
    candles_by_date,
    buy_price,
    profit_target,
    stop_loss,
    maximum_holding,
    morning_high=None,
    morning_low=None,
):
    target_price = buy_price * (1 + profit_target)
    stop_price = (
        buy_price * (1 - stop_loss)
        if stop_loss is not None else None
    )
    final_candle = None
    for offset in range(1, maximum_holding + 1):
        candle = candles_by_date.get(sessions[signal_index + offset])
        if candle is None:
            continue
        final_candle = candle
        stop_hit = stop_price is not None and candle.low <= stop_price
        target_hit = candle.high >= target_price
        if offset == 1 and morning_low is not None:
            stop_hit = stop_hit and morning_low > stop_price
            target_hit = target_hit and morning_high < target_price
        if stop_hit:
            return candle, stop_price, offset, f"STOP_LOSS_{stop_loss * 100:g}"
        if target_hit:
            return candle, target_price, offset, f"PROFIT_TARGET_{profit_target * 100:g}"
    if final_candle is None:
        raise ValueError("최대 보유기간의 가격 데이터가 없습니다.")
    return final_candle, final_candle.close, maximum_holding, "MAX_HOLD_20"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", required=True)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--holding-sessions", type=int, default=1)
    parser.add_argument(
        "--strategy-version",
        choices=[
            "V1.1",
            "V1.2-CANDIDATE",
            "V1.2-GAP-CANDIDATE",
            "V1.2-5D-CANDIDATE",
            "V1.3-RISK-5D-CANDIDATE",
            "V1.3-S78-N7-CANDIDATE",
            "V1.3-S78-N7-TP5-SL10-CANDIDATE",
            "V1.3-S80-N7-TP5-SL10-CANDIDATE",
            "V1.3-S79-N2-TP5-SL10-CANDIDATE",
            "V1.3-DUAL-5D-S80-N7-TP5-SL10-CANDIDATE",
        ],
        default="V1.1",
    )
    args = parser.parse_args()
    results = run_month(
        args.month,
        args.top_n,
        args.holding_sessions,
        args.strategy_version,
    )
    print(f"Completed: {len(results)} trading day(s)")


if __name__ == "__main__":
    main()

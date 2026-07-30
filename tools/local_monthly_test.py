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


ROOT = Path(__file__).resolve().parent.parent
ACTIVE_DATA = ROOT / "output" / "release" / "backtest_data.json"
OUTPUT = ROOT / "output" / "kis_manual_tests"


def run_month(
    month: str,
    top_n: int = 5,
    holding_sessions: int = 1,
    strategy_version: str = "V1.1",
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
    )


def run_year(
    year: str,
    top_n: int = 5,
    holding_sessions: int = 1,
    strategy_version: str = "V1.1",
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
    )


def _run_period(
    period: str,
    top_n: int,
    holding_sessions: int,
    strategy_version: str,
) -> list[dict[str, object]]:
    if holding_sessions <= 0:
        raise ValueError("보유기간은 1거래일 이상이어야 합니다.")
    profile = get_strategy_profile(strategy_version)
    if (
        profile.version in {
            "V1.2-5D-CANDIDATE",
            "V1.3-RISK-5D-CANDIDATE",
        }
        and holding_sessions != profile.recommended_holding_sessions
    ):
        raise ValueError("V1.2-5D 후보는 5거래일 보유만 지원합니다.")
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
    ]
    if not session_dates:
        raise ValueError(f"{period}에 사용할 수 있는 로컬 거래일 데이터가 없습니다.")

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
        selection = runner.select(as_of, top_n=top_n)
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
                buy_price = buy_candle.open
                sell_price = exit_candle.close
                selected_close = candles_by_date.get(as_of)
                entry_gap = (
                    buy_price / selected_close.close - 1.0
                    if selected_close is not None
                    else None
                )
                if (
                    profile.maximum_entry_gap is not None
                    and entry_gap is not None
                    and abs(entry_gap) > profile.maximum_entry_gap
                ):
                    continue
                gross_return = sell_price / buy_price - 1.0
                net_return = cost_policy.net_return(
                    buy_price,
                    sell_price,
                )
                trades.append({
                    "cohort": cohort,
                    "strategy_version": profile.version,
                    "entry_gap": entry_gap,
                    "selection_date": as_of.date().isoformat(),
                    "trade_date": exit_candle.date.date().isoformat(),
                    "buy_date": buy_candle.date.date().isoformat(),
                    "sell_date": exit_candle.date.date().isoformat(),
                    "holding_sessions": holding_sessions,
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

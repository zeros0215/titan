"""TITAN V1 command-line entry point."""

import argparse
import json
import os
import httpx
import sqlite3
import hashlib
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from config.constants import OUTPUT_DIR, PROJECT_TITLE, VERSION
from config.settings import settings
from core.container import Container
from core.logger import logger
from broker.factory import ProviderFactory
from repository.stock_repository import StockRepository
from repository.validation_repository import ValidationRepository
from report.exporter import ValidationExporter
from config.transaction_costs import transaction_cost_policy_from_env
from walkforward.plan import WalkForwardPlan
from monitoring.report import generate_monitoring_markdown
from strategy_gate.report import generate_strategy_gate_markdown
from config.selection_criteria import SelectionCriteria
from runner.factory import create_walk_forward_engine
from universe_history.compiler import UniverseHistoryCompiler
from universe_history.loader import UniverseHistoryLoader
from universe_history.report import generate_universe_history_markdown
from universe_history.krx import (
    KrxRawRepository,
    KrxUniverseClient,
    KrxUniverseCollector,
)
from universe_history.krx_normalizer import KrxSnapshotNormalizer
from pilot.runner import KisPilotRunner
from pilot.report import generate_kis_pilot_markdown
from pilot.history import PilotHistoryRepository, PilotReadinessEvaluator
from pilot.history_report import generate_pilot_readiness_markdown
from release.v1 import backtest_preflight, freeze_v1, preflight_markdown
from price_history.compiler import PriceHistoryCompiler, PriceHistoryLoader
from price_history.krx import (
    KrxPriceClient,
    KrxPriceCollector,
    KrxPriceRawRepository,
)
from price_history.krx_adjustment import KrxAdjustedPriceCompiler
from release.backtest_data import (
    load_active_backtest_data,
    promote_backtest_data,
)
from release.check import run_v1_release_check
from analysis.industry_relative_strength import run_industry_rs_validation
from analysis.morning_entry import (
    build_collection_manifest,
    evaluate_morning_bars,
)
from research.strategy_search import (
    generate_bounded_candidates,
    rank_walk_forward_results,
    render_ranking_markdown,
    save_candidate_grid,
    representative_candidates,
)
from research.portfolio_evaluation import (
    save_challenger_robustness_report,
    save_portfolio_report,
)
from research.challenger_freeze import save_challenger_freeze
from research.stress_diagnostics import save_stress_diagnostics
from research.shadow_portfolio import (
    replay_shadow_month,
    replay_weekday_sensitivity,
    run_shadow_portfolio,
    save_weekly_snapshot,
)
from research.monthly_relative_strength import run_monthly_relative_strength
from research.adaptive_momentum import run_adaptive_momentum
from research.research_scorecard import save_research_scorecard
from research.holding_horizon import save_holding_horizon_report
from research.ac_exit_comparison import save_ac_exit_comparison
from research.ac_audit import save_ac_audit


def banner() -> None:
    print("=" * 50)
    print(PROJECT_TITLE)
    print(f"Version : {VERSION}")
    print("=" * 50)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TITAN V1 selection platform")
    commands = parser.add_subparsers(dest="command")

    select = commands.add_parser("select", help="select and store candidates")
    select.add_argument("--date", required=True, type=datetime.fromisoformat)
    select.add_argument("--top-n", type=int, default=5)

    validate = commands.add_parser(
        "validate",
        help="validate selections stored on a prior date",
    )
    validate.add_argument("--selection-date", required=True, type=datetime.fromisoformat)
    validate.add_argument("--evaluation-date", required=True, type=datetime.fromisoformat)
    validate.add_argument("--holding-days", required=True, type=int)
    validate.add_argument("--success-return", type=float, default=0.03)
    validate.add_argument("--trade-time", default=None)
    validate.add_argument("--sell-time", default=None)
    validate.add_argument("--market-trend-filter", action="store_true")
    horizons = commands.add_parser(
        "validate-horizons",
        help="validate one selection at multiple trading-session horizons",
    )
    horizons.add_argument("--selection-date", required=True, type=datetime.fromisoformat)
    horizons.add_argument("--as-of", required=True, type=datetime.fromisoformat)
    horizons.add_argument(
        "--holding-days",
        nargs="+",
        type=int,
        default=[5, 10, 20, 40],
    )
    horizons.add_argument("--success-return", type=float, default=0.03)
    horizons.add_argument("--trade-time", default=None)
    horizons.add_argument("--sell-time", default=None)
    horizons.add_argument("--market-trend-filter", action="store_true")
    observations = commands.add_parser(
        "validate-observations",
        help="validate the bounded non-recommendation observation cohort",
    )
    observations.add_argument(
        "--selection-date",
        required=True,
        type=datetime.fromisoformat,
    )
    observations.add_argument("--as-of", required=True, type=datetime.fromisoformat)
    observations.add_argument(
        "--holding-days",
        nargs="+",
        type=int,
        default=[5, 10, 20, 40],
    )
    observations.add_argument("--success-return", type=float, default=0.03)
    export = commands.add_parser("export", help="export validation history to csv or excel")
    export.add_argument("--format", choices=["csv", "excel"], default="csv")
    export.add_argument("--output", default=None)
    export.add_argument("--package", action="store_true")
    commands.add_parser("report", help="show cumulative validation performance")
    commands.add_parser(
        "calibration-report",
        help="compare selected and observation score-band performance",
    )
    walk_forward = commands.add_parser(
        "walk-forward",
        help="run expanding-year out-of-sample validation",
    )
    walk_forward.add_argument("--history-start-year", required=True, type=int)
    walk_forward.add_argument("--first-test-year", required=True, type=int)
    walk_forward.add_argument("--last-test-year", required=True, type=int)
    walk_forward.add_argument("--holding-days", type=int, default=20)
    walk_forward.add_argument("--interval-months", type=int, default=1)
    walk_forward.add_argument("--top-n", type=int, default=5)
    walk_forward.add_argument("--success-return", type=float, default=0.03)
    walk_forward.add_argument(
        "--candidate-version",
        default=None,
        help="run a registered candidate configuration instead of V1",
    )
    daily = commands.add_parser(
        "daily",
        help="run selection and all matured validations once",
    )
    daily.add_argument("--date", required=True, type=datetime.fromisoformat)
    daily.add_argument("--top-n", type=int, default=5)
    daily.add_argument("--success-return", type=float, default=0.03)
    daily.add_argument(
        "--force",
        action="store_true",
        help="run even if the same date and strategy version completed",
    )
    commands.add_parser("check", help="check the V1 runtime configuration")
    commands.add_parser(
        "monitor",
        help="build KPI monitoring and anomaly status report",
    )
    propose = commands.add_parser(
        "strategy-propose",
        help="register an immutable strategy candidate",
    )
    propose.add_argument("--version", required=True)
    propose.add_argument("--description", required=True)
    propose.add_argument("--config", required=True, type=Path)
    propose.add_argument("--actor", required=True)
    evaluate = commands.add_parser(
        "strategy-evaluate",
        help="compare candidate and baseline walk-forward evidence",
    )
    evaluate.add_argument("--version", required=True)
    evaluate.add_argument("--baseline-result", required=True, type=Path)
    evaluate.add_argument("--candidate-result", required=True, type=Path)
    evaluate.add_argument("--actor", required=True)
    approve = commands.add_parser(
        "strategy-approve",
        help="approve a candidate that passed every gate",
    )
    approve.add_argument("--version", required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--note", required=True)
    research_generate = commands.add_parser(
        "strategy-research-generate",
        help="generate bounded offline strategy candidate configs",
    )
    research_generate.add_argument(
        "--output-dir", type=Path,
        default=Path("output/strategy_research/candidates"),
    )
    research_rank = commands.add_parser(
        "strategy-research-rank",
        help="rank existing walk-forward results without changing strategy",
    )
    research_rank.add_argument("--results-dir", required=True, type=Path)
    research_rank.add_argument("--minimum-trades", type=int, default=100)
    research_rank.add_argument(
        "--objective", choices=("absolute", "excess"), default="absolute",
        help="rank by cost-adjusted net return (default) or market excess return",
    )
    research_rank.add_argument(
        "--output", type=Path,
        default=Path("output/strategy_research/ranking.md"),
    )
    research_run = commands.add_parser(
        "strategy-research-run",
        help="run five representative research candidates out of sample",
    )
    research_run.add_argument("--history-start-year", type=int, default=2022)
    research_run.add_argument("--first-test-year", type=int, default=2023)
    research_run.add_argument("--last-test-year", type=int, default=2025)
    research_run.add_argument(
        "--active-data", type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
        help="isolated promoted data manifest used only by this research run",
    )
    research_run.add_argument("--holding-days", type=int, default=20)
    research_run.add_argument("--interval-months", type=int, default=1)
    research_run.add_argument("--weekly", action="store_true")
    research_run.add_argument(
        "--regime-experiment", action="store_true",
        help="run the three S78 weekly research-only regime filters",
    )
    research_run.add_argument(
        "--entry-experiment", action="store_true",
        help="run the S78 B-filter breakout-confirmation candidate",
    )
    research_run.add_argument(
        "--breakout-credit-experiment", action="store_true",
        help="run S78 B-filter candidates with bounded breakout threshold credit",
    )
    research_run.add_argument(
        "--challenger-experiment", action="store_true",
        help="compare breakout, pullback, and industry-RS research challengers",
    )
    research_run.add_argument(
        "--event-breakout-experiment", action="store_true",
        help="run daily first volume-confirmed breakout candidate G",
    )
    research_run.add_argument(
        "--candidate", action="append", default=[],
        help="run only the named research id; may be repeated",
    )
    shadow_run = commands.add_parser(
        "strategy-shadow-run",
        help="run the frozen A/C portfolio without placing orders",
    )
    shadow_run.add_argument("--date", type=datetime.fromisoformat)
    shadow_run.add_argument(
        "--active-data", type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    shadow_run.add_argument(
        "--freeze", type=Path,
        default=OUTPUT_DIR / "strategy_research" /
        "research_ac43_portfolio_v1.json",
    )
    shadow_run.add_argument(
        "--state", type=Path,
        default=OUTPUT_DIR / "strategy_shadow" / "ac43_state.json",
    )
    shadow_replay = commands.add_parser(
        "strategy-shadow-replay",
        help="replay a historical month into an isolated A/C shadow state",
    )
    shadow_replay.add_argument("--month", required=True)
    shadow_replay.add_argument(
        "--cadence", choices=("weekly", "daily"), default="weekly",
    )
    shadow_replay.add_argument(
        "--active-data", type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    shadow_replay.add_argument(
        "--freeze", type=Path,
        default=OUTPUT_DIR / "strategy_research" /
        "research_ac43_portfolio_v1.json",
    )
    shadow_replay.add_argument("--state", type=Path)
    weekday_test = commands.add_parser(
        "strategy-shadow-weekday-test",
        help="compare frozen A/C signals across exact weekdays",
    )
    weekday_test.add_argument("--start-month", required=True)
    weekday_test.add_argument("--end-month", required=True)
    weekday_test.add_argument(
        "--active-data", type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    weekday_test.add_argument(
        "--freeze", type=Path,
        default=OUTPUT_DIR / "strategy_research" /
        "research_ac43_portfolio_v1.json",
    )
    weekday_test.add_argument(
        "--output-dir", type=Path,
        default=OUTPUT_DIR / "strategy_shadow" / "weekday_tests",
    )
    monthly_rs = commands.add_parser(
        "strategy-monthly-rs-test",
        help="test research-only monthly relative-strength/low-volatility strategy",
    )
    monthly_rs.add_argument(
        "--active-data", type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    monthly_rs.add_argument("--start-year", type=int, default=2021)
    monthly_rs.add_argument("--end-date", type=date.fromisoformat)
    monthly_rs.add_argument(
        "--defensive", action="store_true",
        help="apply the pre-registered I-2 dual-horizon gate and close stop",
    )
    monthly_rs.add_argument(
        "--output-dir", type=Path,
        default=OUTPUT_DIR / "strategy_research",
    )
    adaptive_momentum = commands.add_parser(
        "strategy-adaptive-momentum-test",
        help="test research-only semi-monthly adaptive momentum strategy J",
    )
    adaptive_momentum.add_argument(
        "--active-data", type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    adaptive_momentum.add_argument("--start-year", type=int, default=2021)
    adaptive_momentum.add_argument("--end-date", type=date.fromisoformat)
    adaptive_momentum.add_argument(
        "--output-dir", type=Path, default=OUTPUT_DIR / "strategy_research",
    )
    scorecard = commands.add_parser(
        "strategy-research-scorecard",
        help="build a unified keep/observe/stop research decision table",
    )
    scorecard.add_argument(
        "--research-dir", type=Path, default=OUTPUT_DIR / "strategy_research",
    )
    horizon_test = commands.add_parser(
        "strategy-ac-horizon-test",
        help="compare frozen A/C signals at 10, 20, 40, and 60 sessions",
    )
    horizon_test.add_argument(
        "--active-data", type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    horizon_test.add_argument(
        "--artifact-root", type=Path,
        default=OUTPUT_DIR / "walk_forward" / "artifacts",
    )
    horizon_test.add_argument(
        "--output", type=Path,
        default=OUTPUT_DIR / "strategy_research" / "ac_holding_horizons.md",
    )
    exit_test = commands.add_parser(
        "strategy-ac-exit-test",
        help="compare fixed 40-day and alternative A4/C3 exit rules",
    )
    exit_test.add_argument("--active-data", type=Path, default=OUTPUT_DIR / "release" / "backtest_data.json")
    exit_test.add_argument("--artifact-root", type=Path, default=OUTPUT_DIR / "walk_forward" / "artifacts")
    exit_test.add_argument("--output", type=Path, default=OUTPUT_DIR / "strategy_research" / "ac_exit_comparison.md")
    ac_audit = commands.add_parser(
        "strategy-ac-audit",
        help="audit A4/C3 data, mechanics, robustness, and promotion gates",
    )
    ac_audit.add_argument(
        "--active-data", type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    ac_audit.add_argument(
        "--artifact-root", type=Path,
        default=OUTPUT_DIR / "walk_forward" / "artifacts",
    )
    ac_audit.add_argument(
        "--output-dir", type=Path, default=OUTPUT_DIR / "strategy_research",
    )
    universe = commands.add_parser(
        "universe-compile",
        help="validate and compile point-in-time universe history",
    )
    universe.add_argument("--input", required=True, type=Path)
    universe.add_argument("--source-manifest", required=True, type=Path)
    universe.add_argument("--coverage-start", required=True, type=date.fromisoformat)
    universe.add_argument("--coverage-end", required=True, type=date.fromisoformat)
    universe.add_argument("--output-dir", required=True, type=Path)
    krx_collect = commands.add_parser(
        "krx-universe-collect",
        help="collect official daily KRX universe snapshots with resume",
    )
    krx_collect.add_argument("--start", required=True, type=date.fromisoformat)
    krx_collect.add_argument("--end", required=True, type=date.fromisoformat)
    krx_collect.add_argument("--raw-dir", required=True, type=Path)
    krx_collect.add_argument("--max-requests", type=int, default=5000)
    krx_build = commands.add_parser(
        "krx-universe-build",
        help="normalize collected KRX snapshots into a staging universe",
    )
    krx_build.add_argument("--raw-dir", required=True, type=Path)
    krx_build.add_argument("--output-dir", required=True, type=Path)
    pilot = commands.add_parser(
        "kis-pilot",
        help="run isolated read-only KIS selection on a fixed small universe",
    )
    pilot.add_argument("--date", required=True, type=datetime.fromisoformat)
    pilot.add_argument("--top-n", type=int, default=5)
    pilot.add_argument(
        "--strategy-version",
        default="V1.1",
        help="registered strategy profile used for daily selection",
    )
    pilot.add_argument(
        "--universe-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "resources" / "pilot",
    )
    pilot.add_argument(
        "--active-data",
        type=Path,
        default=None,
        help="use the promoted point-in-time Top 500 V1 universe",
    )
    pilot.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR / "kis_pilot",
    )
    pilot.add_argument(
        "--prefer-local-history",
        action="store_true",
        help="use promoted local daily prices when they cover the requested date",
    )
    pilot_report = commands.add_parser(
        "kis-pilot-report",
        help="aggregate distinct KIS pilot dates and readiness",
    )
    pilot_report.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR / "kis_pilot",
    )
    pilot_report.add_argument("--required-days", type=int, default=5)
    freeze = commands.add_parser(
        "v1-freeze",
        help="freeze the code-derived V1 strategy and backtest specification",
    )
    freeze.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR / "release" / "v1.0.0" / "strategy_spec.json",
    )
    release_check = commands.add_parser(
        "v1-release-check",
        help="run the complete reproducible V1 audit and package evidence",
    )
    release_check.add_argument(
        "--release-dir",
        type=Path,
        default=OUTPUT_DIR / "release" / "v1.0.0",
    )
    release_check.add_argument(
        "--active-data",
        type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    preflight = commands.add_parser(
        "backtest-preflight",
        help="verify V1 data and assumptions before a formal backtest",
    )
    preflight.add_argument(
        "--spec",
        type=Path,
        default=OUTPUT_DIR / "release" / "v1.0.0" / "strategy_spec.json",
    )
    promote = commands.add_parser(
        "backtest-data-promote",
        help="activate reviewed immutable universe and price staging data",
    )
    promote.add_argument("--universe-dir", required=True, type=Path)
    promote.add_argument("--price-dir", required=True, type=Path)
    promote.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    prices = commands.add_parser(
        "price-history-compile",
        help="validate and compile adjusted historical OHLCV into staging",
    )
    prices.add_argument("--input", required=True, type=Path)
    prices.add_argument("--source-manifest", required=True, type=Path)
    prices.add_argument("--coverage-start", required=True, type=date.fromisoformat)
    prices.add_argument("--coverage-end", required=True, type=date.fromisoformat)
    prices.add_argument("--output-dir", required=True, type=Path)
    krx_prices = commands.add_parser(
        "krx-price-collect",
        help="collect official KRX daily trading snapshots with resume",
    )
    krx_prices.add_argument("--start", required=True, type=date.fromisoformat)
    krx_prices.add_argument("--end", required=True, type=date.fromisoformat)
    krx_prices.add_argument("--raw-dir", required=True, type=Path)
    krx_prices.add_argument("--max-requests", type=int, default=5000)
    krx_price_build = commands.add_parser(
        "krx-price-build",
        help="build conservatively corporate-action-adjusted price staging",
    )
    krx_price_build.add_argument("--universe-raw-dir", required=True, type=Path)
    krx_price_build.add_argument("--price-raw-dir", required=True, type=Path)
    krx_price_build.add_argument("--output-dir", required=True, type=Path)
    krx_price_build.add_argument(
        "--base-price-dir",
        type=Path,
        help="reuse an active compiled price directory and append new sessions",
    )
    industry_rs = commands.add_parser(
        "industry-rs-test",
        help="validate stock relative strength against industry peers",
    )
    industry_rs.add_argument("--start-date", default="2022-04-01")
    industry_rs.add_argument("--end-date", default="2023-09-01")
    industry_rs.add_argument(
        "--active-data",
        type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    industry_rs.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR / "industry_rs",
    )
    morning_manifest = commands.add_parser(
        "morning-entry-manifest",
        help="list next-session intraday bars needed for 10:00 entry research",
    )
    morning_manifest.add_argument("--runs-dir", required=True, type=Path)
    morning_manifest.add_argument("--strategy-version", required=True)
    morning_manifest.add_argument(
        "--candidate-field",
        choices=(
            "selected_candidates",
            "observation_candidates",
            "all_candidates",
        ),
        default="selected_candidates",
    )
    morning_manifest.add_argument("--start-date", type=date.fromisoformat)
    morning_manifest.add_argument("--end-date", type=date.fromisoformat)
    morning_manifest.add_argument(
        "--active-data",
        type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    morning_manifest.add_argument("--output", required=True, type=Path)
    morning_check = commands.add_parser(
        "morning-entry-check",
        help="evaluate 09:00-10:00 five-minute bars for stable entry",
    )
    morning_check.add_argument("--bars", required=True, type=Path)
    morning_check.add_argument("--previous-close", required=True, type=float)
    morning_check.add_argument("--maximum-gap", type=float, default=0.03)
    morning_check.add_argument("--maximum-range", type=float, default=0.04)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    banner()
    print(f"Environment : {settings.env}")
    logger.info("TITAN Started.")

    if args.command is None:
        print("Use check, select, validate, or report. Run with --help for details.")
        return 0

    if args.command == "check":
        ProviderFactory.create()
        stock_count = len(StockRepository().get_all())
        print("Runtime configuration: OK")
        print(f"Market provider: {settings.market_provider.upper()}")
        print(f"Stock universe: {stock_count}")
        costs = transaction_cost_policy_from_env()
        print(
            "Validation costs: "
            f"buy_fee={costs.buy_fee_rate:.4%}, "
            f"sell_fee={costs.sell_fee_rate:.4%}, "
            f"sell_tax={costs.sell_tax_rate:.4%}, "
            f"entry_slippage={costs.entry_slippage_rate:.4%}, "
            f"exit_slippage={costs.exit_slippage_rate:.4%}"
        )
        print("Network request: not performed")
        return 0

    if args.command == "backtest-data-promote":
        try:
            payload = promote_backtest_data(
                args.universe_dir, args.price_dir, args.output
            )
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"Backtest data promotion failed: {error}")
            return 2
        print(f"Backtest data promoted: {payload['status']}")
        print(f"Quality policy: {payload['quality_policy']}")
        print(f"Manifest: {args.output}")
        return 0

    if args.command == "industry-rs-test":
        try:
            result, paths = run_industry_rs_validation(
                args.active_data,
                args.output_dir,
                args.start_date,
                args.end_date,
            )
        except (
            OSError,
            TypeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            print(f"Industry RS validation failed: {error}")
            return 2
        print(
            f"Industry RS: {result['observation_count']} observations, "
            f"{result['validation_date_count']} validation dates"
        )
        print(f"Observations: {paths['csv']}")
        print(f"JSON: {paths['json']}")
        return 0

    if args.command == "morning-entry-manifest":
        try:
            _, price_dir, _ = load_active_backtest_data(args.active_data)
            top500 = json.loads(
                (price_dir / "market_cap_top500.json").read_text(encoding="utf-8")
            )
            sessions = sorted(
                datetime.fromisoformat(value) for value in top500["sessions"]
            )
            result = build_collection_manifest(
                args.runs_dir,
                sessions,
                args.output,
                args.strategy_version,
                candidate_field=args.candidate_field,
                start_date=args.start_date,
                end_date=args.end_date,
            )
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"Morning entry manifest failed: {error}")
            return 2
        print(f"Intraday targets: {result['target_count']}")
        print(f"Manifest: {args.output}")
        return 0

    if args.command == "morning-entry-check":
        try:
            result = evaluate_morning_bars(
                args.bars,
                args.previous_close,
                args.maximum_gap,
                args.maximum_range,
            )
        except (OSError, TypeError, ValueError, KeyError) as error:
            print(f"Morning entry check failed: {error}")
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "v1-release-check":
        try:
            manifest, exit_code = run_v1_release_check(
                args.release_dir,
                args.active_data,
            )
        except (
            OSError,
            TypeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            print(f"V1 release check failed: {error}")
            return 2
        print(f"V1 release status: {manifest['status']}")
        for name, passed in manifest["checks"].items():
            print(f"- {name}: {passed}")
        print(f"Manifest: {args.release_dir / 'release_manifest.json'}")
        return exit_code

    container = Container()
    if args.command == "kis-pilot":
        try:
            now = datetime.now()
            if (
                args.active_data is not None
                and args.date.date() == now.date()
                and now.time() < datetime.strptime("15:40", "%H:%M").time()
            ):
                raise ValueError(
                    "V1.1 pilot must run after 15:40 KST so the daily "
                    "candle is complete"
                )
            result = KisPilotRunner(
                args.universe_dir,
                args.output_dir,
                active_data_path=args.active_data,
                strategy_version=args.strategy_version,
                prefer_local_history=args.prefer_local_history,
            ).run(args.date, top_n=args.top_n)
        except (OSError, TypeError, ValueError, httpx.HTTPError) as error:
            print(f"KIS pilot failed: {error}")
            return 2
        print(generate_kis_pilot_markdown(result), end="")
        print(f"Report: {result.report_path}")
        if result.snapshot_path is not None:
            print(f"Selection snapshot: {result.snapshot_path}")
        return 0 if result.status == "PASS" else 3

    if args.command == "kis-pilot-report":
        try:
            readiness = PilotReadinessEvaluator(
                args.required_days
            ).evaluate(
                PilotHistoryRepository(
                    args.output_dir / "runs"
                ).load_all()
            )
        except (OSError, TypeError, ValueError) as error:
            print(f"KIS pilot report failed: {error}")
            return 2
        report = generate_pilot_readiness_markdown(readiness)
        report_directory = args.output_dir / "reports"
        report_directory.mkdir(parents=True, exist_ok=True)
        report_path = report_directory / "pilot_readiness.md"
        report_path.write_text(report, encoding="utf-8")
        print(report, end="")
        print(f"Report: {report_path}")
        return 0 if readiness.status == "READY" else 3

    if args.command == "v1-freeze":
        try:
            payload, digest = freeze_v1(args.output)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"V1 freeze failed: {error}")
            return 2
        print(f"V1 strategy frozen: {payload['strategy_version']}")
        print(f"Config SHA-256: {digest}")
        print(f"Specification: {args.output}")
        return 0

    if args.command == "backtest-preflight":
        try:
            universe_dir, price_dir, _ = load_active_backtest_data(
                OUTPUT_DIR / "release" / "backtest_data.json"
            )
            result = backtest_preflight(
                args.spec,
                universe_dir / "universe_manifest.json",
                universe_dir,
                price_dir,
            )
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"Backtest preflight failed: {error}")
            return 2
        report = preflight_markdown(result)
        report_path = OUTPUT_DIR / "reports" / "backtest_preflight.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        print(report, end="")
        print(f"Report: {report_path}")
        return 0 if result.status == "READY" else 3

    if args.command == "price-history-compile":
        try:
            if args.output_dir.resolve() == (OUTPUT_DIR / "market_data").resolve():
                raise ValueError(
                    "compile into a staging directory; do not overwrite active data"
                )
            source = json.loads(
                args.source_manifest.read_text(encoding="utf-8")
            )
            rows = PriceHistoryLoader().load(args.input)
            manifest = PriceHistoryCompiler().compile(
                rows, source, args.coverage_start, args.coverage_end,
                args.output_dir, args.input,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"Price history compilation failed: {error}")
            return 2
        print(
            f"Price history compiled: stocks={manifest['stock_count']}, "
            f"rows={manifest['row_count']}"
        )
        print(f"Output: {args.output_dir}")
        return 0

    if args.command == "krx-price-collect":
        try:
            repository = KrxPriceRawRepository(args.raw_dir)
            result = KrxPriceCollector(
                KrxPriceClient(os.getenv("KRX_AUTH_KEY", "")),
                repository,
            ).collect(args.start, args.end, args.max_requests)
            manifest = {
                "schema_version": 1,
                "source_name": "KRX Data Marketplace OPEN API",
                "dataset_id": "stk_bydd_trd+ksq_bydd_trd",
                "coverage_start": args.start.isoformat(),
                "coverage_end": args.end.isoformat(),
                "completed": result.completed,
                "api_calls": result.api_calls,
                "saved_responses": result.saved_responses,
                "skipped_cached": result.skipped_cached,
                "raw_sha256": repository.content_sha256(),
                "prices_adjusted": False,
            }
            args.raw_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = args.raw_dir / "collection_manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except (httpx.HTTPError, OSError, TypeError, ValueError) as error:
            print(f"KRX price collection failed: {error}")
            return 2
        print(
            f"KRX prices: completed={result.completed}, "
            f"calls={result.api_calls}, saved={result.saved_responses}, "
            f"cached={result.skipped_cached}"
        )
        print(f"Manifest: {manifest_path}")
        return 0 if result.completed else 3

    if args.command == "krx-price-build":
        try:
            if args.output_dir.resolve() == (OUTPUT_DIR / "market_data").resolve():
                raise ValueError(
                    "build into a staging directory; do not overwrite active data"
                )
            manifest = KrxAdjustedPriceCompiler().compile(
                args.universe_raw_dir,
                args.price_raw_dir,
                args.output_dir,
                base_price_dir=args.base_price_dir,
            )
        except (OSError, TypeError, ValueError, sqlite3.Error) as error:
            print(f"KRX adjusted price build failed: {error}")
            return 2
        print(
            f"KRX adjusted prices: stocks={manifest['stock_count']}, "
            f"rows={manifest['row_count']}, "
            f"actions={manifest['adjustment_event_count']}, "
            f"unresolved={manifest['unresolved_large_jump_count']}"
        )
        print(f"Output: {args.output_dir}")
        return 0

    if args.command == "daily":
        result = container.daily_operation_runner.run(
            operation_date=args.date,
            top_n=args.top_n,
            success_return=args.success_return,
            force=args.force,
        )
        print(result.report_markdown, end="")
        if result.run_path is not None:
            print(f"Run record: {result.run_path}")
        if result.report_path is not None:
            print(f"Report: {result.report_path}")
        return 2 if result.record.status.value == "FAILED" else 0

    if args.command == "monitor":
        snapshot = container.monitoring_engine.build(
            container.validation_repository.load_all(),
            container.run_repository.load_all(),
            container.data_quality_repository.load_all(),
        )
        report = generate_monitoring_markdown(snapshot)
        snapshot_path = container.monitoring_repository.save(snapshot)
        report_path = container.report_repository.save(
            "kpi_monitoring.md",
            report,
        )
        print(report, end="")
        print(f"Snapshot: {snapshot_path}")
        print(f"Report: {report_path}")
        return 0

    if args.command == "strategy-propose":
        try:
            config = json.loads(args.config.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("strategy config must be a JSON object")
            _validate_candidate_criteria(SelectionCriteria(**config))
            candidate = container.strategy_candidate_repository.propose(
                candidate_version=args.version,
                description=args.description,
                config=config,
                actor=args.actor,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"Strategy proposal failed: {error}")
            return 2
        report = generate_strategy_gate_markdown(candidate)
        report_path = container.report_repository.save(
            f"strategy_gate_{candidate.candidate_version}.md",
            report,
        )
        print(report, end="")
        print(f"Report: {report_path}")
        return 0

    if args.command == "strategy-research-generate":
        candidates = generate_bounded_candidates()
        manifest = save_candidate_grid(args.output_dir, candidates)
        print(f"Generated {len(candidates)} research-only candidates")
        print(f"Manifest: {manifest}")
        print("Operational strategy: unchanged")
        return 0

    if args.command == "strategy-research-rank":
        if args.minimum_trades <= 0:
            print("Strategy research ranking failed: minimum trades must be positive")
            return 2
        paths = sorted(args.results_dir.glob("walk_forward_result_*.json"))
        rows = rank_walk_forward_results(
            paths, args.minimum_trades, objective_kind=args.objective,
        )
        report = render_ranking_markdown(rows)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(report, end="")
        print(f"Report: {args.output}")
        print("Operational strategy: unchanged")
        return 0 if rows else 2

    if args.command == "strategy-research-run":
        plan = WalkForwardPlan.expanding_years(
            args.history_start_year, args.first_test_year, args.last_test_year,
        )
        candidates = representative_candidates(generate_bounded_candidates())
        research_data = json.loads(args.active_data.read_text(encoding="utf-8"))
        price_manifest = json.loads(
            (Path(research_data["price_dir"]) / "price_history_manifest.json")
            .read_text(encoding="utf-8")
        )
        data_start_year = date.fromisoformat(
            price_manifest["coverage_start"]
        ).year
        coverage_end = datetime.combine(
            date.fromisoformat(price_manifest["coverage_end"]),
            datetime.max.time(),
        )
        plan = WalkForwardPlan([
            replace(fold, test_end=min(fold.test_end, coverage_end))
            for fold in plan.folds
            if fold.test_start <= coverage_end
        ])
        research_top_n = 7
        research_interval_days = None
        if args.event_breakout_experiment:
            base = next(
                item for item in candidates
                if item["research_id"] == "s78-m55-mom12-t35-r10"
            )
            candidates = [{
                "research_id": "event-g-first-volume-breakout-h40",
                "config": {
                    **base["config"],
                    "research_market_filter": "exclude_short_slowdown",
                    "research_entry_filter": "first_volume_breakout20",
                },
                "holding_days": 40,
            }]
            research_top_n = 2
            research_interval_days = 1
        if args.challenger_experiment:
            base = next(
                item for item in candidates
                if item["research_id"] == "s78-m55-mom12-t35-r10"
            )
            shared = {
                **base["config"],
                "research_market_filter": "exclude_short_slowdown",
            }
            candidates = [
                {
                    "research_id": "challenger-a-breakout-h40",
                    "config": {
                        **shared,
                        "research_entry_filter": "new_high_or_breakout20",
                    },
                    "holding_days": 40,
                },
                {
                    "research_id": "challenger-b-pullback-h20",
                    "config": {
                        **shared,
                        "research_entry_filter": "recent_breakout_pullback",
                    },
                    "holding_days": 20,
                },
                {
                    "research_id": "challenger-c-pullback-h40",
                    "config": {
                        **shared,
                        "research_entry_filter": "recent_breakout_pullback",
                    },
                    "holding_days": 40,
                },
                {
                    "research_id": "challenger-d-industry-pullback-h40",
                    "config": {
                        **shared,
                        "research_entry_filter": "recent_breakout_pullback",
                        "research_peer_filter": "strong_industry_top30",
                    },
                    "holding_days": 40,
                },
                {
                    "research_id": "challenger-e-confirmed-pullback-h40",
                    "config": {
                        **shared,
                        "research_entry_filter": "confirmed_breakout_pullback",
                    },
                    "holding_days": 40,
                },
                {
                    "research_id": "challenger-f-volume-pullback-h40",
                    "config": {
                        **shared,
                        "research_entry_filter": "volume_confirmed_breakout_pullback",
                    },
                    "holding_days": 40,
                },
            ]
            research_top_n = 3
            args.weekly = True
            freeze_path = save_challenger_freeze(
                candidates,
                OUTPUT_DIR / "strategy_research" /
                "research_ac43_portfolio_v1.json",
            )
            print(f"Frozen research specification: {freeze_path}")
        if args.breakout_credit_experiment:
            base = next(
                item for item in candidates
                if item["research_id"] == "s78-m55-mom12-t35-r10"
            )
            candidates = [{
                "research_id": f"s78-m55-mom12-t35-r10-f-credit{credit}",
                "config": {
                    **base["config"],
                    "research_market_filter": "exclude_short_slowdown",
                    "research_breakout_threshold_credit": credit,
                },
            } for credit in (3, 5)]
            args.weekly = True
        if args.entry_experiment:
            base = next(
                item for item in candidates
                if item["research_id"] == "s78-m55-mom12-t35-r10"
            )
            candidates = [{
                "research_id": (
                    "s78-m55-mom12-t35-r10-e-breakout-"
                    f"h{args.holding_days}"
                ),
                "config": {
                    **base["config"],
                    "research_market_filter": "exclude_short_slowdown",
                    "research_entry_filter": "new_high_or_breakout20",
                },
            }]
            research_top_n = 3
            args.weekly = True
        if args.regime_experiment:
            base = next(
                item for item in candidates
                if item["research_id"] == "s78-m55-mom12-t35-r10"
            )
            candidates = []
            for suffix, mode in (
                ("b-no-slowdown", "exclude_short_slowdown"),
                ("c-strong-continuation", "strong_continuation"),
                ("d-continuation-mom20", "continuation_momentum20"),
            ):
                candidates.append({
                    "research_id": f"s78-m55-mom12-t35-r10-{suffix}",
                    "config": {
                        **base["config"], "research_market_filter": mode,
                    },
                })
            args.weekly = True
        if args.candidate:
            requested = set(args.candidate)
            candidates = [
                item for item in candidates if item["research_id"] in requested
            ]
            missing = requested - {item["research_id"] for item in candidates}
            if missing:
                print(
                    "Strategy research run failed: unknown representative "
                    f"candidate(s): {', '.join(sorted(missing))}"
                )
                return 2
        elif (
            args.weekly
            and not args.regime_experiment
            and not args.entry_experiment
            and not args.breakout_credit_experiment
            and not args.challenger_experiment
            and not args.event_breakout_experiment
        ):
            candidates = [item for item in candidates if item["research_id"] in (
                "s78-m55-mom12-t35-r10",
                "s80-m60-mom10-t30-r15",
                "s80-m60-mom10-t25-r20",
            )]
        for candidate in candidates:
            config = candidate["config"]
            criteria = SelectionCriteria(**config)
            _validate_candidate_criteria(criteria)
            config_hash = hashlib.sha256(json.dumps(
                config, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")).hexdigest()
            research_version = (
                f"research-{candidate['research_id']}-weekly"
                if args.weekly else f"research-{candidate['research_id']}"
            )
            if args.active_data.resolve() != (
                OUTPUT_DIR / "release" / "backtest_data.json"
            ).resolve():
                research_version += f"-hist{data_start_year}"
            engine = create_walk_forward_engine(
                strategy_version=research_version,
                criteria=criteria,
                strategy_config_hash=config_hash,
                active_data_path=args.active_data,
            )
            result = engine.run(
                plan,
                holding_days=candidate.get("holding_days", args.holding_days),
                interval_months=args.interval_months,
                top_n=research_top_n,
                interval_days=(
                    research_interval_days
                    if research_interval_days is not None
                    else 7 if args.weekly else None
                ),
            )
            path = container.walk_forward_repository.save(result)
            print(f"Completed {candidate['research_id']}: {path}")
        if args.challenger_experiment:
            artifact_dirs = sorted(
                (OUTPUT_DIR / "walk_forward" / "artifacts").glob(
                    "research-challenger-*-weekly"
                )
            )
            portfolio_path = save_portfolio_report(
                artifact_dirs,
                OUTPUT_DIR / "strategy_research" /
                "challenger_portfolio.md",
            )
            print(f"Portfolio report: {portfolio_path}")
            artifact_root = OUTPUT_DIR / "walk_forward" / "artifacts"
            suffix = f"-hist{data_start_year}" if data_start_year < 2022 else ""
            a_dir = artifact_root / (
                "research-challenger-a-breakout-h40-weekly" + suffix
            )
            c_dir = artifact_root / (
                "research-challenger-c-pullback-h40-weekly" + suffix
            )
            if a_dir.exists() and c_dir.exists():
                robustness_path = save_challenger_robustness_report(
                    a_dir, c_dir,
                    OUTPUT_DIR / "strategy_research" /
                    ("challenger_robustness" + suffix + ".md"),
                )
                print(f"Robustness report: {robustness_path}")
                diagnostics_path = save_stress_diagnostics(
                    {"A stable breakout": a_dir, "C post-breakout hold": c_dir},
                    OUTPUT_DIR / "strategy_research" /
                    ("challenger_stress_diagnostics" + suffix + ".md"),
                )
                print(f"Stress diagnostics: {diagnostics_path}")
        if args.event_breakout_experiment:
            artifact_dir = (
                OUTPUT_DIR / "walk_forward" / "artifacts" /
                "research-event-g-first-volume-breakout-h40"
            )
            event_report = save_portfolio_report(
                [artifact_dir],
                OUTPUT_DIR / "strategy_research" /
                "event_g_portfolio.md",
            )
            print(f"Event G portfolio report: {event_report}")
        print("Operational strategy: unchanged")
        return 0

    if args.command == "strategy-shadow-run":
        try:
            as_of = args.date or datetime.now()
            state = run_shadow_portfolio(
                as_of, args.active_data, args.freeze, args.state,
            )
            snapshot = save_weekly_snapshot(
                state, OUTPUT_DIR / "strategy_shadow" / "weekly_snapshots",
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"Strategy shadow run failed: {error}")
            return 2
        print(json.dumps(state["summary"], ensure_ascii=False, indent=2))
        print(f"State: {args.state}")
        print(f"Weekly snapshot: {snapshot['markdown_path']}")
        print("Operational orders: 0")
        return 0

    if args.command == "strategy-monthly-rs-test":
        try:
            result = run_monthly_relative_strength(
                args.active_data, args.output_dir, args.start_year, args.end_date,
                args.defensive,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"Monthly relative-strength test failed: {error}")
            return 2
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
        print(f"Report: {result['markdown_path']}")
        print("Operational strategy: unchanged; operational orders: 0")
        return 0

    if args.command == "strategy-adaptive-momentum-test":
        try:
            result = run_adaptive_momentum(
                args.active_data, args.output_dir, args.start_year, args.end_date,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"Adaptive momentum test failed: {error}")
            return 2
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
        print(f"Report: {result['markdown_path']}")
        print("Operational strategy: unchanged; operational orders: 0")
        return 0

    if args.command == "strategy-research-scorecard":
        try:
            path = save_research_scorecard(args.research_dir)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"Research scorecard failed: {error}")
            return 2
        print(f"Scorecard: {path}")
        print("Operational strategy: unchanged; operational orders: 0")
        return 0

    if args.command == "strategy-ac-horizon-test":
        suffix = "-hist2020" if "data_extensions" in str(args.active_data) else ""
        try:
            result = save_holding_horizon_report(
                args.active_data,
                {
                    "A": args.artifact_root / ("research-challenger-a-breakout-h40-weekly" + suffix),
                    "C": args.artifact_root / ("research-challenger-c-pullback-h40-weekly" + suffix),
                },
                args.output,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"A/C horizon test failed: {error}")
            return 2
        print(f"Report: {result['markdown_path']}")
        print("Operational strategy: unchanged; operational orders: 0")
        return 0

    if args.command == "strategy-ac-exit-test":
        suffix = "-hist2020" if "data_extensions" in str(args.active_data) else ""
        try:
            result = save_ac_exit_comparison(args.active_data, {
                "A": args.artifact_root / ("research-challenger-a-breakout-h40-weekly" + suffix),
                "C": args.artifact_root / ("research-challenger-c-pullback-h40-weekly" + suffix),
            }, args.output)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"A/C exit test failed: {error}")
            return 2
        print(f"Report: {result['markdown_path']}")
        print("Operational strategy: unchanged; operational orders: 0")
        return 0

    if args.command == "strategy-ac-audit":
        suffix = "-hist2020" if "data_extensions" in str(args.active_data) else ""
        weekday_files = sorted(
            (OUTPUT_DIR / "strategy_shadow" / "weekday_tests").glob("*-summary.json")
        )
        weekday_path = weekday_files[-1] if weekday_files else Path("missing.json")
        try:
            result = save_ac_audit(
                args.active_data,
                {
                    "A": args.artifact_root / ("research-challenger-a-breakout-h40-weekly" + suffix),
                    "C": args.artifact_root / ("research-challenger-c-pullback-h40-weekly" + suffix),
                },
                OUTPUT_DIR / "strategy_shadow" / "ac43_state.json",
                weekday_path,
                args.output_dir,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"A/C audit failed: {error}")
            return 2
        print(f"Verdict: {result['verdict']}")
        print(f"Report: {result['markdown_path']}")
        print("Operational strategy: unchanged; operational orders: 0")
        return 0

    if args.command == "strategy-shadow-replay":
        try:
            state_path = args.state or (
                OUTPUT_DIR / "strategy_shadow" / "replays" /
                f"{args.month}-{args.cadence}.json"
            )
            state = replay_shadow_month(
                args.month, args.cadence, args.active_data,
                args.freeze, state_path,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"Strategy shadow replay failed: {error}")
            return 2
        print(json.dumps(state["summary"], ensure_ascii=False, indent=2))
        print(f"Replay: {state_path}")
        print("Operational orders: 0")
        return 0

    if args.command == "strategy-shadow-weekday-test":
        try:
            result = replay_weekday_sensitivity(
                args.start_month, args.end_month, args.active_data,
                args.freeze, args.output_dir,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"Strategy weekday test failed: {error}")
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("Operational orders: 0")
        return 0

    if args.command == "strategy-evaluate":
        try:
            candidate = container.strategy_gate_service.evaluate(
                args.version,
                args.baseline_result,
                args.candidate_result,
                args.actor,
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"Strategy evaluation failed: {error}")
            return 2
        report = generate_strategy_gate_markdown(candidate)
        report_path = container.report_repository.save(
            f"strategy_gate_{candidate.candidate_version}.md",
            report,
        )
        print(report, end="")
        print(f"Report: {report_path}")
        return 0 if candidate.status.value == "PASSED" else 2

    if args.command == "strategy-approve":
        try:
            candidate = container.strategy_gate_service.approve(
                args.version,
                args.actor,
                args.note,
            )
        except (OSError, ValueError) as error:
            print(f"Strategy approval failed: {error}")
            return 2
        report = generate_strategy_gate_markdown(candidate)
        report_path = container.report_repository.save(
            f"strategy_gate_{candidate.candidate_version}.md",
            report,
        )
        print(report, end="")
        print(f"Report: {report_path}")
        return 0

    if args.command == "universe-compile":
        try:
            if args.output_dir.resolve() == (
                Path(__file__).resolve().parent.parent / "resources" / "market"
            ).resolve():
                raise ValueError(
                    "compile into a staging directory; do not overwrite "
                    "active market resources"
                )
            source_manifest = json.loads(
                args.source_manifest.read_text(encoding="utf-8")
            )
            if not isinstance(source_manifest, dict):
                raise ValueError("source manifest must be a JSON object")
            loader = UniverseHistoryLoader()
            compiler = UniverseHistoryCompiler()
            records = loader.load(args.input)
            manifest, validation = compiler.compile(
                records=records,
                source_manifest=source_manifest,
                coverage_start=args.coverage_start,
                coverage_end=args.coverage_end,
                output_dir=args.output_dir,
                input_sha256=compiler.file_sha256(args.input),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"Universe compilation failed: {error}")
            return 2
        report = generate_universe_history_markdown(manifest, validation)
        report_path = args.output_dir / "compilation_report.md"
        report_path.write_text(report, encoding="utf-8")
        print(report, end="")
        print(f"Compiled universe: {args.output_dir}")
        print(f"Report: {report_path}")
        return 0

    if args.command == "krx-universe-collect":
        try:
            repository = KrxRawRepository(args.raw_dir)
            result = KrxUniverseCollector(
                KrxUniverseClient(os.getenv("KRX_AUTH_KEY", "")),
                repository,
            ).collect(
                args.start,
                args.end,
                max_requests=args.max_requests,
            )
            manifest = {
                "schema_version": 1,
                "source_name": "KRX Data Marketplace OPEN API",
                "source_type": "official_daily_snapshots",
                "dataset_id": (
                    "stk_isu_base_info+ksq_isu_base_info"
                ),
                "evidence_url": (
                    "https://openapi.krx.co.kr/contents/OPP/INFO/"
                    "service/OPPINFO004.cmd"
                ),
                "acquired_at": datetime.now().astimezone().isoformat(),
                "coverage_start": args.start.isoformat(),
                "coverage_end": args.end.isoformat(),
                "source_complete": result.completed,
                "requested_dates": result.requested_dates,
                "api_calls": result.api_calls,
                "saved_responses": result.saved_responses,
                "skipped_cached": result.skipped_cached,
                "last_date": (
                    result.last_date.isoformat() if result.last_date else None
                ),
                "raw_sha256": repository.content_sha256(),
            }
            manifest_path = repository.save_collection_manifest(manifest)
        except (httpx.HTTPError, OSError, TypeError, ValueError) as error:
            print(f"KRX universe collection failed: {error}")
            return 2
        print(
            f"KRX collection: completed={result.completed}, "
            f"calls={result.api_calls}, saved={result.saved_responses}, "
            f"cached={result.skipped_cached}"
        )
        print(f"Manifest: {manifest_path}")
        return 0 if result.completed else 3

    if args.command == "krx-universe-build":
        try:
            active_market_dir = (
                Path(__file__).resolve().parent.parent / "resources" / "market"
            ).resolve()
            if args.output_dir.resolve() == active_market_dir:
                raise ValueError(
                    "build into a staging directory; do not overwrite "
                    "active market resources"
                )
            raw_repository = KrxRawRepository(args.raw_dir)
            collection_manifest_path = (
                args.raw_dir / "collection_manifest.json"
            )
            collection_manifest = json.loads(
                collection_manifest_path.read_text(encoding="utf-8")
            )
            if (
                collection_manifest.get("raw_sha256")
                != raw_repository.content_sha256()
            ):
                raise ValueError("raw KRX snapshot hash does not match manifest")
            records = KrxSnapshotNormalizer().normalize(args.raw_dir)
            compiler = UniverseHistoryCompiler()
            manifest, validation = compiler.compile(
                records,
                collection_manifest,
                date.fromisoformat(collection_manifest["coverage_start"]),
                date.fromisoformat(collection_manifest["coverage_end"]),
                args.output_dir,
                collection_manifest["raw_sha256"],
            )
        except (
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"KRX universe build failed: {error}")
            return 2
        report = generate_universe_history_markdown(manifest, validation)
        report_path = args.output_dir / "compilation_report.md"
        report_path.write_text(report, encoding="utf-8")
        print(report, end="")
        print(f"Compiled universe: {args.output_dir}")
        print(f"Report: {report_path}")
        return 0 if manifest["point_in_time_complete"] else 3

    if args.command == "select":
        result = container.runner.select(args.date, top_n=args.top_n)
        report = container.report_generator.generate_selection_markdown(
            result.selections,
            quality_summary=result.quality_summary,
            universe_snapshot=result.universe_snapshot,
        )
        report_path = container.report_repository.save(
            f"selection_{args.date:%Y%m%dT%H%M%S}.md",
            report,
        )
        print(report, end="")
        if result.snapshot_path is not None:
            print(f"Snapshot: {result.snapshot_path}")
        print(f"Observation cohort: {len(result.observations)}")
        if result.observation_snapshot_path is not None:
            print(f"Observation snapshot: {result.observation_snapshot_path}")
        if result.quality_report_path is not None:
            print(f"Data quality: {result.quality_report_path}")
        if result.universe_report_path is not None:
            print(f"Universe: {result.universe_report_path}")
        print(f"Report: {report_path}")
        return 0

    if args.command == "validate":
        try:
            result = container.deferred_validation_runner.run(
                selected_at=args.selection_date,
                evaluation_date=args.evaluation_date,
                holding_days=args.holding_days,
                success_return=args.success_return,
                trade_time=args.trade_time,
                sell_time=args.sell_time,
                market_trend_filter=args.market_trend_filter,
            )
        except (ValueError, FileNotFoundError) as error:
            print(f"Validation failed: {error}")
            return 2
        print(result.report_markdown, end="")
        report_path = container.report_repository.save(
            "validation_"
            f"{args.selection_date:%Y%m%dT%H%M%S}_"
            f"{args.evaluation_date:%Y%m%dT%H%M%S}.md",
            result.report_markdown,
        )
        print(f"Report: {report_path}")
        return 0

    if args.command == "validate-horizons":
        try:
            results = container.deferred_validation_runner.run_horizons(
                selected_at=args.selection_date,
                as_of=args.as_of,
                holding_days=args.holding_days,
                success_return=args.success_return,
                trade_time=args.trade_time,
                sell_time=args.sell_time,
                market_trend_filter=args.market_trend_filter,
            )
        except (ValueError, FileNotFoundError) as error:
            print(f"Multi-horizon validation failed: {error}")
            return 2
        report = container.report_generator.generate_horizon_markdown(results)
        report_path = container.report_repository.save(
            f"validation_horizons_{args.selection_date:%Y%m%dT%H%M%S}.md",
            report,
        )
        print(report, end="")
        print(f"Report: {report_path}")
        return 0

    if args.command == "validate-observations":
        try:
            results = container.observation_validation_runner.run_horizons(
                selected_at=args.selection_date,
                as_of=args.as_of,
                holding_days=args.holding_days,
                success_return=args.success_return,
            )
        except (ValueError, FileNotFoundError) as error:
            print(f"Observation validation failed: {error}")
            return 2
        report = container.report_generator.generate_horizon_markdown(results)
        report = report.replace(
            "# TITAN Multi-Horizon Validation Report",
            "# TITAN Observation Cohort Validation Report",
            1,
        )
        report_path = container.report_repository.save(
            f"observation_validation_{args.selection_date:%Y%m%dT%H%M%S}.md",
            report,
        )
        print(report, end="")
        print(f"Report: {report_path}")
        return 0

    if args.command == "export":
        records = ValidationRepository().load_all()
        if not records:
            print("No validation history to export.")
            return 2
        output_path = args.output
        exporter = ValidationExporter()
        if args.package:
            exported_path = exporter.export_package(
                records,
                output_path,
                fmt=args.format,
            )
            print(f"Exported package: {exported_path}")
            return 0
        if output_path is None:
            output_path = OUTPUT_DIR / "exports" / (
                "validation_export.csv"
                if args.format == "csv"
                else "validation_export.xlsx"
            )
        exported_path = exporter.export(records, output_path, fmt=args.format)
        print(f"Exported: {exported_path}")
        return 0

    if args.command == "calibration-report":
        selected_records = container.validation_repository.load_all()
        observation_records = ValidationRepository(
            OUTPUT_DIR / "observation_validations"
        ).load_all()
        records = selected_records + observation_records
        if not records:
            print("No selected or observation validation history.")
            return 2
        summary = container.validation_aggregator.aggregate(records)
        report = container.report_generator.generate_score_calibration_markdown(
            summary,
            selected_run_count=len(selected_records),
            observation_run_count=len(observation_records),
        )
        report_path = container.report_repository.save(
            "score_calibration.md",
            report,
        )
        print(report, end="")
        print(f"Report: {report_path}")
        return 0

    if args.command == "walk-forward":
        try:
            plan = WalkForwardPlan.expanding_years(
                args.history_start_year,
                args.first_test_year,
                args.last_test_year,
            )
            engine = container.walk_forward_engine
            if args.candidate_version:
                candidate = container.strategy_candidate_repository.load(
                    args.candidate_version
                )
                criteria = SelectionCriteria(**candidate.config)
                _validate_candidate_criteria(criteria)
                engine = create_walk_forward_engine(
                    strategy_version=candidate.candidate_version,
                    criteria=criteria,
                    strategy_config_hash=candidate.config_hash,
                )
            result = engine.run(
                plan,
                holding_days=args.holding_days,
                interval_months=args.interval_months,
                top_n=args.top_n,
                success_return=args.success_return,
            )
        except (FileNotFoundError, TypeError, ValueError) as error:
            print(f"Walk-forward validation failed: {error}")
            return 2
        report = container.report_generator.generate_walk_forward_markdown(result)
        report_path = container.report_repository.save(
            f"walk_forward_validation_{result.strategy_version}.md",
            report,
        )
        result_path = container.walk_forward_repository.save(result)
        print(report.replace("–", "-"), end="")
        print(f"Report: {report_path}")
        print(f"Result: {result_path}")
        return 0

    summary = container.validation_aggregator.aggregate(
        container.validation_repository.load_all()
    )
    report = container.report_generator.generate_cumulative_markdown(summary)
    report_path = container.report_repository.save("cumulative_validation.md", report)
    print(report, end="")
    print(f"Report: {report_path}")
    return 0


def _validate_candidate_criteria(criteria: SelectionCriteria) -> None:
    score_values = (
        criteria.buy_score,
        criteria.watch_score,
        criteria.minimum_score,
        criteria.minimum_trend_score,
        criteria.minimum_risk_score,
    )
    if any(not 0 <= value <= 100 for value in score_values):
        raise ValueError("candidate score thresholds must be between 0 and 100")
    if not 0 <= criteria.minimum_market_strength <= 1:
        raise ValueError("minimum_market_strength must be between 0 and 1")
    if criteria.maximum_momentum_5d <= 0:
        raise ValueError("maximum_momentum_5d must be greater than zero")
    weights = (
        criteria.trend_weight, criteria.momentum_weight,
        criteria.volume_weight, criteria.price_action_weight,
        criteria.risk_weight, criteria.context_weight,
    )
    if any(value < 0 for value in weights) or sum(weights) != 100:
        raise ValueError("candidate category weights must be non-negative and sum to 100")


if __name__ == "__main__":
    raise SystemExit(main())

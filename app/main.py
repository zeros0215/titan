"""TITAN V1 command-line entry point."""

import argparse
import json
import os
import httpx
import sqlite3
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
from analysis.sector_laggard import run_sector_laggard_backtest


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
    sector_laggard = commands.add_parser(
        "sector-laggard-test",
        help="backtest laggards inside rising peer groups",
    )
    sector_laggard.add_argument("--start-date", default="2022-04-01")
    sector_laggard.add_argument("--end-date", default="2023-09-01")
    sector_laggard.add_argument(
        "--active-data",
        type=Path,
        default=OUTPUT_DIR / "release" / "backtest_data.json",
    )
    sector_laggard.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR / "sector_laggard",
    )
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

    if args.command == "sector-laggard-test":
        try:
            result, paths = run_sector_laggard_backtest(
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
            print(f"Sector laggard test failed: {error}")
            return 2
        raw = result["summaries"]["RAW"]
        confirmed = result["summaries"]["CONFIRMED"]
        print(
            f"Sector laggard: raw={raw['trades']} trades, "
            f"confirmed={confirmed['trades']} trades"
        )
        print(f"Trades: {paths['csv']}")
        print(f"JSON: {paths['json']}")
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


if __name__ == "__main__":
    raise SystemExit(main())

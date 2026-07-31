from datetime import date, datetime
import unittest
from unittest.mock import patch

from app.main import build_parser, main


class AppCliTest(unittest.TestCase):
    def test_parses_selection_command(self) -> None:
        args = build_parser().parse_args([
            "select",
            "--date",
            "2026-07-27T00:00:00",
            "--top-n",
            "3",
        ])

        self.assertEqual(args.command, "select")
        self.assertEqual(args.date, datetime(2026, 7, 27))
        self.assertEqual(args.top_n, 3)

    def test_parses_validation_command(self) -> None:
        args = build_parser().parse_args([
            "validate",
            "--selection-date",
            "2026-07-01T00:00:00",
            "--evaluation-date",
            "2026-07-21T00:00:00",
            "--holding-days",
            "20",
        ])

        self.assertEqual(args.command, "validate")
        self.assertEqual(args.holding_days, 20)
        self.assertEqual(args.success_return, 0.03)

    def test_parses_cumulative_report_command(self) -> None:
        args = build_parser().parse_args(["report"])

        self.assertEqual(args.command, "report")

    def test_parses_multi_horizon_validation_command(self) -> None:
        args = build_parser().parse_args([
            "validate-horizons",
            "--selection-date", "2026-07-01",
            "--as-of", "2026-09-01",
            "--holding-days", "5", "10", "20", "40",
        ])

        self.assertEqual(args.command, "validate-horizons")
        self.assertEqual(args.holding_days, [5, 10, 20, 40])

    def test_parses_observation_validation_command(self) -> None:
        args = build_parser().parse_args([
            "validate-observations",
            "--selection-date", "2026-07-01",
            "--as-of", "2026-09-01",
        ])

        self.assertEqual(args.command, "validate-observations")
        self.assertEqual(args.holding_days, [5, 10, 20, 40])

    def test_parses_runtime_check_command(self) -> None:
        args = build_parser().parse_args(["check"])

        self.assertEqual(args.command, "check")

    def test_parses_calibration_report_command(self) -> None:
        args = build_parser().parse_args(["calibration-report"])

        self.assertEqual(args.command, "calibration-report")

    def test_parses_walk_forward_command(self) -> None:
        args = build_parser().parse_args([
            "walk-forward",
            "--history-start-year", "2022",
            "--first-test-year", "2023",
            "--last-test-year", "2025",
        ])

        self.assertEqual(args.command, "walk-forward")
        self.assertEqual(args.holding_days, 20)
        self.assertEqual(args.interval_months, 1)
        self.assertIsNone(args.candidate_version)

    def test_parses_daily_operation_command(self) -> None:
        args = build_parser().parse_args([
            "daily",
            "--date", "2026-07-28",
            "--top-n", "4",
            "--force",
        ])

        self.assertEqual(args.command, "daily")
        self.assertEqual(args.date, datetime(2026, 7, 28))
        self.assertEqual(args.top_n, 4)
        self.assertTrue(args.force)

    def test_parses_monitoring_command(self) -> None:
        args = build_parser().parse_args(["monitor"])

        self.assertEqual(args.command, "monitor")

    def test_parses_strategy_gate_commands(self) -> None:
        proposed = build_parser().parse_args([
            "strategy-propose",
            "--version", "1.1.0",
            "--description", "candidate",
            "--config", "candidate.json",
            "--actor", "tester",
        ])
        evaluated = build_parser().parse_args([
            "strategy-evaluate",
            "--version", "1.1.0",
            "--baseline-result", "baseline.json",
            "--candidate-result", "candidate-result.json",
            "--actor", "reviewer",
        ])
        approved = build_parser().parse_args([
            "strategy-approve",
            "--version", "1.1.0",
            "--actor", "owner",
            "--note", "reviewed",
        ])

        self.assertEqual("strategy-propose", proposed.command)
        self.assertEqual("strategy-evaluate", evaluated.command)
        self.assertEqual("strategy-approve", approved.command)

    def test_parses_universe_compile_command(self) -> None:
        args = build_parser().parse_args([
            "universe-compile",
            "--input", "history.csv",
            "--source-manifest", "source.json",
            "--coverage-start", "2020-01-01",
            "--coverage-end", "2025-12-31",
            "--output-dir", "output/universe_staging",
        ])

        self.assertEqual("universe-compile", args.command)
        self.assertEqual(date(2020, 1, 1), args.coverage_start)

    def test_parses_krx_universe_commands(self) -> None:
        collect = build_parser().parse_args([
            "krx-universe-collect",
            "--start", "2020-01-01",
            "--end", "2020-12-31",
            "--raw-dir", "output/krx_raw",
        ])
        build = build_parser().parse_args([
            "krx-universe-build",
            "--raw-dir", "output/krx_raw",
            "--output-dir", "output/universe_staging",
        ])

        self.assertEqual("krx-universe-collect", collect.command)
        self.assertEqual(5000, collect.max_requests)
        self.assertEqual("krx-universe-build", build.command)

    def test_parses_kis_pilot_command(self) -> None:
        args = build_parser().parse_args([
            "kis-pilot",
            "--date", "2026-07-28",
            "--top-n", "3",
            "--prefer-local-history",
        ])

        self.assertEqual("kis-pilot", args.command)
        self.assertEqual(3, args.top_n)
        self.assertTrue(args.prefer_local_history)

    def test_parses_kis_pilot_report_command(self) -> None:
        args = build_parser().parse_args([
            "kis-pilot-report",
            "--required-days", "5",
        ])

        self.assertEqual("kis-pilot-report", args.command)
        self.assertEqual(5, args.required_days)

    def test_parses_all_candidate_morning_manifest(self) -> None:
        args = build_parser().parse_args([
            "morning-entry-manifest",
            "--runs-dir", "output/kis_manual_tests/runs",
            "--strategy-version", "V1.3-S80-N7-TP5-SL10-CANDIDATE",
            "--candidate-field", "all_candidates",
            "--start-date", "2026-01-01",
            "--end-date", "2026-12-31",
            "--output", "output/morning_entry/manifest_2026.json",
        ])

        self.assertEqual("all_candidates", args.candidate_field)
        self.assertEqual(date(2026, 1, 1), args.start_date)

    def test_parses_v1_release_commands(self) -> None:
        frozen = build_parser().parse_args(["v1-freeze"])
        preflight = build_parser().parse_args(["backtest-preflight"])

        self.assertEqual("v1-freeze", frozen.command)

        release_check = build_parser().parse_args(["v1-release-check"])
        self.assertEqual("v1-release-check", release_check.command)
        self.assertEqual("backtest-preflight", preflight.command)

    def test_parses_price_history_compile_command(self) -> None:
        args = build_parser().parse_args([
            "price-history-compile",
            "--input", "prices.csv",
            "--source-manifest", "source.json",
            "--coverage-start", "2022-01-01",
            "--coverage-end", "2025-12-31",
            "--output-dir", "output/price_staging",
        ])

        self.assertEqual("price-history-compile", args.command)
        self.assertEqual(date(2022, 1, 1), args.coverage_start)

    def test_parses_krx_price_collect_command(self) -> None:
        args = build_parser().parse_args([
            "krx-price-collect",
            "--start", "2022-01-01",
            "--end", "2025-12-31",
            "--raw-dir", "output/krx_price_raw",
        ])

        self.assertEqual("krx-price-collect", args.command)
        self.assertEqual(5000, args.max_requests)

    def test_parses_krx_price_build_command(self) -> None:
        args = build_parser().parse_args([
            "krx-price-build",
            "--universe-raw-dir", "output/universe_raw",
            "--price-raw-dir", "output/price_raw",
            "--output-dir", "output/price_staging",
        ])

        self.assertEqual("krx-price-build", args.command)

    def test_parses_industry_rs_command(self) -> None:
        args = build_parser().parse_args([
            "industry-rs-test",
            "--end-date", "2023-09-01",
        ])

        self.assertEqual("industry-rs-test", args.command)
        self.assertEqual("2022-04-01", args.start_date)
        self.assertEqual("2023-09-01", args.end_date)

    @patch("app.main.StockRepository")
    @patch("app.main.ProviderFactory.create")
    def test_check_validates_local_runtime_without_network(
        self,
        create_provider,
        stock_repository,
    ) -> None:
        stock_repository.return_value.get_all.return_value = [object(), object()]

        exit_code = main(["check"])

        self.assertEqual(exit_code, 0)
        create_provider.assert_called_once()
        stock_repository.return_value.get_all.assert_called_once()


if __name__ == "__main__":
    unittest.main()

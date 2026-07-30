from validation.validation_result import ValidationResult
from validation.cumulative_validation_result import CumulativeValidationResult
from backtest.model.selection import Selection
from backtest.model.selection_result import SelectionResult
from validation.score_band_validation import assess_score_monotonicity
from data.quality import DataQualitySummary
from repository.universe_snapshot import UniverseSnapshot
from walkforward.result import WalkForwardResult


class ReportGenerator:
    """Renders a validation result without performing any calculations."""

    def generate_markdown(
        self,
        validation: ValidationResult,
        selection_results: list[SelectionResult] | None = None,
        success_return: float = 0.0,
    ) -> str:
        lines = [
            "# TITAN Selection Validation Report",
            "",
            "## Executive Summary",
            "",
            f"- **Outcome:** {self._summary_label(validation)}",
            f"- **Selections:** {validation.total_count}",
            f"- **Successes:** {validation.success_count}",
            f"- **Failures:** {validation.fail_count}",
            f"- **Win rate:** {validation.win_rate:.2%}",
            f"- **Average return:** {validation.average_return:.2%}",
            f"- **Average gross return:** {validation.average_gross_return:.2%}",
            f"- **Average net return:** {validation.average_net_return:.2%}",
            "",
            "## Performance Snapshot",
            "",
            self._build_return_summary(validation),
            "",
            "## Overall",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Selections | {validation.total_count} |",
            f"| Successes | {validation.success_count} |",
            f"| Failures | {validation.fail_count} |",
            f"| Win rate | {validation.win_rate:.2%} |",
            f"| Average return | {validation.average_return:.2%} |",
            f"| Average gross return | {validation.average_gross_return:.2%} |",
            f"| Average net return | {validation.average_net_return:.2%} |",
        ]

        if validation.average_benchmark_return is not None:
            lines.extend([
                f"| Average benchmark return | {validation.average_benchmark_return:.2%} |",
                f"| Average excess return | {validation.average_excess_return:.2%} |",
            ])

        self._append_feature_section(lines, validation)
        self._append_prediction_section(lines, validation)
        self._append_decision_section(lines, validation)
        self._append_context_section(lines, validation)
        self._append_feature_regime_section(lines, validation)
        self._append_score_band_section(lines, validation)
        self._append_trade_section(lines, selection_results, success_return)

        return "\n".join(lines) + "\n"

    def generate_cumulative_markdown(
        self,
        validation: CumulativeValidationResult,
    ) -> str:
        result = self.generate_markdown(ValidationResult(
            total_count=validation.total_count,
            success_count=validation.success_count,
            fail_count=validation.fail_count,
            win_rate=validation.win_rate,
            average_return=validation.average_return,
            feature_validations=validation.feature_validations,
            prediction_validations=validation.prediction_validations,
            decision_validations=validation.decision_validations,
            average_gross_return=validation.average_gross_return,
            average_net_return=validation.average_net_return,
            average_benchmark_return=validation.average_benchmark_return,
            average_excess_return=validation.average_excess_return,
            context_validations=validation.context_validations,
            feature_regime_validations=validation.feature_regime_validations,
            score_band_validations=validation.score_band_validations,
        ))
        result = result.replace(
            "# TITAN Selection Validation Report",
            "# TITAN Cumulative Selection Validation Report",
            1,
        )
        return result.replace(
            "## Overall",
            f"## Overall\n\nValidation runs: {validation.run_count}",
            1,
        )

    def generate_horizon_markdown(self, results: dict[int, object]) -> str:
        """Render comparable validation metrics by trading-session horizon."""
        lines = [
            "# TITAN Multi-Horizon Validation Report",
            "",
            "| Holding sessions | Evaluation date | Selections | Win rate | Gross return | Net return | Benchmark | Excess return |",
            "|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
        for days, item in sorted(results.items()):
            validation = item.validation
            evaluation_date = (
                item.backtest.results[0].evaluation_date
                if item.backtest.results
                else "N/A"
            )
            if evaluation_date != "N/A":
                evaluation_date = evaluation_date.isoformat()
            benchmark = (
                f"{validation.average_benchmark_return:.2%}"
                if validation.average_benchmark_return is not None
                else "N/A"
            )
            excess = (
                f"{validation.average_excess_return:.2%}"
                if validation.average_excess_return is not None
                else "N/A"
            )
            lines.append(
                f"| {days} | {evaluation_date} | {validation.total_count} | "
                f"{validation.win_rate:.2%} | "
                f"{validation.average_gross_return:.2%} | "
                f"{validation.average_net_return:.2%} | "
                f"{benchmark} | {excess} |"
            )
        return "\n".join(lines) + "\n"

    def generate_score_calibration_markdown(
        self,
        validation: CumulativeValidationResult,
        selected_run_count: int,
        observation_run_count: int,
    ) -> str:
        lines = [
            "# TITAN Score Calibration Report",
            "",
            f"- Selected validation runs: {selected_run_count}",
            f"- Observation validation runs: {observation_run_count}",
            "- Observation cohorts are statistical samples, not recommendations.",
        ]
        proxy = ValidationResult(
            total_count=validation.total_count,
            success_count=validation.success_count,
            fail_count=validation.fail_count,
            win_rate=validation.win_rate,
            average_return=validation.average_return,
            feature_validations=[],
            prediction_validations=[],
            decision_validations=[],
            score_band_validations=validation.score_band_validations,
        )
        self._append_score_band_section(lines, proxy)
        return "\n".join(lines) + "\n"

    def generate_walk_forward_markdown(
        self,
        result: WalkForwardResult,
    ) -> str:
        lines = [
            "# TITAN Walk-Forward Validation Report",
            "",
            f"- Strategy version: {result.strategy_version}",
            f"- Strategy frozen during test folds: {result.strategy_frozen}",
            f"- Holding sessions: {result.holding_days}",
            f"- Sampling interval: {result.interval_months} month(s)",
            "",
            "| Fold | Training period | Test period | Attempts | Completed | Selections | Win rate | Net return | Excess return | Universe coverage | Errors |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---|---:|",
        ]
        incomplete_universe = False
        for item in result.folds:
            net_return = item.weighted("average_net_return")
            excess_return = item.weighted("average_excess_return")
            coverages = sorted(set(item.universe_coverages)) or ["UNKNOWN"]
            if any(value != "COMPLETE" for value in coverages):
                incomplete_universe = True
            lines.append(
                f"| {item.fold.index} | "
                f"{item.fold.training_start.date()}–{item.fold.training_end.date()} | "
                f"{item.fold.test_start.date()}–{item.fold.test_end.date()} | "
                f"{item.attempted_dates} | {item.completed_dates} | "
                f"{item.total_count} | {item.win_rate:.2%} | "
                f"{self._optional_percent(net_return)} | "
                f"{self._optional_percent(excess_return)} | "
                f"{', '.join(coverages)} | {len(item.errors)} |"
            )
        if incomplete_universe:
            lines.extend([
                "",
                "> Warning: at least one fold lacks COMPLETE point-in-time "
                "universe coverage; survivorship bias may remain.",
            ])
        errors = [
            f"- Fold {item.fold.index}: {error}"
            for item in result.folds
            for error in item.errors
        ]
        if errors:
            lines.extend(["", "## Incomplete runs", "", *errors])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _optional_percent(value: float | None) -> str:
        return f"{value:.2%}" if value is not None else "N/A"

    def generate_selection_markdown(
        self,
        selections: list[Selection],
        quality_summary: DataQualitySummary | None = None,
        universe_snapshot: UniverseSnapshot | None = None,
    ) -> str:
        """Renders precomputed selection facts without changing their scores."""
        lines = ["# TITAN Selection Report", ""]
        self._append_quality_section(lines, quality_summary)
        self._append_universe_section(lines, universe_snapshot)
        if not selections:
            return "\n".join(
                lines + ["", "No candidates passed the selection criteria."]
            ) + "\n"

        selected_at = selections[0].selected_date.isoformat()
        best_selection = max(
            selections,
            key=lambda item: item.analysis.score.normalized_score,
        )
        lines.extend([
            "## Summary",
            "",
            f"- **Selection date:** {selected_at}",
            f"- **Candidates:** {len(selections)}",
            f"- **Top score:** {best_selection.analysis.score.normalized_score}",
            f"- **Top pick:** {best_selection.code} {best_selection.name}",
            "",
            "## Ranking",
            "",
            "| Rank | Code | Name | Score | Prediction | Decision |",
            "|---:|---|---|---:|---|---|",
        ])
        for selection in selections:
            analysis = selection.analysis
            prediction = (
                analysis.prediction.grade.value
                if analysis.prediction is not None else "-"
            )
            decision = (
                analysis.decision.decision.value
                if analysis.decision is not None else "-"
            )
            lines.append(
                f"| {selection.rank} | {selection.code} | {selection.name} | "
                f"{analysis.score.normalized_score} | {prediction} | {decision} |"
            )

        lines.extend(["", "## Selection rationale"])
        for selection in selections:
            analysis = selection.analysis
            lines.extend(["", f"### {selection.rank}. {selection.code} {selection.name}"])
            features = [feature.type.value for feature in analysis.features.enabled()]
            lines.append(f"- Enabled features: {', '.join(features) if features else '-'}")
            lines.append(
                "- Positive factors: "
                + ("; ".join(analysis.positive_factors) if analysis.positive_factors else "-")
            )
            lines.append(
                "- Negative factors: "
                + ("; ".join(analysis.negative_factors) if analysis.negative_factors else "-")
            )
            if analysis.context is not None:
                lines.append(
                    "- Market context: "
                    f"KOSPI {analysis.context.kospi_trend.value}, "
                    f"KOSDAQ {analysis.context.kosdaq_trend.value}, "
                    f"strength {analysis.context.market_strength:.2f}"
                )

        return "\n".join(lines) + "\n"

    @staticmethod
    def _append_quality_section(
        lines: list[str],
        summary: DataQualitySummary | None,
    ) -> None:
        if summary is None:
            return
        lines.extend([
            "## Data quality",
            "",
            f"- Total stocks: {summary.total_count}",
            f"- Valid: {summary.valid_count}",
            f"- Valid with warnings: {summary.warning_count}",
            f"- Excluded: {summary.excluded_count}",
        ])
        if summary.issues_by_code:
            lines.extend(["", "| Issue | Count |", "|---|---:|"])
            for code, count in summary.issues_by_code.items():
                lines.append(f"| {code} | {count} |")

    @staticmethod
    def _append_universe_section(
        lines: list[str],
        snapshot: UniverseSnapshot | None,
    ) -> None:
        if snapshot is None:
            return
        lines.extend([
            "",
            "## Point-in-time universe",
            "",
            f"- Coverage: **{snapshot.coverage.value}**",
            f"- Historical completeness declared: {snapshot.point_in_time_complete}",
            f"- Source records: {snapshot.source_count}",
            f"- Active records: {snapshot.active_count}",
            f"- Records with effective dates: {snapshot.dated_count}",
            f"- Unknown effective dates: {snapshot.unknown_date_count}",
            f"- Excluded before listing: {snapshot.excluded_before_listing}",
            f"- Excluded after delisting: {snapshot.excluded_after_delisting}",
        ])
        if not snapshot.point_in_time_complete:
            lines.extend([
                "",
                "> Warning: the source does not declare complete historical "
                "coverage; survivorship bias may remain.",
            ])

    @staticmethod
    def _summary_label(validation: ValidationResult) -> str:
        if validation.total_count == 0:
            return "No data"
        if validation.win_rate >= 0.5:
            return "Strong positive"
        if validation.win_rate >= 0.3:
            return "Mixed"
        if validation.average_return >= 0.0:
            return "Weak positive"
        return "Weak negative"

    @staticmethod
    def _build_return_summary(validation: ValidationResult) -> str:
        if validation.total_count == 0:
            return "No return data available."

        bars = [
            ("Win rate", validation.win_rate),
            ("Avg return", validation.average_return),
        ]
        lines = [
            "| Metric | Value | Trend |",
            "|---|---:|---|",
        ]
        for name, value in bars:
            bar_width = int(min(abs(value) * 20, 20))
            bar = "#" * bar_width if bar_width > 0 else "-"
            lines.append(f"| {name} | {value:.2%} | {bar} |")
        return "\n".join(lines)

    @staticmethod
    def _append_trade_section(
        lines: list[str],
        selection_results: list[SelectionResult] | None,
        success_return: float,
    ) -> None:
        lines.extend(["", "## Trades", ""])
        if not selection_results:
            lines.append("No trade details available.")
            return

        lines.extend([
            "| Rank | Code | Name | Selection price | Evaluation price | Gross return | Net return | Benchmark | Excess return | Outcome |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
        ])
        for item in sorted(selection_results, key=lambda entry: entry.rank):
            outcome = (
                "Success"
                if item.effective_return_rate >= success_return
                else "Failure"
            )
            benchmark = (
                f"{item.benchmark_return_rate:.2%}"
                if item.benchmark_return_rate is not None
                else "N/A"
            )
            excess = (
                f"{item.excess_return_rate:.2%}"
                if item.excess_return_rate is not None
                else "N/A"
            )
            lines.append(
                f"| {item.rank} | {item.code} | {item.name} | "
                f"{item.selection_price:.2f} | {item.evaluation_price:.2f} | "
                f"{item.return_rate:.2%} | {item.effective_return_rate:.2%} | "
                f"{benchmark} | {excess} | {outcome} |"
            )

    @staticmethod
    def _append_feature_section(
        lines: list[str],
        validation: ValidationResult,
    ) -> None:
        lines.extend(["", "## Feature performance", ""])
        if not validation.feature_validations:
            lines.append("No feature validation data.")
            return

        lines.extend([
            "| Feature | Selections | Win rate | Gross return | Net return | Benchmark | Excess return |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for item in validation.feature_validations:
            lines.append(
                f"| {item.feature_type.value} | {item.total_count} | "
                f"{item.win_rate:.2%} | {item.effective_gross_return:.2%} | "
                f"{item.average_return:.2%} | "
                f"{item.average_benchmark_return:.2%} | "
                f"{item.average_excess_return:.2%} |"
                if item.average_benchmark_return is not None
                else (
                    f"| {item.feature_type.value} | {item.total_count} | "
                    f"{item.win_rate:.2%} | {item.effective_gross_return:.2%} | "
                    f"{item.average_return:.2%} | N/A | N/A |"
                )
            )

    @staticmethod
    def _append_prediction_section(
        lines: list[str],
        validation: ValidationResult,
    ) -> None:
        lines.extend(["", "## Prediction performance", ""])
        if not validation.prediction_validations:
            lines.append("No prediction validation data.")
            return

        lines.extend([
            "| Prediction | Selections | Win rate | Average return |",
            "|---|---:|---:|---:|",
        ])
        for item in validation.prediction_validations:
            lines.append(
                f"| {item.grade.value} | {item.total_count} | "
                f"{item.win_rate:.2%} | {item.average_return:.2%} |"
            )

    @staticmethod
    def _append_decision_section(
        lines: list[str],
        validation: ValidationResult,
    ) -> None:
        lines.extend(["", "## Decision performance", ""])
        if not validation.decision_validations:
            lines.append("No decision validation data.")
            return

        lines.extend([
            "| Decision | Selections | Win rate | Average return |",
            "|---|---:|---:|---:|",
        ])
        for item in validation.decision_validations:
            lines.append(
                f"| {item.decision.value} | {item.total_count} | "
                f"{item.win_rate:.2%} | {item.average_return:.2%} |"
            )

    @staticmethod
    def _append_context_section(
        lines: list[str],
        validation: ValidationResult,
    ) -> None:
        lines.extend(["", "## Market Context performance", ""])
        if not validation.context_validations:
            lines.append("No market Context validation data.")
            return
        lines.extend([
            "| Regime | Selections | Market strength | Context score | Win rate | Gross return | Net return | Benchmark | Excess return |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for item in validation.context_validations:
            benchmark = (
                f"{item.average_benchmark_return:.2%}"
                if item.average_benchmark_return is not None
                else "N/A"
            )
            excess = (
                f"{item.average_excess_return:.2%}"
                if item.average_excess_return is not None
                else "N/A"
            )
            lines.append(
                f"| {item.regime.value} | {item.total_count} | "
                f"{item.average_market_strength:.2%} | "
                f"{item.average_context_score:.2f} | "
                f"{item.win_rate:.2%} | {item.average_gross_return:.2%} | "
                f"{item.average_return:.2%} | {benchmark} | {excess} |"
            )

    @staticmethod
    def _append_feature_regime_section(
        lines: list[str],
        validation: ValidationResult,
    ) -> None:
        lines.extend(["", "## Feature performance by market regime", ""])
        if not validation.feature_regime_validations:
            lines.append("No Feature-by-regime validation data.")
            return
        lines.extend([
            "| Feature | Regime | Selections | Win rate | Net return | Excess return |",
            "|---|---|---:|---:|---:|---:|",
        ])
        for item in validation.feature_regime_validations:
            excess = (
                f"{item.average_excess_return:.2%}"
                if item.average_excess_return is not None
                else "N/A"
            )
            lines.append(
                f"| {item.feature_type.value} | {item.regime.value} | "
                f"{item.total_count} | {item.win_rate:.2%} | "
                f"{item.average_return:.2%} | {excess} |"
            )

    @staticmethod
    def _append_score_band_section(
        lines: list[str],
        validation: ValidationResult,
    ) -> None:
        lines.extend(["", "## Score calibration", ""])
        if not validation.score_band_validations:
            lines.append("No score-band validation data.")
            return
        assessment = assess_score_monotonicity(
            validation.score_band_validations
        )
        lines.extend([
            f"Observed win-rate ordering: **{assessment}** "
            "(minimum 30 selections per score band).",
            "",
            "| Score band | Selections | Win rate | Gross return | Net return | Benchmark | Excess return |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for item in validation.score_band_validations:
            benchmark = (
                f"{item.average_benchmark_return:.2%}"
                if item.average_benchmark_return is not None
                else "N/A"
            )
            excess = (
                f"{item.average_excess_return:.2%}"
                if item.average_excess_return is not None
                else "N/A"
            )
            lines.append(
                f"| {item.label} | {item.total_count} | "
                f"{item.win_rate:.2%} | {item.average_gross_return:.2%} | "
                f"{item.average_return:.2%} | {benchmark} | {excess} |"
            )

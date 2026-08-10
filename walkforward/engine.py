from datetime import timedelta

from config.constants import VERSION
from walkforward.plan import WalkForwardPlan
from walkforward.result import WalkForwardFoldResult, WalkForwardResult


class WalkForwardEngine:
    """Replay frozen V1 rules through expanding out-of-sample year folds."""

    def __init__(
        self,
        selection_runner,
        validation_runner,
        strategy_version: str = VERSION,
        strategy_config_hash: str | None = None,
    ) -> None:
        self.selection_runner = selection_runner
        self.validation_runner = validation_runner
        self.strategy_version = strategy_version
        self.strategy_config_hash = strategy_config_hash

    def run(
        self,
        plan: WalkForwardPlan,
        holding_days: int = 20,
        interval_months: int = 1,
        top_n: int = 5,
        success_return: float = 0.03,
        interval_days: int | None = None,
    ) -> WalkForwardResult:
        if holding_days <= 0:
            raise ValueError("holding_days must be greater than zero")
        fold_results = []
        for fold in plan.folds:
            validations = []
            errors = []
            coverages = []
            dates = fold.selection_dates(interval_months, interval_days)
            completed = 0
            for selected_at in dates:
                try:
                    selection = self.selection_runner.select(
                        selected_at,
                        top_n=top_n,
                    )
                    if selection.universe_snapshot is not None:
                        coverages.append(
                            selection.universe_snapshot.coverage.value
                        )
                    if not selection.selections:
                        # A frozen strategy producing no signal is a valid
                        # out-of-sample observation, not an execution error.
                        completed += 1
                        continue
                    evaluation_as_of = selected_at + timedelta(
                        days=holding_days * 2 + 10
                    )
                    horizon = self.validation_runner.run_horizons(
                        selected_at=selected_at,
                        as_of=evaluation_as_of,
                        holding_days=[holding_days],
                        success_return=success_return,
                    )
                    validations.append(horizon[holding_days].validation)
                    completed += 1
                except (ValueError, FileNotFoundError) as error:
                    errors.append(f"{selected_at.date()}: {error}")
            fold_results.append(WalkForwardFoldResult(
                fold=fold,
                validations=validations,
                attempted_dates=len(dates),
                completed_dates=completed,
                errors=errors,
                universe_coverages=coverages,
            ))
        return WalkForwardResult(
            folds=fold_results,
            strategy_version=self.strategy_version,
            holding_days=holding_days,
            interval_months=interval_months,
            interval_days=interval_days,
            strategy_config_hash=self.strategy_config_hash,
        )

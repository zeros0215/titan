from __future__ import annotations

from validation.validation_result import ValidationResult
from backtest.model.backtest_result import BacktestResult
from backtest.model.selection_result import SelectionResult
from validation.decision_validation import DecisionValidation
from validation.feature_validation import FeatureValidation
from validation.prediction_validation import PredictionValidation
from validation.context_validation import ContextValidation
from market.context.market_regime import MarketRegimeClassifier
from validation.feature_regime_validation import FeatureRegimeValidation
from validation.score_band_validation import ScoreBandValidation, score_band_for


class Validator:
    """
    Backtest 결과를 검증한다.
    """

    def validate(
        self,
        result: BacktestResult,
        success_return: float = 0.0,
    ) -> ValidationResult:
        """
        Parameters
        ----------
        success_return

            성공으로 인정할 최소 수익률

            예)

            0.00 = 수익만 나면 성공

            0.05 = 5% 이상

            0.10 = 10% 이상
        """

        total, success, average = self._metrics(
            result.results,
            success_return,
        )

        benchmark_values = [
            item.benchmark_return_rate
            for item in result.results
            if item.benchmark_return_rate is not None
        ]
        excess_values = [
            item.excess_return_rate
            for item in result.results
            if item.excess_return_rate is not None
        ]
        return ValidationResult(
            total_count=total,
            success_count=success,
            fail_count=total - success,
            win_rate=success / total if total else 0.0,
            average_return=average,
            feature_validations=self._validate_features(
                result.results,
                success_return,
            ),
            prediction_validations=self._validate_predictions(
                result.results,
                success_return,
            ),
            decision_validations=self._validate_decisions(
                result.results,
                success_return,
            ),
            average_gross_return=self._average(
                [item.return_rate for item in result.results]
            ),
            average_net_return=average,
            average_benchmark_return=(
                self._average(benchmark_values) if benchmark_values else None
            ),
            average_excess_return=(
                self._average(excess_values) if excess_values else None
            ),
            context_validations=self._validate_contexts(
                result.results,
                success_return,
            ),
            feature_regime_validations=self._validate_feature_regimes(
                result.results,
                success_return,
            ),
            score_band_validations=self._validate_score_bands(
                result.results,
                success_return,
            ),
        )

    @staticmethod
    def _metrics(
        results: list[SelectionResult],
        success_return: float,
    ) -> tuple[int, int, float]:
        total = len(results)
        success = sum(
            item.effective_return_rate >= success_return
            for item in results
        )
        average = (
            sum(item.effective_return_rate for item in results) / total
            if total else 0.0
        )
        return total, success, average

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _validate_features(
        self,
        results: list[SelectionResult],
        success_return: float,
    ) -> list[FeatureValidation]:
        grouped: dict = {}
        for result in results:
            for feature in result.selection.analysis.features.enabled():
                grouped.setdefault(feature.type, []).append(result)

        return [
            self._feature_validation(
                feature_type,
                members,
                success_return,
            )
            for feature_type, members in sorted(
                grouped.items(),
                key=lambda item: item[0].value,
            )
        ]

    def _feature_validation(
        self,
        feature_type,
        members: list[SelectionResult],
        success_return: float,
    ) -> FeatureValidation:
        total, success, average = self._metrics(members, success_return)
        benchmarks = [
            item.benchmark_return_rate
            for item in members
            if item.benchmark_return_rate is not None
        ]
        excess = [
            item.excess_return_rate
            for item in members
            if item.excess_return_rate is not None
        ]
        return FeatureValidation(
            feature_type=feature_type,
            total_count=total,
            success_count=success,
            average_return=average,
            average_gross_return=self._average(
                [item.return_rate for item in members]
            ),
            average_benchmark_return=(
                self._average(benchmarks) if benchmarks else None
            ),
            average_excess_return=(
                self._average(excess) if excess else None
            ),
        )

    def _validate_predictions(
        self,
        results: list[SelectionResult],
        success_return: float,
    ) -> list[PredictionValidation]:
        grouped: dict = {}
        for result in results:
            prediction = result.selection.analysis.prediction
            if prediction is not None:
                grouped.setdefault(prediction.grade, []).append(result)

        return [
            PredictionValidation(
                grade=grade,
                total_count=metrics[0],
                success_count=metrics[1],
                average_return=metrics[2],
            )
            for grade, members in sorted(
                grouped.items(),
                key=lambda item: item[0].value,
            )
            if (metrics := self._metrics(members, success_return))
        ]

    def _validate_decisions(
        self,
        results: list[SelectionResult],
        success_return: float,
    ) -> list[DecisionValidation]:
        grouped: dict = {}
        for result in results:
            decision = result.selection.analysis.decision
            if decision is not None:
                grouped.setdefault(decision.decision, []).append(result)

        return [
            DecisionValidation(
                decision=decision,
                total_count=metrics[0],
                success_count=metrics[1],
                average_return=metrics[2],
            )
            for decision, members in sorted(
                grouped.items(),
                key=lambda item: item[0].value,
            )
            if (metrics := self._metrics(members, success_return))
        ]

    def _validate_contexts(
        self,
        results: list[SelectionResult],
        success_return: float,
    ) -> list[ContextValidation]:
        grouped: dict = {}
        for result in results:
            context = result.selection.analysis.context
            if context is not None:
                regime = MarketRegimeClassifier.classify(context)
                grouped.setdefault(regime, []).append(result)

        validations = []
        for regime, members in sorted(
            grouped.items(),
            key=lambda item: item[0].value,
        ):
            total, success, average = self._metrics(members, success_return)
            benchmarks = [
                item.benchmark_return_rate
                for item in members
                if item.benchmark_return_rate is not None
            ]
            excess = [
                item.excess_return_rate
                for item in members
                if item.excess_return_rate is not None
            ]
            validations.append(ContextValidation(
                regime=regime,
                total_count=total,
                success_count=success,
                average_return=average,
                average_gross_return=self._average(
                    [item.return_rate for item in members]
                ),
                average_benchmark_return=(
                    self._average(benchmarks) if benchmarks else None
                ),
                average_excess_return=(
                    self._average(excess) if excess else None
                ),
                average_market_strength=self._average([
                    item.selection.analysis.context.market_strength
                    for item in members
                ]),
                average_context_score=self._average([
                    item.selection.analysis.score.context_score
                    for item in members
                ]),
            ))
        return validations

    def _validate_feature_regimes(
        self,
        results: list[SelectionResult],
        success_return: float,
    ) -> list[FeatureRegimeValidation]:
        grouped: dict = {}
        for result in results:
            context = result.selection.analysis.context
            if context is None:
                continue
            regime = MarketRegimeClassifier.classify(context)
            for feature in result.selection.analysis.features.enabled():
                grouped.setdefault((feature.type, regime), []).append(result)

        validations = []
        for (feature_type, regime), members in sorted(
            grouped.items(),
            key=lambda item: (item[0][0].value, item[0][1].value),
        ):
            feature = self._feature_validation(
                feature_type,
                members,
                success_return,
            )
            validations.append(FeatureRegimeValidation(
                feature_type=feature_type,
                regime=regime,
                total_count=feature.total_count,
                success_count=feature.success_count,
                average_return=feature.average_return,
                average_gross_return=feature.average_gross_return,
                average_benchmark_return=feature.average_benchmark_return,
                average_excess_return=feature.average_excess_return,
            ))
        return validations

    def _validate_score_bands(
        self,
        results: list[SelectionResult],
        success_return: float,
    ) -> list[ScoreBandValidation]:
        grouped: dict = {}
        for result in results:
            score = result.selection.analysis.score.normalized_score
            band = score_band_for(score)
            grouped.setdefault((band.minimum, band.maximum), []).append(result)

        validations = []
        for (minimum, maximum), members in sorted(grouped.items()):
            total, success, average = self._metrics(members, success_return)
            benchmarks = [
                item.benchmark_return_rate
                for item in members
                if item.benchmark_return_rate is not None
            ]
            excess = [
                item.excess_return_rate
                for item in members
                if item.excess_return_rate is not None
            ]
            validations.append(ScoreBandValidation(
                minimum_score=minimum,
                maximum_score=maximum,
                total_count=total,
                success_count=success,
                average_return=average,
                average_gross_return=self._average(
                    [item.return_rate for item in members]
                ),
                average_benchmark_return=(
                    self._average(benchmarks) if benchmarks else None
                ),
                average_excess_return=(
                    self._average(excess) if excess else None
                ),
            ))
        return validations

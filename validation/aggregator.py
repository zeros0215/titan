from validation.cumulative_validation_result import CumulativeValidationResult
from validation.decision_validation import DecisionValidation
from validation.feature_validation import FeatureValidation
from validation.prediction_validation import PredictionValidation
from validation.validation_record import ValidationRecord
from validation.context_validation import ContextValidation
from validation.feature_regime_validation import FeatureRegimeValidation
from validation.score_band_validation import ScoreBandValidation


class ValidationAggregator:
    """Aggregates completed validation runs using selection-count weights."""

    def aggregate(
        self,
        records: list[ValidationRecord],
    ) -> CumulativeValidationResult:
        total_count = sum(record.result.total_count for record in records)
        success_count = sum(record.result.success_count for record in records)
        weighted_return = sum(
            record.result.average_return * record.result.total_count
            for record in records
        )
        benchmark_records = [
            record
            for record in records
            if record.result.average_benchmark_return is not None
        ]
        benchmark_count = sum(
            record.result.total_count for record in benchmark_records
        )
        return CumulativeValidationResult(
            run_count=len(records),
            total_count=total_count,
            success_count=success_count,
            fail_count=total_count - success_count,
            win_rate=success_count / total_count if total_count else 0.0,
            average_return=weighted_return / total_count if total_count else 0.0,
            feature_validations=self._features(records),
            prediction_validations=self._predictions(records),
            decision_validations=self._decisions(records),
            average_gross_return=self._weighted_average(
                records,
                "average_gross_return",
            ),
            average_net_return=self._weighted_average(
                records,
                "average_net_return",
            ),
            average_benchmark_return=(
                sum(
                    record.result.average_benchmark_return
                    * record.result.total_count
                    for record in benchmark_records
                ) / benchmark_count
                if benchmark_count else None
            ),
            average_excess_return=self._weighted_optional_average(
                records,
                "average_excess_return",
            ),
            context_validations=self._contexts(records),
            feature_regime_validations=self._feature_regimes(records),
            score_band_validations=self._score_bands(records),
        )

    @staticmethod
    def _weighted_average(
        records: list[ValidationRecord],
        attribute: str,
    ) -> float:
        total = sum(record.result.total_count for record in records)
        if not total:
            return 0.0
        return sum(
            getattr(record.result, attribute) * record.result.total_count
            for record in records
        ) / total

    @staticmethod
    def _weighted_optional_average(
        records: list[ValidationRecord],
        attribute: str,
    ) -> float | None:
        available = [
            record
            for record in records
            if getattr(record.result, attribute) is not None
        ]
        total = sum(record.result.total_count for record in available)
        if not total:
            return None
        return sum(
            getattr(record.result, attribute) * record.result.total_count
            for record in available
        ) / total

    @staticmethod
    def _features(records: list[ValidationRecord]) -> list[FeatureValidation]:
        grouped = {}
        for record in records:
            for item in record.result.feature_validations:
                grouped.setdefault(item.feature_type, []).append(item)
        return [
            ValidationAggregator._aggregate_feature(key, items)
            for key, items in sorted(
                grouped.items(),
                key=lambda item: item[0].value,
            )
        ]

    @staticmethod
    def _aggregate_feature(key, items) -> FeatureValidation:
        total = sum(item.total_count for item in items)
        return FeatureValidation(
            feature_type=key,
            total_count=total,
            success_count=sum(item.success_count for item in items),
            average_return=sum(
                item.average_return * item.total_count for item in items
            ) / total,
            average_gross_return=sum(
                item.effective_gross_return * item.total_count for item in items
            ) / total,
            average_benchmark_return=ValidationAggregator._weighted_context_optional(
                items,
                "average_benchmark_return",
            ),
            average_excess_return=ValidationAggregator._weighted_context_optional(
                items,
                "average_excess_return",
            ),
        )

    @staticmethod
    def _predictions(records: list[ValidationRecord]) -> list[PredictionValidation]:
        grouped = {}
        for record in records:
            for item in record.result.prediction_validations:
                grouped.setdefault(item.grade, []).append(item)
        return [
            PredictionValidation(key, total, success, total_return / total)
            for key, total, success, total_return in ValidationAggregator._totals(grouped)
        ]

    @staticmethod
    def _decisions(records: list[ValidationRecord]) -> list[DecisionValidation]:
        grouped = {}
        for record in records:
            for item in record.result.decision_validations:
                grouped.setdefault(item.decision, []).append(item)
        return [
            DecisionValidation(key, total, success, total_return / total)
            for key, total, success, total_return in ValidationAggregator._totals(grouped)
        ]

    @staticmethod
    def _contexts(records: list[ValidationRecord]) -> list[ContextValidation]:
        grouped = {}
        for record in records:
            for item in record.result.context_validations:
                grouped.setdefault(item.regime, []).append(item)
        results = []
        for regime, items in sorted(grouped.items(), key=lambda item: item[0].value):
            total = sum(item.total_count for item in items)
            success = sum(item.success_count for item in items)
            gross = sum(
                item.average_gross_return * item.total_count for item in items
            ) / total
            average = sum(
                item.average_return * item.total_count for item in items
            ) / total
            benchmark = ValidationAggregator._weighted_context_optional(
                items,
                "average_benchmark_return",
            )
            excess = ValidationAggregator._weighted_context_optional(
                items,
                "average_excess_return",
            )
            results.append(ContextValidation(
                regime=regime,
                total_count=total,
                success_count=success,
                average_return=average,
                average_gross_return=gross,
                average_benchmark_return=benchmark,
                average_excess_return=excess,
                average_market_strength=sum(
                    item.average_market_strength * item.total_count
                    for item in items
                ) / total,
                average_context_score=sum(
                    item.average_context_score * item.total_count
                    for item in items
                ) / total,
            ))
        return results

    @staticmethod
    def _feature_regimes(
        records: list[ValidationRecord],
    ) -> list[FeatureRegimeValidation]:
        grouped = {}
        for record in records:
            for item in record.result.feature_regime_validations:
                grouped.setdefault((item.feature_type, item.regime), []).append(item)
        results = []
        for (feature_type, regime), items in sorted(
            grouped.items(),
            key=lambda item: (item[0][0].value, item[0][1].value),
        ):
            total = sum(item.total_count for item in items)
            results.append(FeatureRegimeValidation(
                feature_type=feature_type,
                regime=regime,
                total_count=total,
                success_count=sum(item.success_count for item in items),
                average_return=sum(
                    item.average_return * item.total_count for item in items
                ) / total,
                average_gross_return=sum(
                    item.average_gross_return * item.total_count for item in items
                ) / total,
                average_benchmark_return=(
                    ValidationAggregator._weighted_context_optional(
                        items,
                        "average_benchmark_return",
                    )
                ),
                average_excess_return=(
                    ValidationAggregator._weighted_context_optional(
                        items,
                        "average_excess_return",
                    )
                ),
            ))
        return results

    @staticmethod
    def _score_bands(
        records: list[ValidationRecord],
    ) -> list[ScoreBandValidation]:
        grouped = {}
        for record in records:
            for item in record.result.score_band_validations:
                grouped.setdefault(
                    (item.minimum_score, item.maximum_score),
                    [],
                ).append(item)
        results = []
        for (minimum, maximum), items in sorted(grouped.items()):
            total = sum(item.total_count for item in items)
            results.append(ScoreBandValidation(
                minimum_score=minimum,
                maximum_score=maximum,
                total_count=total,
                success_count=sum(item.success_count for item in items),
                average_return=sum(
                    item.average_return * item.total_count for item in items
                ) / total,
                average_gross_return=sum(
                    item.average_gross_return * item.total_count for item in items
                ) / total,
                average_benchmark_return=(
                    ValidationAggregator._weighted_context_optional(
                        items,
                        "average_benchmark_return",
                    )
                ),
                average_excess_return=(
                    ValidationAggregator._weighted_context_optional(
                        items,
                        "average_excess_return",
                    )
                ),
            ))
        return results

    @staticmethod
    def _weighted_context_optional(items: list, attribute: str) -> float | None:
        available = [item for item in items if getattr(item, attribute) is not None]
        total = sum(item.total_count for item in available)
        if not total:
            return None
        return sum(
            getattr(item, attribute) * item.total_count for item in available
        ) / total

    @staticmethod
    def _totals(grouped: dict) -> list[tuple]:
        totals = []
        for key, items in grouped.items():
            total = sum(item.total_count for item in items)
            success = sum(item.success_count for item in items)
            total_return = sum(item.average_return * item.total_count for item in items)
            totals.append((key, total, success, total_return))
        return sorted(totals, key=lambda item: item[0].value)

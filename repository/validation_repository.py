import json
from datetime import datetime
from pathlib import Path

from config.constants import OUTPUT_DIR
from decision.decision_type import DecisionType
from feature.feature_type import FeatureType
from prediction.prediction_grade import PredictionGrade
from validation.decision_validation import DecisionValidation
from validation.feature_validation import FeatureValidation
from validation.prediction_validation import PredictionValidation
from validation.validation_record import ValidationRecord
from validation.validation_result import ValidationResult
from validation.context_validation import ContextValidation
from market.context.market_regime import MarketRegime
from validation.feature_regime_validation import FeatureRegimeValidation
from validation.score_band_validation import ScoreBandValidation


class ValidationRepository:
    """Stores completed validation runs for cumulative V1 performance reports."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or OUTPUT_DIR / "validations"

    def save(self, record: ValidationRecord) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (
            f"{record.selected_at:%Y%m%dT%H%M%S}_"
            f"{record.evaluation_date:%Y%m%dT%H%M%S}.json"
        )
        path.write_text(
            json.dumps(self._serialize(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load_all(self) -> list[ValidationRecord]:
        if not self.directory.exists():
            return []
        return [
            self._deserialize(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(self.directory.glob("*.json"))
        ]

    def exists(self, selected_at: datetime, holding_days: int) -> bool:
        """Check whether a horizon was already validated for a snapshot."""
        return any(
            record.selected_at == selected_at
            and record.holding_days == holding_days
            for record in self.load_all()
        )

    @staticmethod
    def _serialize(record: ValidationRecord) -> dict:
        result = record.result
        return {
            "selected_at": record.selected_at.isoformat(),
            "evaluation_date": record.evaluation_date.isoformat(),
            "holding_days": record.holding_days,
            "success_return": record.success_return,
            "result": {
                "total_count": result.total_count,
                "success_count": result.success_count,
                "fail_count": result.fail_count,
                "win_rate": result.win_rate,
                "average_return": result.average_return,
                "average_gross_return": result.average_gross_return,
                "average_net_return": result.average_net_return,
                "average_benchmark_return": result.average_benchmark_return,
                "average_excess_return": result.average_excess_return,
                "features": [
                    {
                        "feature": item.feature_type.value,
                        "total_count": item.total_count,
                        "success_count": item.success_count,
                        "average_return": item.average_return,
                        "average_gross_return": item.effective_gross_return,
                        "average_benchmark_return": item.average_benchmark_return,
                        "average_excess_return": item.average_excess_return,
                    }
                    for item in result.feature_validations
                ],
                "feature_regimes": [
                    {
                        "feature": item.feature_type.value,
                        "regime": item.regime.value,
                        "total_count": item.total_count,
                        "success_count": item.success_count,
                        "average_return": item.average_return,
                        "average_gross_return": item.average_gross_return,
                        "average_benchmark_return": item.average_benchmark_return,
                        "average_excess_return": item.average_excess_return,
                    }
                    for item in result.feature_regime_validations
                ],
                "score_bands": [
                    {
                        "minimum_score": item.minimum_score,
                        "maximum_score": item.maximum_score,
                        "total_count": item.total_count,
                        "success_count": item.success_count,
                        "average_return": item.average_return,
                        "average_gross_return": item.average_gross_return,
                        "average_benchmark_return": item.average_benchmark_return,
                        "average_excess_return": item.average_excess_return,
                    }
                    for item in result.score_band_validations
                ],
                "predictions": [
                    [item.grade.value, item.total_count, item.success_count, item.average_return]
                    for item in result.prediction_validations
                ],
                "decisions": [
                    [item.decision.value, item.total_count, item.success_count, item.average_return]
                    for item in result.decision_validations
                ],
                "contexts": [
                    {
                        "regime": item.regime.value,
                        "total_count": item.total_count,
                        "success_count": item.success_count,
                        "average_return": item.average_return,
                        "average_gross_return": item.average_gross_return,
                        "average_benchmark_return": item.average_benchmark_return,
                        "average_excess_return": item.average_excess_return,
                        "average_market_strength": item.average_market_strength,
                        "average_context_score": item.average_context_score,
                    }
                    for item in result.context_validations
                ],
            },
        }

    @staticmethod
    def _deserialize(payload: dict) -> ValidationRecord:
        result = payload["result"]
        return ValidationRecord(
            selected_at=datetime.fromisoformat(payload["selected_at"]),
            evaluation_date=datetime.fromisoformat(payload["evaluation_date"]),
            holding_days=payload["holding_days"],
            success_return=payload["success_return"],
            result=ValidationResult(
                total_count=result["total_count"],
                success_count=result["success_count"],
                fail_count=result["fail_count"],
                win_rate=result["win_rate"],
                average_return=result["average_return"],
                feature_validations=[
                    ValidationRepository._deserialize_feature(item)
                    for item in result["features"]
                ],
                prediction_validations=[
                    PredictionValidation(PredictionGrade(key), total, success, average)
                    for key, total, success, average in result["predictions"]
                ],
                decision_validations=[
                    DecisionValidation(DecisionType(key), total, success, average)
                    for key, total, success, average in result["decisions"]
                ],
                average_gross_return=result.get(
                    "average_gross_return",
                    result["average_return"],
                ),
                average_net_return=result.get(
                    "average_net_return",
                    result["average_return"],
                ),
                average_benchmark_return=result.get("average_benchmark_return"),
                average_excess_return=result.get("average_excess_return"),
                context_validations=[
                    ContextValidation(
                        regime=MarketRegime(item["regime"]),
                        total_count=item["total_count"],
                        success_count=item["success_count"],
                        average_return=item["average_return"],
                        average_gross_return=item.get(
                            "average_gross_return",
                            item["average_return"],
                        ),
                        average_benchmark_return=item.get(
                            "average_benchmark_return"
                        ),
                        average_excess_return=item.get("average_excess_return"),
                        average_market_strength=item.get(
                            "average_market_strength",
                            0.0,
                        ),
                        average_context_score=item.get(
                            "average_context_score",
                            0.0,
                        ),
                    )
                    for item in result.get("contexts", [])
                ],
                feature_regime_validations=[
                    FeatureRegimeValidation(
                        feature_type=FeatureType(item["feature"]),
                        regime=MarketRegime(item["regime"]),
                        total_count=item["total_count"],
                        success_count=item["success_count"],
                        average_return=item["average_return"],
                        average_gross_return=item.get(
                            "average_gross_return",
                            item["average_return"],
                        ),
                        average_benchmark_return=item.get(
                            "average_benchmark_return"
                        ),
                        average_excess_return=item.get("average_excess_return"),
                    )
                    for item in result.get("feature_regimes", [])
                ],
                score_band_validations=[
                    ScoreBandValidation(
                        minimum_score=item["minimum_score"],
                        maximum_score=item["maximum_score"],
                        total_count=item["total_count"],
                        success_count=item["success_count"],
                        average_return=item["average_return"],
                        average_gross_return=item.get(
                            "average_gross_return",
                            item["average_return"],
                        ),
                        average_benchmark_return=item.get(
                            "average_benchmark_return"
                        ),
                        average_excess_return=item.get("average_excess_return"),
                    )
                    for item in result.get("score_bands", [])
                ],
            ),
        )

    @staticmethod
    def _deserialize_feature(item) -> FeatureValidation:
        if isinstance(item, list):
            key, total, success, average = item
            return FeatureValidation(
                FeatureType(key),
                total,
                success,
                average,
                average,
            )
        return FeatureValidation(
            feature_type=FeatureType(item["feature"]),
            total_count=item["total_count"],
            success_count=item["success_count"],
            average_return=item["average_return"],
            average_gross_return=item.get(
                "average_gross_return",
                item["average_return"],
            ),
            average_benchmark_return=item.get("average_benchmark_return"),
            average_excess_return=item.get("average_excess_return"),
        )

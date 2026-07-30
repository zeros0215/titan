import json
import hashlib
from datetime import datetime
from pathlib import Path

from backtest.model.selection import Selection
from backtest.model.selection_snapshot import SelectionSnapshot
from config.constants import OUTPUT_DIR, VERSION
from config.settings import settings
from market.context.market_context import MarketContext


class SelectionRepository:
    """Stores immutable daily selection snapshots as JSON documents."""

    def __init__(
        self,
        directory: Path | None = None,
        cohort_type: str = "SELECTED",
        strategy_version: str = VERSION,
        provider_name: str | None = None,
    ) -> None:
        self.directory = directory or OUTPUT_DIR / "selections"
        self.cohort_type = cohort_type
        self.strategy_version = strategy_version
        self.provider_name = (
            provider_name or settings.market_provider
        ).upper()

    def save(
        self,
        selections: list[Selection],
        selected_at: datetime | None = None,
    ) -> Path | None:
        if selections:
            selection_date = selections[0].selected_date
            if selected_at is not None and selected_at != selection_date:
                raise ValueError("selected_at does not match the selections")
            selected_at = selection_date
        if selected_at is None:
            return None
        if any(item.selected_date != selected_at for item in selections):
            raise ValueError("all selections must have the same selected_date")

        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path_for(selected_at)
        snapshots = [self._to_snapshot(item) for item in selections]
        serialized = [self._serialize(snapshot) for snapshot in snapshots]
        execution_id = self._execution_id(selected_at, serialized)
        payload = {
            "version": 2,
            "execution_id": execution_id,
            "selected_at": selected_at.isoformat(),
            "data_as_of": selected_at.isoformat(),
            "provider": self.provider_name,
            "price_adjustment": (
                "ADJUSTED"
                if self.provider_name in {"KIS", "KRX_HISTORICAL"}
                else "SYNTHETIC"
            ),
            "strategy_version": self.strategy_version,
            "criteria_version": self.strategy_version,
            "universe_version": f"{selected_at:%Y-%m-%d}",
            "cohort_type": self.cohort_type,
            "selections": serialized,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load(self, selected_at: datetime) -> list[SelectionSnapshot]:
        path = self._path_for(selected_at)
        if not path.exists():
            return []

        payload = json.loads(path.read_text(encoding="utf-8"))
        return [
            SelectionSnapshot(
                selected_at=datetime.fromisoformat(item["selected_at"]),
                rank=item["rank"],
                code=item["code"],
                name=item["name"],
                total_score=item["total_score"],
                normalized_score=item["normalized_score"],
                trend_score=item["trend_score"],
                momentum_score=item["momentum_score"],
                volume_score=item["volume_score"],
                price_action_score=item["price_action_score"],
                risk_score=item["risk_score"],
                context_score=item["context_score"],
                enabled_features=item["enabled_features"],
                prediction_grade=item["prediction_grade"],
                decision=item["decision"],
                positive_factors=item["positive_factors"],
                negative_factors=item["negative_factors"],
                market=item.get("market"),
                market_context=item.get("market_context"),
            )
            for item in payload["selections"]
        ]

    def exists(self, selected_at: datetime) -> bool:
        return self._path_for(selected_at).exists()

    def list_dates(self) -> list[datetime]:
        """Return snapshot dates available in this cohort."""
        if not self.directory.exists():
            return []
        dates: list[datetime] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                dates.append(datetime.fromisoformat(payload["selected_at"]))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return dates

    def load_metadata(self, selected_at: datetime) -> dict:
        """Load reproducibility metadata without rebuilding domain snapshots."""
        path = self._path_for(selected_at)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            key: payload.get(key)
            for key in (
                "version",
                "execution_id",
                "selected_at",
                "data_as_of",
                "provider",
                "price_adjustment",
                "strategy_version",
                "criteria_version",
                "universe_version",
                "cohort_type",
            )
        }

    def _path_for(self, selected_at: datetime) -> Path:
        return self.directory / f"{selected_at:%Y%m%dT%H%M%S}.json"

    def _execution_id(self, selected_at: datetime, selections: list[dict]) -> str:
        canonical = json.dumps(
            {
                "selected_at": selected_at.isoformat(),
                "strategy_version": self.strategy_version,
                "selections": selections,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        return f"{selected_at:%Y%m%dT%H%M%S}_{digest}"

    @staticmethod
    def _to_snapshot(selection: Selection) -> SelectionSnapshot:
        analysis = selection.analysis
        score = analysis.score
        return SelectionSnapshot(
            selected_at=selection.selected_date,
            rank=selection.rank,
            code=selection.code,
            name=selection.name,
            total_score=score.total_score,
            normalized_score=score.normalized_score,
            trend_score=score.trend_score,
            momentum_score=score.momentum_score,
            volume_score=score.volume_score,
            price_action_score=score.price_action_score,
            risk_score=score.risk_score,
            context_score=score.context_score,
            enabled_features=[
                feature.type.value
                for feature in analysis.features.enabled()
            ],
            prediction_grade=(
                analysis.prediction.grade.value
                if analysis.prediction is not None
                else None
            ),
            decision=(
                analysis.decision.decision.value
                if analysis.decision is not None
                else None
            ),
            positive_factors=analysis.positive_factors,
            negative_factors=analysis.negative_factors,
            market=(
                analysis.market.value
                if analysis.market is not None
                else None
            ),
            market_context=SelectionRepository._serialize_context(analysis.context),
        )

    @staticmethod
    def _serialize(snapshot: SelectionSnapshot) -> dict:
        return {
            "selected_at": snapshot.selected_at.isoformat(),
            "rank": snapshot.rank,
            "code": snapshot.code,
            "name": snapshot.name,
            "total_score": snapshot.total_score,
            "normalized_score": snapshot.normalized_score,
            "trend_score": snapshot.trend_score,
            "momentum_score": snapshot.momentum_score,
            "volume_score": snapshot.volume_score,
            "price_action_score": snapshot.price_action_score,
            "risk_score": snapshot.risk_score,
            "context_score": snapshot.context_score,
            "enabled_features": snapshot.enabled_features,
            "prediction_grade": snapshot.prediction_grade,
            "decision": snapshot.decision,
            "positive_factors": snapshot.positive_factors,
            "negative_factors": snapshot.negative_factors,
            "market": snapshot.market,
            "market_context": snapshot.market_context,
        }

    @staticmethod
    def _serialize_context(
        context: MarketContext | None,
    ) -> dict[str, str | float | int] | None:
        if context is None:
            return None
        return {
            "kospi_trend": context.kospi_trend.value,
            "kosdaq_trend": context.kosdaq_trend.value,
            "market_strength": context.market_strength,
            "sector_strength": context.sector_strength,
            "theme_strength": context.theme_strength,
            "foreign_flow": context.foreign_flow,
            "institution_flow": context.institution_flow,
            "score": context.score,
        }

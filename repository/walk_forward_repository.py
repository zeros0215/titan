import json
import re
from pathlib import Path

from config.constants import OUTPUT_DIR
from walkforward.result import WalkForwardResult


class WalkForwardRepository:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or OUTPUT_DIR / "walk_forward"

    def save(self, result: WalkForwardResult) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        safe_version = re.sub(r"[^A-Za-z0-9._-]", "_", result.strategy_version)
        path = self.directory / f"walk_forward_result_{safe_version}.json"
        payload = self.to_payload(result)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def to_payload(result: WalkForwardResult) -> dict:
        return {
            "strategy_version": result.strategy_version,
            "strategy_config_hash": result.strategy_config_hash,
            "strategy_frozen": result.strategy_frozen,
            "holding_days": result.holding_days,
            "interval_months": result.interval_months,
            "folds": [
                {
                    "index": item.fold.index,
                    "training_start": item.fold.training_start.isoformat(),
                    "training_end": item.fold.training_end.isoformat(),
                    "test_start": item.fold.test_start.isoformat(),
                    "test_end": item.fold.test_end.isoformat(),
                    "attempted_dates": item.attempted_dates,
                    "completed_dates": item.completed_dates,
                    "total_count": item.total_count,
                    "success_count": item.success_count,
                    "win_rate": item.win_rate,
                    "average_net_return": item.weighted("average_net_return"),
                    "average_excess_return": item.weighted(
                        "average_excess_return"
                    ),
                    "universe_coverages": sorted(
                        set(item.universe_coverages)
                    ),
                    "errors": item.errors,
                }
                for item in result.folds
            ],
        }

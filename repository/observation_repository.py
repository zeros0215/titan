from pathlib import Path

from config.constants import OUTPUT_DIR, VERSION
from repository.selection_repository import SelectionRepository


class ObservationRepository(SelectionRepository):
    """Stores non-recommendation samples separately from selected candidates."""

    def __init__(
        self,
        directory: Path | None = None,
        strategy_version: str = VERSION,
        provider_name: str | None = None,
    ) -> None:
        super().__init__(
            directory=directory or OUTPUT_DIR / "observations",
            cohort_type="OBSERVATION",
            strategy_version=strategy_version,
            provider_name=provider_name,
        )

from pathlib import Path

from config.constants import OUTPUT_DIR


class ReportRepository:
    """Stores rendered reports; it does not calculate report values."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or OUTPUT_DIR / "reports"

    def save(self, name: str, markdown: str) -> Path:
        path = Path(name)
        if path.name != name or path.suffix != ".md":
            raise ValueError("report name must be a simple .md filename")

        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / path
        target.write_text(markdown, encoding="utf-8")
        return target

import csv
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from domain.enums import MarketType
from universe_history.validator import UniverseHistoryValidator


class UniverseHistoryCompiler:
    def __init__(self, validator=None) -> None:
        self.validator = validator or UniverseHistoryValidator()

    def compile(
        self,
        records,
        source_manifest: dict,
        coverage_start: date,
        coverage_end: date,
        output_dir: Path,
        input_sha256: str,
    ) -> tuple[dict, object]:
        validation = self.validator.validate(
            records,
            coverage_start,
            coverage_end,
        )
        if validation.errors:
            raise ValueError(
                f"universe history has {len(validation.errors)} validation errors"
            )
        source_complete = source_manifest.get("source_complete") is True
        declared_start = source_manifest.get("coverage_start")
        declared_end = source_manifest.get("coverage_end")
        provenance_fields = (
            "source_name",
            "source_type",
            "dataset_id",
            "evidence_url",
            "acquired_at",
        )
        provenance_complete = all(
            isinstance(source_manifest.get(key), str)
            and bool(source_manifest[key].strip())
            for key in provenance_fields
        )
        coverage_matches = (
            declared_start == coverage_start.isoformat()
            and declared_end == coverage_end.isoformat()
        )
        point_in_time_complete = (
            source_complete and coverage_matches and provenance_complete
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        self._write_market(
            output_dir / "kospi.csv",
            records,
            MarketType.KOSPI,
        )
        self._write_market(
            output_dir / "kosdaq.csv",
            records,
            MarketType.KOSDAQ,
        )
        compiled_files = {
            name: self.file_sha256(output_dir / name)
            for name in ("kospi.csv", "kosdaq.csv")
        }
        manifest = {
            "schema_version": 1,
            "point_in_time_complete": point_in_time_complete,
            "coverage_start": coverage_start.isoformat(),
            "coverage_end": coverage_end.isoformat(),
            "source_type": source_manifest.get("source_type", "unknown"),
            "source_name": source_manifest.get("source_name", "unknown"),
            "source_complete": source_complete,
            "dataset_id": source_manifest.get("dataset_id"),
            "evidence_url": source_manifest.get("evidence_url"),
            "acquired_at": source_manifest.get("acquired_at"),
            "provenance_complete": provenance_complete,
            "source_manifest_coverage_matches": coverage_matches,
            "input_sha256": input_sha256,
            "compiled_files": compiled_files,
            "compiled_at": datetime.now().isoformat(),
            "record_count": validation.record_count,
            "stock_count": validation.stock_count,
            "error_count": len(validation.errors),
            "warning_count": len(validation.warnings),
            "issues": [
                {
                    "severity": item.severity.value,
                    "code": item.code,
                    "message": item.message,
                    "stock_code": item.stock_code,
                }
                for item in validation.issues
            ],
        }
        (output_dir / "universe_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest, validation

    @staticmethod
    def file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_market(path, records, market):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow([
                "code",
                "name",
                "market",
                "effective_from",
                "effective_to",
                "source_id",
            ])
            for item in sorted(
                (record for record in records if record.market is market),
                key=lambda record: (record.code, record.effective_from),
            ):
                writer.writerow([
                    item.code,
                    item.name,
                    item.market.value,
                    item.effective_from.isoformat(),
                    item.effective_to.isoformat() if item.effective_to else "",
                    item.source_id,
                ])

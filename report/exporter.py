from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from config.constants import OUTPUT_DIR
from report.report_generator import ReportGenerator
from validation.aggregator import ValidationAggregator
from validation.validation_record import ValidationRecord


class ValidationExporter:
    """Exports validation history to CSV or Excel for downstream analysis."""

    def export(
        self,
        records: Iterable[ValidationRecord],
        destination: str | Path | None = None,
        fmt: str = "csv",
    ) -> Path:
        records = list(records)
        if not records:
            raise ValueError("No validation records to export")

        destination_path = self._resolve_destination(destination, fmt)
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        summary_rows = [
            self._build_summary_row(record)
            for record in records
        ]
        summary_df = pd.DataFrame(summary_rows)

        if fmt.lower() == "csv":
            summary_df.to_csv(destination_path, index=False)
            return destination_path

        if fmt.lower() == "excel":
            with pd.ExcelWriter(destination_path) as writer:
                summary_df.to_excel(writer, sheet_name="summary", index=False)
                self._feature_frame(records).to_excel(writer, sheet_name="features", index=False)
                self._feature_regime_frame(records).to_excel(
                    writer,
                    sheet_name="feature_regimes",
                    index=False,
                )
                self._prediction_frame(records).to_excel(writer, sheet_name="predictions", index=False)
                self._decision_frame(records).to_excel(writer, sheet_name="decisions", index=False)
                self._context_frame(records).to_excel(writer, sheet_name="contexts", index=False)
                self._score_band_frame(records).to_excel(
                    writer,
                    sheet_name="score_bands",
                    index=False,
                )
            return destination_path

        raise ValueError(f"Unsupported export format: {fmt}")

    def export_package(
        self,
        records: Iterable[ValidationRecord],
        destination: str | Path | None = None,
        fmt: str = "csv",
    ) -> Path:
        records = list(records)
        if not records:
            raise ValueError("No validation records to export")

        destination_path = Path(destination) if destination is not None else OUTPUT_DIR / "exports" / "validation_package"
        destination_path.mkdir(parents=True, exist_ok=True)

        summary_name = "validation_summary.csv" if fmt.lower() == "csv" else "validation_summary.xlsx"
        self.export(records, destination_path / summary_name, fmt=fmt)
        if fmt.lower() == "csv":
            self._feature_frame(records).to_csv(
                destination_path / "feature_performance.csv",
                index=False,
            )
            self._context_frame(records).to_csv(
                destination_path / "context_performance.csv",
                index=False,
            )
            self._feature_regime_frame(records).to_csv(
                destination_path / "feature_regime_performance.csv",
                index=False,
            )
            self._score_band_frame(records).to_csv(
                destination_path / "score_band_performance.csv",
                index=False,
            )

        report_path = destination_path / "validation_report.md"
        report_markdown = ReportGenerator().generate_cumulative_markdown(
            ValidationAggregator().aggregate(records)
        )
        report_path.write_text(report_markdown, encoding="utf-8")

        preview_path = destination_path / "preview.html"
        preview_path.write_text(
            self._render_html_preview(report_markdown),
            encoding="utf-8",
        )

        return destination_path

    @staticmethod
    def _render_html_preview(markdown: str) -> str:
        escaped = markdown.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body = escaped.replace("\n", "<br>\n")
        return """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>TITAN Validation Report Preview</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; line-height: 1.5; }}
    h1, h2, h3 {{ color: #1f4e79; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 20px; }}
    th, td {{ border: 1px solid #c8d4e3; padding: 8px; text-align: left; }}
    th {{ background: #f2f6fb; }}
    code {{ background: #f5f5f5; padding: 2px 4px; }}
  </style>
</head>
<body>
{body}
</body>
</html>
""".format(body=body)

    @staticmethod
    def _resolve_destination(destination: str | Path | None, fmt: str) -> Path:
        if destination is None:
            directory = OUTPUT_DIR / "exports"
            suffix = ".csv" if fmt.lower() == "csv" else ".xlsx"
            return directory / f"validation_export{suffix}"
        path = Path(destination)
        if path.suffix == "":
            path = path.with_suffix(".csv" if fmt.lower() == "csv" else ".xlsx")
        return path

    @staticmethod
    def _build_summary_row(record: ValidationRecord) -> dict[str, object]:
        result = record.result
        return {
            "selected_at": record.selected_at.isoformat(),
            "evaluation_date": record.evaluation_date.isoformat(),
            "holding_days": record.holding_days,
            "success_return": record.success_return,
            "total_count": result.total_count,
            "success_count": result.success_count,
            "fail_count": result.fail_count,
            "win_rate": result.win_rate,
            "average_return": result.average_return,
            "average_gross_return": result.average_gross_return,
            "average_net_return": result.average_net_return,
            "average_benchmark_return": result.average_benchmark_return,
            "average_excess_return": result.average_excess_return,
        }

    @staticmethod
    def _feature_frame(records: list[ValidationRecord]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for record in records:
            for item in record.result.feature_validations:
                rows.append({
                    "selected_at": record.selected_at.isoformat(),
                    "evaluation_date": record.evaluation_date.isoformat(),
                    "feature": item.feature_type.value,
                    "total_count": item.total_count,
                    "success_count": item.success_count,
                    "average_return": item.average_return,
                    "average_gross_return": item.effective_gross_return,
                    "average_benchmark_return": item.average_benchmark_return,
                    "average_excess_return": item.average_excess_return,
                })
        return pd.DataFrame(rows)

    @staticmethod
    def _prediction_frame(records: list[ValidationRecord]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for record in records:
            for item in record.result.prediction_validations:
                rows.append({
                    "selected_at": record.selected_at.isoformat(),
                    "evaluation_date": record.evaluation_date.isoformat(),
                    "prediction": item.grade.value,
                    "total_count": item.total_count,
                    "success_count": item.success_count,
                    "average_return": item.average_return,
                })
        return pd.DataFrame(rows)

    @staticmethod
    def _decision_frame(records: list[ValidationRecord]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for record in records:
            for item in record.result.decision_validations:
                rows.append({
                    "selected_at": record.selected_at.isoformat(),
                    "evaluation_date": record.evaluation_date.isoformat(),
                    "decision": item.decision.value,
                    "total_count": item.total_count,
                    "success_count": item.success_count,
                    "average_return": item.average_return,
                })
        return pd.DataFrame(rows)

    @staticmethod
    def _feature_regime_frame(records: list[ValidationRecord]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for record in records:
            for item in record.result.feature_regime_validations:
                rows.append({
                    "selected_at": record.selected_at.isoformat(),
                    "evaluation_date": record.evaluation_date.isoformat(),
                    "holding_days": record.holding_days,
                    "feature": item.feature_type.value,
                    "regime": item.regime.value,
                    "total_count": item.total_count,
                    "success_count": item.success_count,
                    "win_rate": item.win_rate,
                    "average_gross_return": item.average_gross_return,
                    "average_net_return": item.average_return,
                    "average_benchmark_return": item.average_benchmark_return,
                    "average_excess_return": item.average_excess_return,
                })
        return pd.DataFrame(rows)

    @staticmethod
    def _context_frame(records: list[ValidationRecord]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for record in records:
            for item in record.result.context_validations:
                rows.append({
                    "selected_at": record.selected_at.isoformat(),
                    "evaluation_date": record.evaluation_date.isoformat(),
                    "holding_days": record.holding_days,
                    "regime": item.regime.value,
                    "total_count": item.total_count,
                    "success_count": item.success_count,
                    "win_rate": item.win_rate,
                    "average_market_strength": item.average_market_strength,
                    "average_context_score": item.average_context_score,
                    "average_gross_return": item.average_gross_return,
                    "average_net_return": item.average_return,
                    "average_benchmark_return": item.average_benchmark_return,
                    "average_excess_return": item.average_excess_return,
                })
        return pd.DataFrame(rows)

    @staticmethod
    def _score_band_frame(records: list[ValidationRecord]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for record in records:
            for item in record.result.score_band_validations:
                rows.append({
                    "selected_at": record.selected_at.isoformat(),
                    "evaluation_date": record.evaluation_date.isoformat(),
                    "holding_days": record.holding_days,
                    "minimum_score": item.minimum_score,
                    "maximum_score": item.maximum_score,
                    "score_band": item.label,
                    "total_count": item.total_count,
                    "success_count": item.success_count,
                    "win_rate": item.win_rate,
                    "average_gross_return": item.average_gross_return,
                    "average_net_return": item.average_return,
                    "average_benchmark_return": item.average_benchmark_return,
                    "average_excess_return": item.average_excess_return,
                })
        return pd.DataFrame(rows)

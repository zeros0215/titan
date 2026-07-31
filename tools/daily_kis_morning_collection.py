"""Daily 10:02 KST job: collect prior selections' morning bars."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from analysis.morning_entry import build_daily_collection_manifest
from tools.collect_kis_morning_bars import collect_manifest


ROOT = Path(__file__).resolve().parent.parent


def run_daily(
    entry_date: date,
    runs_dir: Path,
    output_dir: Path,
    strategy_version: str,
) -> dict:
    manifest_path = output_dir / "manifests" / f"{entry_date}.json"
    manifest = build_daily_collection_manifest(
        runs_dir, manifest_path, strategy_version, entry_date
    )
    if manifest["target_count"] == 0:
        return {
            "target_count": 0,
            "saved_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "failures": [],
        }
    return collect_manifest(
        manifest_path, output_dir / "bars", target_date=entry_date
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=ROOT / "output" / "kis_manual_tests" / "runs",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "output" / "morning_entry",
    )
    parser.add_argument(
        "--strategy-version",
        default="V1.3-S80-N7-TP5-SL10-CANDIDATE",
    )
    args = parser.parse_args()
    report = run_daily(
        args.date, args.runs_dir, args.output_dir, args.strategy_version
    )
    print(
        f"targets={report['target_count']} saved={report['saved_count']} "
        f"skipped={report['skipped_count']} failed={report['failed_count']}"
    )
    raise SystemExit(0 if report["failed_count"] == 0 else 2)


if __name__ == "__main__":
    main()

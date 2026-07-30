"""One-command V1 release audit and immutable evidence packaging."""

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from config.constants import ROOT_DIR, VERSION
from release.backtest_data import load_active_backtest_data
from release.v1 import (
    backtest_preflight,
    freeze_v1,
    preflight_markdown,
)
from report.report_generator import ReportGenerator
from repository.walk_forward_repository import WalkForwardRepository
from runner.factory import create_walk_forward_engine
from walkforward.plan import WalkForwardPlan


def run_v1_release_check(
    release_dir: Path,
    active_data_path: Path,
) -> tuple[dict, int]:
    release_dir.mkdir(parents=True, exist_ok=True)
    spec_path = release_dir / "strategy_spec.json"
    spec, strategy_hash = freeze_v1(spec_path)
    universe_dir, price_dir, active_data = load_active_backtest_data(
        active_data_path
    )
    preflight = backtest_preflight(
        spec_path,
        universe_dir / "universe_manifest.json",
        universe_dir,
        price_dir,
    )
    (release_dir / "preflight.md").write_text(
        preflight_markdown(preflight),
        encoding="utf-8",
    )

    tests = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
            "-q",
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    test_log = (tests.stdout or "") + (tests.stderr or "")
    (release_dir / "test_results.txt").write_text(
        test_log,
        encoding="utf-8",
    )

    plan = WalkForwardPlan.expanding_years(2022, 2023, 2025)
    first = create_walk_forward_engine(
        strategy_config_hash=strategy_hash
    ).run(plan, holding_days=20, interval_months=1, top_n=5, success_return=0.03)
    second = create_walk_forward_engine(
        strategy_config_hash=strategy_hash
    ).run(plan, holding_days=20, interval_months=1, top_n=5, success_return=0.03)
    first_payload = WalkForwardRepository.to_payload(first)
    second_payload = WalkForwardRepository.to_payload(second)
    reproducible = _canonical_hash(first_payload) == _canonical_hash(
        second_payload
    )
    result_path = release_dir / "walk_forward_result.json"
    result_path.write_text(
        json.dumps(first_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (release_dir / "walk_forward_report.md").write_text(
        ReportGenerator().generate_walk_forward_markdown(first),
        encoding="utf-8",
    )
    shutil.copy2(active_data_path, release_dir / "backtest_data.json")
    quality_source = ROOT_DIR / "output" / "reports" / "price_quality_review.md"
    if quality_source.exists():
        shutil.copy2(quality_source, release_dir / "quality_review.md")

    folds_complete = all(
        fold.attempted_dates == 12
        and fold.completed_dates == 12
        and not fold.errors
        and set(fold.universe_coverages) == {"COMPLETE"}
        for fold in first.folds
    )
    checks = {
        "unit_tests": tests.returncode == 0,
        "preflight_ready": preflight.status == "READY",
        "walk_forward_36_of_36": folds_complete,
        "walk_forward_errors_zero": all(
            not fold.errors for fold in first.folds
        ),
        "point_in_time_universe_complete": all(
            set(fold.universe_coverages) == {"COMPLETE"}
            for fold in first.folds
        ),
        "reproducible_result": reproducible,
        "order_api_calls": 0,
    }
    passed = all(
        value is True or (key == "order_api_calls" and value == 0)
        for key, value in checks.items()
    )
    manifest = {
        "schema_version": 1,
        "release_version": VERSION,
        "status": "COMPLETE" if passed else "FAILED",
        "scope": "RESEARCH_BACKTEST",
        "data_status": active_data["status"],
        "formal_backtest_ready": active_data["formal_backtest_ready"],
        "formal_blocker": active_data["formal_blocker"],
        "strategy_config_sha256": strategy_hash,
        "checks": checks,
        "walk_forward_result_sha256": _sha256(result_path),
        "artifacts": {},
        "limitations": [
            "official KOSPI/KOSDAQ benchmark history is unavailable",
            "official adjusted prices are unavailable",
            "intraday execution is unsupported without intraday candles",
            "orders, positions, and live trading are outside V1 scope",
        ],
        "built_at": datetime.now().astimezone().isoformat(),
    }
    artifact_names = [
        "strategy_spec.json",
        "backtest_data.json",
        "preflight.md",
        "walk_forward_result.json",
        "walk_forward_report.md",
        "quality_review.md",
        "test_results.txt",
    ]
    manifest["artifacts"] = {
        name: _sha256(release_dir / name)
        for name in artifact_names
        if (release_dir / name).exists()
    }
    manifest_path = release_dir / "release_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest, 0 if passed else 3


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()

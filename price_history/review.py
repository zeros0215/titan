"""Audit conservative dispositions for unresolved KRX price discontinuities."""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path


def review_price_quality(price_dir: Path, report_path: Path) -> dict:
    manifest = _load(price_dir / "price_history_manifest.json")
    quarantines = _load(price_dir / "quality_quarantines.json")
    rejected = _load(price_dir / "rejected_price_rows.json")
    by_code: dict[str, list[dict]] = {}
    for item in quarantines:
        by_code.setdefault(item["code"], []).append(item)

    event_count = covered_count = 0
    classifications = Counter()
    uncovered = []
    stock_files = [
        path
        for path in price_dir.glob("*.json")
        if len(path.stem) == 6 and path.stem.isalnum()
    ]
    for path in stock_files:
        payload = _load(path)
        for event in payload.get("unresolved_large_jumps", []):
            event_count += 1
            classifications[event["classification"]] += 1
            event_date = datetime.fromisoformat(event["date"])
            covered = any(
                datetime.fromisoformat(item["start"])
                <= event_date
                <= datetime.fromisoformat(item["end"])
                for item in by_code.get(payload["code"], [])
            )
            if covered:
                covered_count += 1
            else:
                uncovered.append({
                    "code": payload["code"],
                    "date": event["date"],
                    "classification": event["classification"],
                })

    expected = manifest["unresolved_large_jump_count"]
    passed = (
        event_count == expected
        and covered_count == expected
        and not uncovered
        and len(quarantines) == manifest["quality_quarantine_count"]
        and len(rejected) == manifest["rejected_row_count"]
    )
    result = {
        "status": "PASS" if passed else "FAIL",
        "disposition": (
            "EXCLUDED_FROM_SELECTION_DURING_QUARANTINE; "
            "NO_UNVERIFIED_PRICE_CORRECTION"
        ),
        "unresolved_event_count": event_count,
        "covered_event_count": covered_count,
        "uncovered_events": uncovered,
        "quarantine_interval_count": len(quarantines),
        "rejected_row_count": len(rejected),
        "classifications": dict(sorted(classifications.items())),
        "formal_backtest_ready": manifest["formal_backtest_ready"],
        "formal_blocker": manifest["formal_blocker"],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_markdown(result), encoding="utf-8")
    (report_path.with_suffix(".json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def _markdown(result: dict) -> str:
    lines = [
        "# KRX Price Quality Review",
        "",
        f"- Status: **{result['status']}**",
        f"- Disposition: `{result['disposition']}`",
        (
            "- Unresolved events covered by quarantine: "
            f"{result['covered_event_count']}/"
            f"{result['unresolved_event_count']}"
        ),
        (
            "- Quarantine intervals: "
            f"{result['quarantine_interval_count']}"
        ),
        f"- Rejected invalid rows: {result['rejected_row_count']}",
        f"- Formal backtest ready: {result['formal_backtest_ready']}",
        f"- Formal blocker: {result['formal_blocker']}",
        "",
        "## Classification counts",
        "",
    ]
    lines.extend(
        f"- {name}: {count}"
        for name, count in result["classifications"].items()
    )
    lines.extend([
        "",
        "Unresolved discontinuities are not silently corrected. A stock is "
        "ineligible on every affected selection date covered by its quarantine.",
        "",
    ])
    return "\n".join(lines)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

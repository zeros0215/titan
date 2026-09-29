"""Audit conservative dispositions for unresolved KRX price discontinuities."""

import json
import csv
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

    event_count = covered_count = action_count = 0
    classifications = Counter()
    uncovered = []
    review_queue = []
    invalid_adjustments = []
    non_official_files = 0
    stock_files = [
        path
        for path in price_dir.glob("*.json")
        if len(path.stem) == 6 and path.stem.isalnum()
    ]
    for path in stock_files:
        payload = _load(path)
        code = payload["code"]
        name = payload.get("name", "")
        if payload.get("official_adjusted_prices") is not True:
            non_official_files += 1
        for action in payload.get("adjustment_events", []):
            action_count += 1
            share_ratio = float(action["share_ratio"])
            factor = float(action["backward_price_factor"])
            continuity = float(action["continuity"])
            valid = (
                share_ratio > 0
                and abs(factor - (1.0 / share_ratio)) < 1e-9
                and 0.75 <= continuity <= 1.25
            )
            if not valid:
                invalid_adjustments.append({"code": code, **action})
            review_queue.append({
                "event_type": "INFERRED_ADJUSTMENT",
                "code": code,
                "name": name,
                "date": action["date"],
                "classification": "SHARE_COUNT_CONTINUITY_HEURISTIC",
                "share_ratio": share_ratio,
                "price_ratio": "",
                "continuity": continuity,
                "quarantine_start": "",
                "quarantine_end": "",
                "review_status": "PENDING_OFFICIAL_EVIDENCE",
            })
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
            matching = [
                item for item in by_code.get(code, [])
                if datetime.fromisoformat(item["start"])
                <= event_date
                <= datetime.fromisoformat(item["end"])
            ]
            review_queue.append({
                "event_type": "UNRESOLVED_DISCONTINUITY",
                "code": code,
                "name": name,
                "date": event["date"],
                "classification": event["classification"],
                "share_ratio": event["share_ratio"],
                "price_ratio": event["price_ratio"],
                "continuity": event["continuity"],
                "quarantine_start": matching[0]["start"] if matching else "",
                "quarantine_end": matching[0]["end"] if matching else "",
                "review_status": "PENDING_OFFICIAL_EVIDENCE",
            })

    expected = manifest["unresolved_large_jump_count"]
    passed = (
        event_count == expected
        and covered_count == expected
        and not uncovered
        and len(quarantines) == manifest["quality_quarantine_count"]
        and len(rejected) == manifest["rejected_row_count"]
        and action_count == manifest["adjustment_event_count"]
        and not invalid_adjustments
        and len(stock_files) == manifest["stock_count"]
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
        "stock_file_count": len(stock_files),
        "inferred_adjustment_count": action_count,
        "invalid_adjustments": invalid_adjustments,
        "non_official_adjusted_file_count": non_official_files,
        "official_evidence_pending_count": len(review_queue),
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
    _write_review_queue(
        report_path.with_name(f"{report_path.stem}_queue.csv"),
        review_queue,
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
        f"- Stock files checked: {result['stock_file_count']}",
        (
            "- Inferred adjustment events: "
            f"{result['inferred_adjustment_count']}"
        ),
        (
            "- Invalid inferred adjustment records: "
            f"{len(result['invalid_adjustments'])}"
        ),
        (
            "- Files without official adjusted-price evidence: "
            f"{result['non_official_adjusted_file_count']}"
        ),
        (
            "- Events pending official evidence review: "
            f"{result['official_evidence_pending_count']}"
        ),
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
        "`PASS` means that compiled records, manifest counts, adjustment "
        "arithmetic, and quarantine coverage are internally consistent. It "
        "does not approve inferred corporate actions or make the data formally "
        "backtest-ready.",
        "",
        "Unresolved discontinuities are not silently corrected. A stock is "
        "ineligible on every affected selection date covered by its quarantine.",
        "",
    ])
    return "\n".join(lines)


def _write_review_queue(path: Path, rows: list[dict]) -> None:
    fields = [
        "event_type", "code", "name", "date", "classification",
        "share_ratio", "price_ratio", "continuity", "quarantine_start",
        "quarantine_end", "review_status",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

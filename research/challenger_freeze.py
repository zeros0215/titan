"""Immutable research specification for the selected challenger program."""

import hashlib
import json
from pathlib import Path


def save_challenger_freeze(candidates: list[dict], output: Path) -> Path:
    selected = {
        row["research_id"]: {
            "config": row["config"],
            "holding_days": int(row.get("holding_days", 40)),
            "interval_days": 7,
            "top_n": 3,
        }
        for row in candidates
        if row["research_id"] in {
            "challenger-a-breakout-h40",
            "challenger-c-pullback-h40",
        }
    }
    if len(selected) != 2:
        raise ValueError("both frozen A and C challenger definitions are required")
    specification = {
        "schema_version": 1,
        "program_version": "research-ac43-portfolio-v1",
        "strategies": selected,
        "portfolio": {
            "maximum_positions": 7,
            "slot_limits": {
                "challenger-a-breakout-h40": 4,
                "challenger-c-pullback-h40": 3,
            },
            "duplicate_code_policy": "single_position",
            "allocation_policy": "equal_weight_fixed_slots",
        },
        "status": "RESEARCH_ONLY",
    }
    canonical = json.dumps(
        specification, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    payload = {
        **specification,
        "specification_sha256": hashlib.sha256(canonical).hexdigest(),
    }
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != payload:
            raise ValueError(
                "frozen challenger specification differs from existing version"
            )
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output

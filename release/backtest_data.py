"""Promotion and loading of immutable backtest data sets."""

import hashlib
import json
from datetime import datetime
from pathlib import Path


def promote_backtest_data(
    universe_dir: Path,
    price_dir: Path,
    output_path: Path,
) -> dict:
    universe = _json(universe_dir / "universe_manifest.json")
    prices = _json(price_dir / "price_history_manifest.json")
    if universe.get("point_in_time_complete") is not True:
        raise ValueError("point-in-time universe is not complete")
    if universe.get("stock_count", 0) < 100:
        raise ValueError("universe contains fewer than 100 stocks")
    for name, expected in universe.get("compiled_files", {}).items():
        if _sha256(universe_dir / name) != expected:
            raise ValueError(f"universe file hash mismatch: {name}")
    if prices.get("price_history_complete") is not True:
        raise ValueError("price history is not complete")
    if prices.get("adjusted_prices") is not True:
        raise ValueError("price history is not adjusted")
    if prices.get("provisional_backtest_ready") is not True:
        raise ValueError("price history is not provisionally ready")
    quarantine_path = price_dir / "quality_quarantines.json"
    quarantines = _json(quarantine_path)
    if len(quarantines) != prices.get("quality_quarantine_count"):
        raise ValueError("quality quarantine count does not match manifest")
    market_cap_path = price_dir / "market_cap_top500.json"
    market_cap = _json(market_cap_path)
    if (
        market_cap.get("limit") != 500
        or market_cap.get("minimum_trading_value") != 5_000_000_000
        or not market_cap.get("sessions")
    ):
        raise ValueError("point-in-time Top 500 eligibility data is not complete")
    payload = {
        "schema_version": 1,
        "status": "PROVISIONAL",
        "universe_dir": str(universe_dir.resolve()),
        "price_dir": str(price_dir.resolve()),
        "universe_manifest_sha256": _sha256(
            universe_dir / "universe_manifest.json"
        ),
        "price_manifest_sha256": _sha256(
            price_dir / "price_history_manifest.json"
        ),
        "quality_quarantine_sha256": _sha256(quarantine_path),
        "market_cap_top500_sha256": _sha256(market_cap_path),
        "universe_policy": (
            "point-in-time market-cap Top 500; daily trading value >= KRW 5bn; "
            "managed issues, SPACs, and preferred shares excluded"
        ),
        "quality_policy": "exclude quarantined stock/date intervals",
        "formal_backtest_ready": prices.get("formal_backtest_ready") is True,
        "formal_blocker": prices.get("formal_blocker"),
        "promoted_at": datetime.now().astimezone().isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def load_active_backtest_data(path: Path) -> tuple[Path, Path, dict]:
    payload = _json(path)
    universe_dir = Path(payload["universe_dir"])
    price_dir = Path(payload["price_dir"])
    checks = (
        (
            universe_dir / "universe_manifest.json",
            payload["universe_manifest_sha256"],
        ),
        (
            price_dir / "price_history_manifest.json",
            payload["price_manifest_sha256"],
        ),
        (
            price_dir / "quality_quarantines.json",
            payload["quality_quarantine_sha256"],
        ),
        (
            price_dir / "market_cap_top500.json",
            payload["market_cap_top500_sha256"],
        ),
    )
    for target, expected in checks:
        if _sha256(target) != expected:
            raise ValueError(f"promoted data changed after review: {target}")
    return universe_dir, price_dir, payload


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()

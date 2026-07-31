"""Collect selected stocks' 09:00-10:00 bars through the read-only KIS API."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path
from time import sleep

from broker.kis.client import KisReadOnlyClient
from broker.kis.intraday import KisIntradayProvider
from broker.kis.session import KisSession


def collect_manifest(
    manifest_path: Path,
    output_dir: Path,
    target_date: date | None = None,
    collect_all: bool = False,
    provider=None,
    request_interval: float = 0.1,
) -> dict:
    if target_date is not None and collect_all:
        raise ValueError("target_date and collect_all cannot be used together")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if provider is None:
        client = KisReadOnlyClient()
        client.minimum_interval_seconds = request_interval
        provider = KisIntradayProvider(KisSession(client))
    effective_date = target_date or date.today()
    targets = [
        row for row in manifest["targets"]
        if collect_all or row["entry_date"] == effective_date.isoformat()
    ]
    saved = skipped = failed = 0
    failures = []
    for target in targets:
        path = (
            output_dir / target["entry_date"]
            / f"{target['code']}.csv"
        )
        if path.exists():
            skipped += 1
            continue
        try:
            minutes = provider.get_minutes(
                target["code"],
                date.fromisoformat(target["entry_date"]),
                "100000",
            )
            bars = _five_minute_bars(minutes, target["code"])
            if len(bars) != 12:
                raise ValueError(
                    f"expected 12 morning bars, received {len(bars)}"
                )
            _write_bars(path, bars)
            saved += 1
        except Exception as error:
            failed += 1
            failures.append({
                "entry_date": target["entry_date"],
                "code": target["code"],
                "error": str(error),
            })
        if request_interval > 0:
            sleep(request_interval)
    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "target_count": len(targets),
        "saved_count": saved,
        "skipped_count": skipped,
        "failed_count": failed,
        "failures": failures,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "last_collection.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def _five_minute_bars(minutes: list[dict], code: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in minutes:
        hour = int(row["time"][:2])
        minute = int(row["time"][2:4])
        if hour != 9:
            continue
        bucket = minute // 5 * 5
        key = f"{row['date']}T09:{bucket:02d}:00"
        groups.setdefault(key, []).append(row)
    result = []
    for timestamp, rows in sorted(groups.items()):
        rows.sort(key=lambda row: row["time"])
        volume = sum(row["volume"] for row in rows)
        result.append({
            "timestamp": timestamp,
            "code": code,
            "open": rows[0]["open"],
            "high": max(row["high"] for row in rows),
            "low": min(row["low"] for row in rows),
            "close": rows[-1]["close"],
            "volume": volume,
            "trading_value": sum(row["close"] * row["volume"] for row in rows),
        })
    return result


def _write_bars(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "timestamp", "code", "open", "high", "low", "close",
            "volume", "trading_value",
        ])
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--request-interval", type=float, default=0.1)
    args = parser.parse_args()
    if args.request_interval < 0:
        parser.error("--request-interval must not be negative")
    report = collect_manifest(
        args.manifest,
        args.output_dir,
        target_date=args.date,
        collect_all=args.all,
        request_interval=args.request_interval,
    )
    print(
        f"targets={report['target_count']} saved={report['saved_count']} "
        f"skipped={report['skipped_count']} failed={report['failed_count']}"
    )
    raise SystemExit(0 if report["failed_count"] == 0 else 2)


if __name__ == "__main__":
    main()

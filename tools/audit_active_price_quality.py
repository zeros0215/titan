"""Audit the active price data without changing or promoting it."""

import argparse
import json
from pathlib import Path

from price_history.review import review_price_quality
from release.backtest_data import load_active_backtest_data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="audit active inferred adjustments and quarantines"
    )
    parser.add_argument(
        "--active-data",
        type=Path,
        default=Path("output/release/backtest_data.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("output/reports/price_quality_review.md"),
    )
    args = parser.parse_args()

    _, price_dir, active = load_active_backtest_data(args.active_data)
    result = review_price_quality(price_dir, args.report)
    print(f"Active data: {active['status']}")
    print(f"Internal consistency: {result['status']}")
    print(
        "Official evidence pending: "
        f"{result['official_evidence_pending_count']}"
    )
    print(f"Formal backtest ready: {result['formal_backtest_ready']}")
    print(f"Report: {args.report}")
    print(f"Queue: {args.report.with_name(args.report.stem + '_queue.csv')}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

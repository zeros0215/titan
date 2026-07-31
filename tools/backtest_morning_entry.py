"""Run the 10:00 stable-entry comparison from collected KIS bars."""

from __future__ import annotations

import argparse
from pathlib import Path

from analysis.morning_entry import run_morning_entry_backtest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--bars-dir", required=True, type=Path)
    parser.add_argument("--active-data", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = run_morning_entry_backtest(
        args.manifest, args.bars_dir, args.active_data, args.output_dir
    )
    print(
        f"available={result['available_count']} "
        f"qualified={result['qualified_count']} "
        f"missing={result['missing_count']}"
    )
    for name, summary in result["summaries"].items():
        print(
            f"{name}: trades={summary['trades']} "
            f"win_rate={summary['win_rate']} "
            f"average_return={summary['average_return']}"
        )


if __name__ == "__main__":
    main()

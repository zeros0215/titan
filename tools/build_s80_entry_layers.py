"""Build the S80 daily-core and 10:00-overlay comparison report."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.s80_morning_ablation import save_s80_entry_layer_comparison


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = save_s80_entry_layer_comparison(args.backtest, args.output_dir)
    for name, row in result["summaries"].items():
        print(
            f"{name}: trades={row['trades']} win_rate={row['win_rate']} "
            f"average_return={row['average_return']}"
        )


if __name__ == "__main__":
    main()

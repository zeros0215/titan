import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.strategy_comparison import run_strategy_comparison


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    result = run_strategy_comparison(args.year)
    print(f"Completed: {result['year']} / {len(result['strategies'])} strategies")


if __name__ == "__main__":
    main()

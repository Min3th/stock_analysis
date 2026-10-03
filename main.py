"""Command-line entry point."""

import argparse
from pathlib import Path

from cse_screening.periods import period_label
from cse_screening.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="CSE Capital Goods screening pipeline")
    parser.add_argument(
        "--sector", default="Capital Goods", help="Configured sector (currently Capital Goods only)"
    )
    parser.add_argument("--period", required=True, help="Output label such as 2026Q3")
    parser.add_argument("--company", help="Run one configured CSE ticker")
    args = parser.parse_args()
    if args.sector.casefold() != "capital goods":
        parser.error("This pilot currently supports only the Capital Goods sector")
    period_label(args.period)
    outputs = run(args.period.upper(), args.company, Path(__file__).parent)
    for kind, path in outputs.items():
        print(f"{kind}: {path}")


if __name__ == "__main__":
    main()

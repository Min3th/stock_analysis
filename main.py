"""Command-line entry point."""

import argparse
from pathlib import Path

from cse_screening.periods import period_label
from cse_screening.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="CSE GICS industry-group screening pipeline")
    parser.add_argument(
        "--sector", default="Capital Goods", help="CSE GICS industry group, for example Banks"
    )
    parser.add_argument("--period", required=True, help="Output label such as 2026Q3")
    parser.add_argument("--company", help="Run one configured CSE ticker")
    parser.add_argument(
        "--corrections",
        type=Path,
        help="Correction overlay (default: config/corrections.yml)",
    )
    args = parser.parse_args()
    period_label(args.period)
    try:
        outputs = run(
            args.period.upper(),
            args.sector,
            args.company,
            Path(__file__).parent,
            args.corrections,
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    for kind, path in outputs.items():
        print(f"{kind}: {path}")


if __name__ == "__main__":
    main()

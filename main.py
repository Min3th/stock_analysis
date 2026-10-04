"""Command-line entry point."""

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from cse_screening.periods import current_period, period_label
from cse_screening.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="CSE GICS industry-group screening pipeline")
    parser.add_argument(
        "--sector", default="Capital Goods", help="CSE GICS industry group, for example Banks"
    )
    parser.add_argument(
        "--period",
        help="Output label such as 2026Q3 (default: the current calendar quarter)",
    )
    parser.add_argument("--company", help="Run one CSE ticker, for example HHL.N0000")
    parser.add_argument(
        "--corrections",
        type=Path,
        help="Correction overlay (default: config/corrections.yml)",
    )
    args = parser.parse_args()
    period = args.period or current_period(datetime.now(ZoneInfo("Asia/Colombo")).date())
    try:
        period_label(period)
    except ValueError:
        parser.error(f"--period must look like 2026Q3 or 2026, not {period!r}")
    try:
        outputs = run(
            period.upper(),
            args.sector,
            args.company,
            Path(__file__).parent,
            args.corrections,
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    except httpx.HTTPError as exc:
        parser.exit(1, f"Could not reach the Colombo Stock Exchange website: {exc}\n")
    for kind, path in outputs.items():
        print(f"{kind}: {path}")


if __name__ == "__main__":
    main()

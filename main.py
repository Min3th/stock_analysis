"""Command-line entry point.

Without a subcommand this behaves as it always has (``python main.py --sector
Banks``). ``run``, ``extract`` and ``corrections add`` are explicit forms.
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from cse_screening.corrections import append_correction
from cse_screening.periods import current_period, period_label
from cse_screening.pipeline import load_pipeline_config, run
from cse_screening.preview import extract_preview

ROOT = Path(__file__).parent
SUBCOMMANDS = {"run", "extract", "corrections"}


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use only cached CSE data and documents; a cache miss becomes a warning",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="Also write JSON tables and manifest.json to this directory",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CSE GICS industry-group screening pipeline")
    commands = parser.add_subparsers(dest="command")
    _add_run_arguments(commands.add_parser("run", help="Screen an industry group (the default)"))

    extract = commands.add_parser("extract", help="Preview what the extractors read from a PDF")
    extract.add_argument("--pdf", type=Path, required=True)
    extract.add_argument("--kind", choices=["annual_report", "interim_statement"], required=True)
    extract.add_argument("--period-end", required=True, help="YYYY-MM-DD")
    extract.add_argument("--period-months", type=int)

    corrections = commands.add_parser("corrections", help="Manage manual corrections")
    actions = corrections.add_subparsers(dest="action", required=True)
    add = actions.add_parser("add", help="Append a correction (nothing is deleted)")
    add.add_argument("--ticker", required=True)
    add.add_argument("--metric", required=True)
    add.add_argument("--value", required=True)
    add.add_argument("--unit", default="LKR")
    add.add_argument("--period-end", required=True, help="YYYY-MM-DD")
    add.add_argument("--document", required=True, help="Exact title of the source document")
    add.add_argument("--source-page", type=int, required=True)
    add.add_argument("--scope", default="group", help="Statement scope, e.g. group or company")
    add.add_argument("--reason", required=True)
    add.add_argument("--author", default="reviewer")
    add.add_argument("--source-text", help="Text copied from the cited page")
    add.add_argument("--supersedes", help="Id of the correction this one replaces")
    add.add_argument("--file", type=Path, help="Correction file (default: config/corrections.yml)")
    return parser


def _iso_date(parser: argparse.ArgumentParser, value: str, flag: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        parser.error(f"{flag} must look like 2026-03-31, not {value!r}")


def _run_command(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
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
            ROOT,
            args.corrections,
            offline=args.offline,
            run_dir=args.run_dir,
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    except OSError as exc:
        if not args.offline:
            raise
        parser.exit(1, f"Offline run needs a cached CSE universe: {exc}\n")
    except httpx.HTTPError as exc:
        parser.exit(1, f"Could not reach the Colombo Stock Exchange website: {exc}\n")
    for kind, path in outputs.items():
        print(f"{kind}: {path}")


def _extract_command(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    period_end = _iso_date(parser, args.period_end, "--period-end")
    if not args.pdf.is_file() or args.pdf.read_bytes()[:4] != b"%PDF":
        parser.error(f"--pdf {str(args.pdf)!r} is not a PDF file")
    settings = load_pipeline_config(ROOT / "config")
    try:
        result = extract_preview(args.pdf, args.kind, period_end, settings)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"Could not read the PDF: {exc}\n")
    result["period_months"] = args.period_months
    json.dump(result, sys.stdout, indent=1, default=str)
    print()


def _corrections_command(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    period_end = _iso_date(parser, args.period_end, "--period-end")
    entry = {
        "ticker": args.ticker,
        "metric": args.metric,
        "financial_period": period_end.isoformat(),
        "source_document": args.document,
        "value": args.value,
        "unit": args.unit,
        "source_page": args.source_page,
        "statement_scope": args.scope,
        "reason": args.reason,
        "author": args.author,
        "corrected_at": datetime.now(ZoneInfo("Asia/Colombo")).date().isoformat(),
    }
    if args.source_text:
        entry["source_text"] = args.source_text
    path = args.file or ROOT / "config" / "corrections.yml"
    try:
        saved = append_correction(path, entry, args.supersedes)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"correction: {saved['id']}")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    # Bare flags (the original interface) mean ``run``.
    if not argv or (argv[0] not in SUBCOMMANDS and argv[0] not in {"-h", "--help"}):
        argv = ["run", *argv]
    args = parser.parse_args(argv)
    if args.command == "run":
        _run_command(parser, args)
    elif args.command == "extract":
        _extract_command(parser, args)
    else:
        _corrections_command(parser, args)


if __name__ == "__main__":
    main()

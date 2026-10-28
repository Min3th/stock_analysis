"""A stand-in for the pipeline's command line, used only by the web app's end-to-end tests.

It serves a committed fixture run directory instead of reading the CSE, and writes the same
kinds of files and messages the real commands do. It contains no financial logic.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE_RUN = HERE.parent / "run"


def run(args) -> None:
    out = Path(args.run_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw = str(HERE / "data" / "raw")
    for source in FIXTURE_RUN.glob("*.json"):
        text = source.read_text(encoding="utf-8").replace("{RAW}", raw.replace("\\", "\\\\"))
        (out / source.name).write_text(text, encoding="utf-8")
    counts = {p.stem: len(json.loads(p.read_text(encoding="utf-8"))) for p in out.glob("*.json")}
    manifest = {
        "run_id": out.name,
        "sector": args.sector,
        "period": args.period,
        "ticker": args.company,
        "offline": args.offline,
        "git_commit": "e2e0000000000000000000000000000000fixture",
        "config_hash": "e2e-fixture",
        "status": "ok",
        "counts": counts,
    }
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    print(f"Running {args.sector} {args.period}")
    print(f"run_manifest: {out / 'manifest.json'}")


def extract(args) -> None:
    json.dump(
        {
            "file": Path(args.pdf).name,
            "kind": args.kind,
            "period_end": args.period_end,
            "pages": 3,
            "parsing_methods": ["native_text"],
            "parser_warnings": [],
            "located_statements": {"income": [2], "position": [3]},
            "facts": [
                {
                    "metric": "net_profit",
                    "value": "6337879000",
                    "unit": "LKR",
                    "original_value": "6337879",
                    "original_unit": "LKR '000",
                    "page": 2,
                    "source_text": "Profit attributable to owners 6,337,879",
                    "statement_scope": "group",
                    "confidence": "0.90",
                    "below_threshold": False,
                    "extraction_method": "primary_income_row",
                    "validation_status": "passed",
                    "validation_notes": "",
                },
                {
                    "metric": "eps",
                    "value": "9.14",
                    "unit": "LKR/share",
                    "original_value": "9.14",
                    "original_unit": "LKR/share",
                    "page": 2,
                    "source_text": "Basic earnings per share 9.14",
                    "statement_scope": "group",
                    "confidence": "0.62",
                    "below_threshold": True,
                    "extraction_method": "label_match_outside_primary_statement",
                    "validation_status": "review",
                    "validation_notes": "unit unconfirmed",
                },
            ],
            "validation_issues": [],
        },
        sys.stdout,
    )
    print()


def uploads_add(args) -> None:
    path = HERE / "config" / "uploads.yml"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"- ticker: {args.ticker}\n  title: {args.title}\n  original_filename: {args.original_name}\n"
        )
    print("upload: abcdef0123456789 data/raw/stub")


def corrections_add(args) -> None:
    path = HERE / "config" / "corrections.yml"
    text = path.read_text(encoding="utf-8")
    count = text.count("- id:") + 1
    correction_id = f"{args.ticker}-{args.metric}-{args.period_end}-{count}"
    body = text.replace("corrections: []", "corrections:") if "corrections: []" in text else text
    body += (
        f"- id: {correction_id}\n  ticker: {args.ticker}\n  metric: {args.metric}\n  value: '{args.value}'\n"
        f"  unit: {args.unit}\n  source_page: {args.source_page}\n  reason: {args.reason}\n"
    )
    path.write_text(body, encoding="utf-8")
    print(f"correction: {correction_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    r = commands.add_parser("run")
    r.add_argument("--sector", required=True)
    r.add_argument("--period", required=True)
    r.add_argument("--company")
    r.add_argument("--offline", action="store_true")
    r.add_argument("--run-dir", required=True)
    e = commands.add_parser("extract")
    e.add_argument("--pdf", required=True)
    e.add_argument("--kind", required=True)
    e.add_argument("--period-end", required=True)
    e.add_argument("--period-months")
    u = commands.add_parser("uploads")
    ua = u.add_subparsers(dest="action", required=True).add_parser("add")
    for name in (
        "--pdf",
        "--ticker",
        "--kind",
        "--period-end",
        "--period-months",
        "--title",
        "--original-name",
    ):
        ua.add_argument(name)
    c = commands.add_parser("corrections")
    ca = c.add_subparsers(dest="action", required=True).add_parser("add")
    for name in (
        "--ticker",
        "--metric",
        "--value",
        "--unit",
        "--period-end",
        "--document",
        "--source-page",
        "--scope",
        "--reason",
        "--author",
        "--source-text",
        "--supersedes",
    ):
        ca.add_argument(name)
    args = parser.parse_args()
    {"run": run, "extract": extract, "uploads": uploads_add, "corrections": corrections_add}[
        args.command
    ](args)


if __name__ == "__main__":
    main()

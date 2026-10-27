"""Fill rates and reconciliation pass rates for every supported industry group.

    python scripts/coverage_report.py                  # cached groups only, no network
    python scripts/coverage_report.py --groups Banks   # one or more groups
    python scripts/coverage_report.py --live           # fetch groups that are not cached

Groups whose universe is not in ``data/raw/cse_universe`` are listed as
``not cached`` rather than fetched, because seeding a group downloads every
annual report and interim statement for it. ``--live`` opts in to that.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cse_screening.downloaders.universe import SUPPORTED_INDUSTRY_GROUPS
from cse_screening.pipeline import run

FILL_METRICS = (
    "Revenue",
    "Net Profit",
    "EPS",
    "ROE",
    "ROA",
    "Debt-to-Equity",
    "Operating Cash Flow",
    "Free Cash Flow",
    "P/E",
    "P/B",
    "DPS",
)
# Validation rules that mean an identity between extracted facts did not hold.
RECONCILIATION_RULES = (
    "accounting_equation",
    "share_count_identity",
    "eps_profit_sign",
    "profit_revenue_scale",
)


def slug(group: str) -> str:
    return "_".join("".join(c if c.isalnum() else " " for c in group.casefold()).split())


def cached(group: str) -> bool:
    return (ROOT / "data" / "raw" / "cse_universe" / f"{slug(group)}.json").exists()


def measure(group: str, period: str, live: bool) -> dict:
    outputs = run(period, group, None, ROOT, offline=not live)
    review = pd.read_csv(outputs["review"]) if "review" in outputs else pd.DataFrame()
    if "csv" not in outputs:
        return {"group": group, "issuers": 0, "note": "no screening rows"}
    table = pd.read_csv(outputs["csv"])
    issuers = len(table)
    fills = {}
    for metric in FILL_METRICS:
        # A ratio marked not applicable for an issuer is not a gap for that issuer.
        applicable = ~table.get("Not Applicable Metrics", pd.Series("", index=table.index)).fillna(
            ""
        ).str.contains(metric, regex=False)
        denominator = int(applicable.sum())
        fills[metric] = (
            round(float(table.loc[applicable, metric].notna().sum()) / denominator, 2)
            if denominator
            else None
        )
    flagged = (
        review[review["Validation Rule"].isin(RECONCILIATION_RULES)]["Ticker"].nunique()
        if len(review)
        else 0
    )
    return {
        "group": group,
        "issuers": issuers,
        "fill": fills,
        "reconciled": round(1 - flagged / issuers, 2),
        "high_confidence": round(float((table["Data Confidence"] == "high").mean()), 2),
        "ttm": round(
            float(table["Income Period Basis"].fillna("").str.startswith("TTM").mean()), 2
        ),
    }


def render(results: list[dict], period: str) -> str:
    lines = [
        f"# Coverage report {period}",
        "",
        "Share of issuers with a value (not-applicable ratios excluded); reconciled = issuers",
        "with no failed identity (assets = liabilities + equity, EPS x shares ~ profit, signs, scale).",
        "",
        "| Group | Issuers | " + " | ".join(FILL_METRICS) + " | Reconciled | High conf. | TTM |",
        "| --- | ---: | " + " | ".join("---:" for _ in FILL_METRICS) + " | ---: | ---: | ---: |",
    ]
    for item in results:
        if "fill" not in item:
            lines.append(f"| {item['group']} | {item.get('issuers', '')} | {item['note']} |")
            continue
        cells = [("n/a" if v is None else f"{v:.0%}") for v in item["fill"].values()]
        lines.append(
            f"| {item['group']} | {item['issuers']} | "
            + " | ".join(cells)
            + f" | {item['reconciled']:.0%} | {item['high_confidence']:.0%} | {item['ttm']:.0%} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--period", default="2026Q3")
    parser.add_argument("--groups", help="Comma-separated industry groups (default: all)")
    parser.add_argument("--live", action="store_true", help="Fetch groups that are not cached")
    parser.add_argument("--out", type=Path, help="Also write the table to this Markdown file")
    args = parser.parse_args()
    groups = (
        [g.strip() for g in args.groups.split(",")] if args.groups else SUPPORTED_INDUSTRY_GROUPS
    )
    results = []
    for group in groups:
        if not args.live and not cached(group):
            results.append({"group": group, "note": "not cached (run with --live to fetch)"})
            continue
        try:
            results.append(measure(group, args.period, args.live))
        except (OSError, ValueError) as exc:
            results.append({"group": group, "note": f"failed: {exc}"})
    text = render(results, args.period)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

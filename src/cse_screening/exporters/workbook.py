"""Required Excel, CSV, Markdown, and review exports."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

SHEETS = [
    "01_Screening",
    "02_Raw_Data",
    "03_Ratios",
    "04_History",
    "05_Dividends",
    "06_Sources",
    "07_Flags",
    "08_Summary",
]
PERCENT_COLUMNS = {
    "Revenue Growth YoY",
    "Net Profit Growth YoY",
    "EPS Growth YoY",
    "3Y Revenue CAGR",
    "3Y EPS CAGR",
    "ROE",
    "ROA",
    "Dividend Yield",
    "Payout Ratio",
    "Earnings Yield",
}


def export_all(
    period: str,
    industry_group: str,
    output: Path,
    screening: list[dict],
    raw: list[dict],
    ratios: list[dict],
    history: list[dict],
    dividends: list[dict],
    sources: list[dict],
    flags: list[dict],
    review: list[dict],
) -> dict[str, Path]:
    output.mkdir(parents=True, exist_ok=True)
    safe_group = "_".join(re.findall(r"[A-Za-z0-9]+", industry_group))
    stem = f"{safe_group}_Screening_{period}"
    workbook_path = output / f"{stem}.xlsx"
    csv_path = output / f"{stem}.csv"
    summary_path = output / f"{safe_group}_Summary_{period}.md"
    review_path = output / "manual_review.csv"
    warning_path = output / "extraction_warnings.jsonl"

    frames = {
        "01_Screening": pd.DataFrame(screening),
        "02_Raw_Data": pd.DataFrame(raw),
        "03_Ratios": pd.DataFrame(ratios),
        "04_History": pd.DataFrame(history),
        "05_Dividends": pd.DataFrame(dividends),
        "06_Sources": pd.DataFrame(sources),
        "07_Flags": pd.DataFrame(flags),
        "08_Summary": _summary_frame(screening),
    }
    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        for sheet in SHEETS:
            frames[sheet].to_excel(writer, sheet_name=sheet, index=False)
        _format_workbook(writer.book)
    frames["01_Screening"].to_csv(csv_path, index=False)
    pd.DataFrame(review).to_csv(review_path, index=False)
    warning_path.write_text(
        "".join(json.dumps(item, default=str) + "\n" for item in review), encoding="utf-8"
    )
    summary_path.write_text(
        _neutral_markdown_summary(period, industry_group, screening, review), encoding="utf-8"
    )
    return {
        "xlsx": workbook_path,
        "csv": csv_path,
        "markdown": summary_path,
        "review": review_path,
        "warnings": warning_path,
    }


def _format_workbook(workbook) -> None:
    for ws in workbook.worksheets:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
        for column in ws.columns:
            width = min(45, max(10, max(len(str(cell.value or "")) for cell in column) + 2))
            ws.column_dimensions[get_column_letter(column[0].column)].width = width
        headers = {cell.value: cell.column for cell in ws[1]}
        for name in PERCENT_COLUMNS:
            if name in headers:
                for cell in ws.iter_cols(min_col=headers[name], max_col=headers[name], min_row=2):
                    for item in cell:
                        item.number_format = "0.00%;[Red]-0.00%"
        if ws.title == "01_Screening" and ws.max_row > 1:
            for name in ("P/E", "P/B", "ROE", "Debt-to-Equity", "Dividend Yield"):
                if name in headers:
                    letter = get_column_letter(headers[name])
                    ws.conditional_formatting.add(
                        f"{letter}2:{letter}{ws.max_row}",
                        ColorScaleRule(
                            start_type="min",
                            start_color="F8696B",
                            mid_type="percentile",
                            mid_value=50,
                            mid_color="FFEB84",
                            end_type="max",
                            end_color="63BE7B",
                        ),
                    )


def _summary_frame(rows: list[dict]) -> pd.DataFrame:
    metrics = ["P/E", "P/B", "ROE", "Dividend Yield"]
    data = []
    frame = pd.DataFrame(rows)
    for metric in metrics:
        series = (
            pd.to_numeric(frame[metric], errors="coerce")
            if metric in frame
            else pd.Series(dtype=float)
        )
        data.append(
            {
                "Metric": f"Sector median {metric}",
                "Value": series.median() if not series.empty else None,
            }
        )
    data.insert(0, {"Metric": "Companies processed", "Value": len(rows)})
    return pd.DataFrame(data)


def _markdown_summary(period: str, rows: list[dict], review: list[dict]) -> str:
    frame = pd.DataFrame(rows)
    lines = [
        f"# Capital Goods screening summary — {period}",
        "",
        f"Companies processed: **{len(rows)}**.",
        "",
    ]
    for metric in ("P/E", "P/B", "ROE", "Dividend Yield"):
        series = (
            pd.to_numeric(frame[metric], errors="coerce").dropna()
            if metric in frame
            else pd.Series(dtype=float)
        )
        value = series.median() if not series.empty else None
        rendered = "NA" if value is None else f"{value:.4f}"
        lines.append(f"- Sector median {metric}: {rendered}")
    missing = [row["Ticker"] for row in rows if row.get("Data Confidence") != "high"]
    lines += [
        "",
        "## Missing data and warnings",
        "",
        f"Companies requiring review: {', '.join(missing) or 'None'}.",
        f"Manual-review items: {len(review)}.",
        "",
        "This report contains no ranking, score, selection, or investment recommendation.",
        "",
    ]
    return "\n".join(lines)


def _neutral_markdown_summary(
    period: str, industry_group: str, rows: list[dict], review: list[dict]
) -> str:
    frame = pd.DataFrame(rows)
    lines = [
        f"# {industry_group} screening summary - {period}",
        "",
        f"Companies processed: **{len(rows)}**.",
        "",
    ]
    for metric in ("P/E", "P/B", "ROE", "Dividend Yield"):
        series = (
            pd.to_numeric(frame[metric], errors="coerce").dropna()
            if metric in frame
            else pd.Series(dtype=float)
        )
        value = series.median() if not series.empty else None
        rendered = "NA" if value is None else f"{value:.4f}"
        lines.append(f"- Sector median {metric}: {rendered}")
    missing = [row["Ticker"] for row in rows if row.get("Data Confidence") != "high"]
    lines += [
        "",
        "## Missing data and warnings",
        "",
        f"Companies requiring review: {', '.join(missing) or 'None'}.",
        f"Manual-review items: {len(review)}.",
        "",
        "This report contains no ranking, score, selection, or investment recommendation.",
        "",
    ]
    return "\n".join(lines)

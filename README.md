# CSE Capital Goods Screening Pipeline

A reusable, traceable Python pipeline for quarterly screening of Colombo Stock
Exchange companies in the Capital Goods industry group.

The working pilot processes Access Engineering, ACL Cables, and Hayleys using
official investor-relations reports plus current CSE market data. Extraction is
deliberately conservative: incomplete fields are exported to manual review.

## Design priorities

1. Accuracy and traceability take precedence over completeness.
2. Every raw value retains its document, URL, page, period, unit, confidence,
   extraction method, source text, and notes.
3. Annual, interim, year-to-date, and trailing-twelve-month periods remain
   explicit and are never silently mixed or annualized.
4. Missing or unreliable values remain null and flow into manual review.
5. Calculated metrics retain their formula and the exact input records used.

## Setup

Python 3.11 or later is required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

OCR is optional and is not invoked unless a page fails the text-density test:

```powershell
python -m pip install -e ".[ocr]"
```

## Command line

```powershell
python main.py --sector "Capital Goods" --period 2026Q3
python main.py --company ACL.N0000 --period 2026Q3
```

Downloaded PDFs are cached under `data/raw/<ticker>/`. Rerunning the same URLs
uses the cached bytes and records a cache hit in `06_Sources`.

## Structure

```text
config/                 configurable universe and pipeline settings
data/raw/               cached source documents (ignored by Git)
data/processed/         normalized intermediate datasets (ignored by Git)
docs/                   architecture, methodology, and risk decisions
reports/                generated XLSX, CSV, Markdown, and review files
src/cse_screening/
  calculations/         ratios, growth, and calculation lineage
  downloaders/          CSE/company discovery, download, and cache handling
  exporters/            Excel, CSV, Markdown, and review outputs
  extractors/           statement metric recognition and candidates
  parsers/              PDF text/table/OCR strategies
  validators/           accounting, period, range, and anomaly checks
tests/                   unit and end-to-end fixture tests
```

See [architecture.md](docs/architecture.md) for the component flow and
[technical-risks.md](docs/technical-risks.md) for the initial risk register.

## Domain references

The following user-supplied CSE educational PDFs are local-only methodology
references and are excluded from version control:

- `Stock-Selection-Desision-Making-English.pdf`
- `Understanding-Financial-Statements-English.pdf`

They define concepts, terminology, statement locations, and interpretation.
They must never be treated as sources for company-specific values. Actual
figures must come from current official CSE disclosures or company investor
relations documents.

## Company configuration

Edit `config/companies.yml`. Each entry records the ticker, official CSE profile,
date-stamped classification source, and official document URLs. The example file
is safe to copy when creating another universe. Do not put extracted financial
values in configuration; facts must originate from source documents.

The official CSE sector-statistics report dated 25 September 2026 reports 30
listed Capital Goods securities. The pilot does not assert a full 28- or
30-company constituent list; that must be obtained from a date-stamped official
classification source before the expansion milestone.

## Extraction and review

PDF pages are retained as page-numbered text. Statement headings narrow the
search area, metric aliases produce candidates, reported units are normalized to
base LKR, and note references are separated from values. The workbook preserves
original value/unit/text and the normalized result. Low-confidence or absent
facts appear in `reports/manual_review.csv` rather than being guessed.

For a manual correction, first verify the consolidated/group column and period
in the cited PDF. Record the candidate and reason in the review file; the planned
next hardening step is an append-only YAML correction overlay so corrections
remain reproducible without changing source evidence.

The supplied CSE educational documents informed the distinction between the
income statement, statement of financial position, cash-flow statement, and
per-share/valuation measures. Their formulas and terminology guide extraction;
they are never used as company-specific facts.

## Known limitations

- The pilot extractor handles text PDFs; OCR fallback is configured but not yet
  wired into the parser.
- Current/prior Group values are accepted only when column order is reliable.
  Three-year history remains null when scope cannot be proven.
- Total debt, capex, retained earnings, dividends, and one-off items often need
  note-level extraction, which is still pending.
- TTM construction is intentionally not implemented until non-overlapping
  quarters can be validated.
- Dividend-announcement discovery and the complete sector universe remain part
  of the scale-up milestone.
- CSE's public market endpoint is operational but undocumented; failures become
  review items rather than silent gaps.

## Milestone plan

1. Architecture and data contracts (complete).
2. End-to-end pilot for three representative companies, including tests and
   initial Excel/CSV/Markdown output (complete).
3. Harden extraction strategies and manual corrections from review findings.
4. Expand the configurable universe to all current Capital Goods companies.


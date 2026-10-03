# CSE Capital Goods Screening Pipeline

A reusable, traceable Python pipeline for quarterly screening of Colombo Stock
Exchange companies in the Capital Goods industry group.

This repository is being delivered in independently working milestones. The
current milestone establishes the architecture, data contracts, configuration,
and engineering risk register. It intentionally contains no company-specific
financial values yet.

## Design priorities

1. Accuracy and traceability take precedence over completeness.
2. Every raw value retains its document, URL, page, period, unit, confidence,
   extraction method, source text, and notes.
3. Annual, interim, year-to-date, and trailing-twelve-month periods remain
   explicit and are never silently mixed or annualized.
4. Missing or unreliable values remain null and flow into manual review.
5. Calculated metrics retain their formula and the exact input records used.

## Planned command line

```powershell
python main.py --sector "Capital Goods" --period 2026Q3
python main.py --company HHL.N0000 --period 2026Q3
```

The CLI becomes executable in milestone 2, after document discovery and the
first representative-company adapters are implemented.

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

## Milestone plan

1. Architecture and data contracts (current milestone).
2. End-to-end pipeline for 2–3 representative companies, including tests and
   initial Excel/CSV/Markdown output.
3. Harden extraction strategies and manual corrections from review findings.
4. Expand the configurable universe to all current Capital Goods companies.


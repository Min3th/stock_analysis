# CSE Capital Goods Screening Pipeline

A reusable, traceable Python pipeline for quarterly screening of Colombo Stock
Exchange companies in the Capital Goods industry group.

The pipeline resolves any supported CSE GICS industry group at runtime from the
official classification endpoints. Access Engineering, ACL Cables, and Hayleys
currently have document extraction configurations; every other constituent is
included with official market data and explicit missing-document review items.
Extraction is deliberately conservative: incomplete fields are exported to
manual review.

## Design priorities

1. Accuracy and traceability take precedence over completeness.
2. Every raw value retains its document, URL, page, period, unit, confidence,
   extraction method, source text, and notes.
3. Annual, interim, year-to-date, and trailing-twelve-month periods remain
   explicit. TTM is calculated only from four discrete quarters or as latest FY
   plus current YTD less the matching prior YTD; partial periods are never
   silently annualized.
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
python main.py --sector "Banks" --period 2026Q3
python main.py --company ACL.N0000 --period 2026Q3
```

Downloaded PDFs are cached under `data/raw/<ticker>/`. Rerunning the same URLs
uses the cached bytes and records a cache hit in `06_Sources`.
Official CSE cash-dividend announcements are discovered on every run. Their
structured details are cached under `data/raw/cse_announcements/`, attachments
under the issuer cache, and results are written to `05_Dividends`.

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

The company universe is downloaded from CSE each run. `config/companies.yml` is
an optional ticker-keyed overlay for official report URLs and publication dates;
it does not define sector membership. Do not put extracted financial values in
configuration; facts must originate from source documents.

Supported `--sector` values are Energy, Materials, Capital Goods, Commercial &
Professional Services, Transportation, Automobiles & Components, Consumer
Durables & Apparel, Consumer Services, Retailing, Food & Staples Retailing,
Food, Beverage & Tobacco, Household & Personal Products, Health Care Equipment
& Services, Banks, Diversified Financials, Insurance, Software & Services,
Telecommunication Services, Utilities, and Real Estate Management & Development.

The current CSE hierarchy names the last category `Real Estate`; both names are
accepted. CSE currently exposes the former `Software & Services` category as
`Technology Hardware & Equipment`, so both inputs resolve to that official group.
At the time of validation, the CSE endpoint returned no listed constituents for
that technology group; the pipeline therefore creates a valid empty report rather
than substituting companies from another category.

The CSE universe response is authoritative for a run and may differ from a daily
sector-statistics security count because of inactive or separately listed share
classes. The source URL and runtime result are retained rather than forcing a
hard-coded expected count.

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
- Total debt, capex, retained earnings, operating cash flow, free cash flow, ROE,
  and ROA are extracted/calculated for configured reports with page-level input
  lineage. Narrative one-off items still need broader note-level discovery.
- TTM construction requires explicit `period_months` and
  `comparative_period_end` metadata and compatible current/prior YTD columns.
  It returns null rather than estimating when that evidence is absent.
- The CSE corporate-disclosure feed supplies its current announcement window,
  not a guaranteed complete historical archive. The pipeline collects all cash
  dividends in that feed matching the selected universe and caches their PDFs.
- Automatic financial-document discovery remains part of the scale-up milestone.
  Until then, unconfigured tickers are market-data-only.
- CSE's public market endpoint is operational but undocumented; failures become
  review items rather than silent gaps.

## Milestone plan

1. Architecture and data contracts (complete).
2. End-to-end pilot for three representative companies, including tests and
   initial Excel/CSV/Markdown output (complete).
3. Harden extraction strategies and manual corrections from review findings.
4. Add automatic document discovery and extraction coverage across every current
   constituent returned for the selected industry group.

## Neutrality policy

The program does not rank securities, assign a score, select a security, or
produce investment recommendations. Outputs contain raw values, calculated
metrics, sector medians, provenance, and data-quality warnings only.


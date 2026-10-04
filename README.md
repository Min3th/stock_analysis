# CSE Capital Goods Screening Pipeline

A reusable, traceable Python pipeline for quarterly screening of Colombo Stock
Exchange companies in the Capital Goods industry group.

The pipeline resolves any supported CSE GICS industry group at runtime from the
official classification endpoints. It queries the official CSE financial archive
for the latest three annual periods and latest interim filing of every selected issuer, downloads and
caches those reports, and runs the same traceable extraction flow across the full
universe. Extraction is deliberately conservative: incomplete fields are
exported to manual review.

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

The OCR extra supplies the Python integration; the Tesseract executable must also
be installed and available on `PATH`. If OCR is required but unavailable, the
page is retained, the value stays missing, and a `parser_fallback` item is written
to manual review. PyMuPDF table recognition is enabled by default and requires no
external executable. Parser settings are under `ocr` and `tables` in
`config/pipeline.example.yml`.

## Command line

```powershell
python main.py --sector "Capital Goods" --period 2026Q3
python main.py --sector "Banks" --period 2026Q3
python main.py --company ACL.N0000 --period 2026Q3
python main.py --company ACL.N0000 --period 2026Q3 --corrections config/corrections.yml
```

Downloaded PDFs are cached under `data/raw/<ticker>/`. Rerunning the same URLs
uses the cached bytes and records a cache hit in `06_Sources`.
The CSE financial-announcement index is refreshed at most every 15 minutes and
cached under `data/raw/cse_financial_announcements/`. Extracted page text is
cached beside each PDF, substantially reducing repeat-run time.
Official CSE cash-dividend announcements are discovered on every run. Their
structured details are cached under `data/raw/cse_announcements/`, attachments
under the issuer cache, and results are written to `05_Dividends`.

Each run also writes `reports/extraction_warnings.jsonl`. This machine-readable
log mirrors missing, low-confidence, validation, and document-error records from
`manual_review.csv`.

The Markdown summary reports processing confidence, sector medians, missing
fields by ticker, neutral highest/lowest observed values, anomaly counts, and
grouped extraction warnings. It does not rank or recommend companies. Excel
outputs use separate formats for LKR amounts, per-share values, whole-share and
volume counts, ratios, and percentages; negatives use red parentheses, while
conditional formatting highlights negative financial results and populated flag
cells.

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

The company universe is downloaded from CSE each run. Annual and interim reports
are discovered from `getFinancialAnnouncement` using a rolling three-year archive
window, exact issuer-symbol matching, conservative title classification, and
period parsing. `config/companies.yml` remains an optional ticker-keyed fallback;
the newest document per kind wins. Do not put extracted financial values in
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

`01_Screening` includes reported operating profit, EBIT, and ordinary shares
outstanding. EBIT uses an explicitly reported EBIT/profit-before-interest-and-tax
line when one is accepted; otherwise the displayed EBIT is an operating-profit
proxy and `03_Ratios` labels that formula and its source fact. Share extraction
prefers a period-end issued ordinary-share count. A weighted-average share count
is used only as a lower-confidence, explicitly noted fallback so it is routed to
manual review rather than silently treated as the period-end balance.

`02_Raw_Data` records the extraction method, validation status, and validation
notes for every fact. Current validation checks unknown unit/column context,
the accounting equation (`assets = liabilities + equity`) with a 5% tolerance,
and extreme profit-to-revenue scale conflicts. A failed check preserves the
reported value, lowers its confidence, changes its validation status to
`review`, and writes the candidate values, page, source text, strategy, rule,
and reason to both review outputs.

`07_Flags` contains one evidence row per descriptive anomaly. Rules cover
negative EPS/equity/operating cash flow, two consecutive annual declines in EPS
or revenue, weak cash conversion, high debt-to-equity, payout above 100%,
positive P/E and P/B outliers relative to their sector medians, multi-day low
or insufficient trading-volume history, and explicit one-off/non-recurring
profit or loss wording. Thresholds are configured under `flags` in
`config/pipeline.example.yml`. Liquidity uses average and median volume from the
latest 20 locally captured CSE trading-day observations. A run upserts the
official volume for the CSE trading date under `data/raw/market_liquidity/`;
same-day reruns do not create duplicates. Until the configured minimum sample is
available, the result is explicitly flagged as insufficient multi-day history
instead of treating one day as representative. One-off flags retain the report,
URL, page, and matching excerpt for analyst review.

For a manual correction, first verify the consolidated/group column, unit,
period, and page in the cited PDF. Copy the unresolved item into
`config/corrections.yml` using this form:

```yaml
corrections:
  - id: acl-revenue-fy26-v1
    status: active
    ticker: ACL.N0000
    metric: revenue
    financial_period: 2026-03-31
    source_document: Annual Report 2025/26
    value: "45507.610"
    unit: LKR million
    source_page: 122
    statement_scope: group
    source_text: "Revenue 45,507.610 ..."
    reason: Verified against the consolidated current-year column
    author: analyst-name
    corrected_at: 2026-10-03
```

`value` is expressed in the stated `unit` and normalized by the pipeline. The
ticker, period, and document title must match exactly; stale or misspelled active
entries stop the run instead of silently doing nothing. The extracted candidate
remains in `02_Raw_Data`, while the accepted correction is added as a separate
row with `Correction ID`, confidence 1.0, author/date/reason, and its own fact ID.
Calculated ratios cite that corrected fact ID.

Do not delete an old correction. Mark it `status: superseded` and append a new
entry with a new ID. Only one active correction may target a given ticker,
metric, period, and source document. The default overlay is version-controlled;
use `--corrections <path>` for a different overlay.

The supplied CSE educational documents informed the distinction between the
income statement, statement of financial position, cash-flow statement, and
per-share/valuation measures. Their formulas and terminology guide extraction;
they are never used as company-specific facts.

## Known limitations

- Native text, PyMuPDF table recognition, and page-level Tesseract OCR are wired
  into a layered parser. OCR still depends on the optional Python packages and a
  system Tesseract installation; unavailable engines produce review warnings.
- Current/prior Group values are accepted only when column order is reliable.
  History and CAGR remain null when three consecutive, matching fiscal year-ends
  cannot be proven or when CAGR is mathematically undefined for negative values.
- Validation is intentionally conservative and does not prove that a value is
  correct. Holding-company presentations and unusual classifications can trigger
  review even when reported correctly; use the cited page and correction overlay
  to resolve those cases.
- Automatic discovery selects the latest three distinct annual periods and the
  latest interim report per issuer. Overlapping annual comparatives are
  deduplicated in favor of the directly reported current-year observation, while
  preserving source period, value basis, page, and confidence in `04_History`.
  Errata, prospectuses, trust deeds, articles, and accountants'
  reports are excluded; unusual CSE titles that contain no recognizable period
  are left unmatched rather than guessed.
- Total debt, capex, retained earnings, operating cash flow, free cash flow, ROE,
  and ROA are extracted/calculated for configured reports with page-level input
  lineage. Narrative one-off items still need broader note-level discovery.
- TTM construction requires explicit `period_months` and
  `comparative_period_end` metadata and compatible current/prior YTD columns.
  It returns null rather than estimating when that evidence is absent.
- The CSE corporate-disclosure feed supplies its current announcement window,
  not a guaranteed complete historical archive. The pipeline collects all cash
  dividends in that feed matching the selected universe and caches their PDFs.
- CSE's public market endpoint is operational but undocumented; failures become
  review items rather than silent gaps.
- CSE does not expose a stable public per-security historical-volume endpoint.
  Multi-day liquidity therefore accumulates from official daily snapshots across
  runs. Run the pipeline after each trading day (or on a daily schedule) to build
  the configured 20-day window; the default minimum is five observations.

## Milestone plan

1. Architecture and data contracts (complete).
2. End-to-end pilot for three representative companies, including tests and
   initial Excel/CSV/Markdown output (complete).
3. Harden extraction strategies and manual corrections from review findings
   (persistent correction overlay complete; broader extraction hardening ongoing).
4. Automatic document discovery and extraction coverage across every current
   constituent returned for the selected industry group (complete for the live
   Capital Goods validation; extractor hardening remains ongoing).

## Neutrality policy

The program does not rank securities, assign a score, select a security, or
produce investment recommendations. Outputs contain raw values, calculated
metrics, sector medians, provenance, and data-quality warnings only.


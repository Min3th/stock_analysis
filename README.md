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
   explicit. TTM is calculated only as latest FY plus current YTD less the
   matching prior YTD, and only when the interim statement header proves the
   year-to-date length. A bare interim figure never appears in the screening
   table, partial periods are never annualized, and every calculated value
   states the period it is based on.
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
external executable. Parser settings are under `ocr` and `tables` in the
pipeline settings.

### Settings

`config/pipeline.example.yml` holds every default: the confidence threshold,
output directories, parser options and anomaly thresholds. To change one,
create `config/pipeline.yml` containing only the keys you want to override;
nested sections such as `flags` are merged with the defaults.

```yaml
# config/pipeline.yml
confidence_threshold: 0.85
flags:
  high_debt_to_equity: 1.5
```

## Command line

```powershell
python main.py --sector "Capital Goods" --period 2026Q3
python main.py --sector "Banks" --period 2026Q3
python main.py --company HHL.N0000
python main.py --company ACL.N0000 --period 2026Q3 --corrections config/corrections.yml
```

`--period` is the label written into the output filenames. It defaults to the
current calendar quarter, so the quarterly rerun is just
`python main.py --sector "Capital Goods"`. `--company` runs one ticker from the
selected industry group for debugging.

Each run writes, under `reports/`:

| File | Contents |
| --- | --- |
| `Capital_Goods_Screening_2026_Q3.xlsx` | Workbook with `00_Universe` and `01_Screening` to `08_Summary` |
| `Capital_Goods_Screening_2026_Q3.csv` | The `01_Screening` table |
| `Capital_Goods_Summary_2026_Q3.md` | Counts, sector medians, highest/lowest raw values, warnings |
| `Capital_Goods_Universe_2026_Q3.csv` | Membership decisions |
| `manual_review.csv`, `extraction_warnings.jsonl` | Every value that was withheld or flagged |

The raw-fact, ratio and history tables are also written as CSV under
`data/processed/`.

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
data/processed/         raw-fact, ratio and history tables as CSV (ignored by Git)
docs/                   architecture, methodology, and risk decisions
reports/                generated XLSX, CSV, Markdown, and review files
src/cse_screening/
  calculations/         ratios, period-safe fact selection, and calculation lineage
  downloaders/          CSE/company discovery, download, and cache handling
  exporters/            Excel, CSV, Markdown, and review outputs
  extractors/           statement location, column layout, and metric candidates
  parsers/              PDF text/table/OCR strategies
  validators/           accounting, period, range, and anomaly checks
tests/                   unit and end-to-end fixture tests
```

See [architecture.md](docs/architecture.md) for the component flow and
[technical-risks.md](docs/technical-risks.md) for the initial risk register.
AI coding agents continuing development should begin with
[AGENTS.md](AGENTS.md), which records project invariants, validation gates, and
the expected handoff format for each committed stage.

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

The `universe` section applies membership independently of document fallbacks:

```yaml
universe:
  exclude:
    - EXAMPLE.N0000
  include:
    - ticker: MANUAL.N0000
      name: MANUALLY INCLUDED PLC
      industry_group: Capital Goods
      profile_url: https://www.cse.lk/pages/company-profile/company-profile.component.html?symbol=MANUAL.N0000
      classification_source_url: https://example.com/classification-evidence
  overrides:
    KEEP.N0000:
      name: CORRECTED DISPLAY NAME PLC
```

Exclusions take precedence. Includes may add a ticker even when it is absent
from the current CSE response. Overrides only modify current official members;
an unknown override stops the run so configuration mistakes are not ignored.
`companies` continues to hold document URL fallbacks and does not change
membership. Every decision, including excluded and no-longer-present tickers, is
written to `00_Universe` and `reports/<Sector>_Universe_<Period>.csv` with company
name, ticker, GICS sector and industry group, profile URL, classification date,
classification source, membership source, and inclusion decision.

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

The CSE universe response is the default authority for a run and may differ from
a daily sector-statistics security count because of inactive or separately
listed share classes. Explicit includes/excludes are retained as auditable
configuration decisions rather than silently changing the official response.

## Extraction and review

PDF pages are retained as page-numbered text. Extraction then works in four
steps.

1. **Locate the primary statements.** Every page is scored for how strongly it
   resembles an income statement, a statement of financial position or a
   cash-flow statement (title plus characteristic rows). The best adjacent set
   is chosen, with continuation pages. Multi-year summaries, segment tables and
   US-dollar translations are scored down, so they cannot supply a metric.
2. **Read the column layout.** The page header gives the order of the Group and
   Company blocks, the order of the years, any restated third column and any
   % change column. The consolidated current-year cell is selected from that
   layout; a nil dash keeps its column. `Statement Scope` in `02_Raw_Data`
   records which block was read and whether the row's cell count agreed with
   the header (`confirmed`) or the leading pair was taken (`assumed`).
3. **Read the row.** Labels wrapped over two lines are rejoined. A note
   reference is told apart from an amount by how it is written (`11` or `10.1`
   in front of `2.98 2.70`), not by its size. The unit comes from the statement
   header or an explicit sentence such as "All values are in Rupees '000s"; a
   page with no unit takes the unit of the other primary statements.
4. **Fill gaps only by identity.** Total liabilities (total assets less total
   equity) and parent equity (total equity less non-controlling interests) are
   derived when the statement prints no such row, and the derivation is named
   in `Extraction Method`. A label match elsewhere in the document is kept only
   as a low-confidence review candidate. Net assets per share and dividend per
   share are also read from highlights when the statements do not print them.

### Validation and the reliability gate

`02_Raw_Data` records the extraction method, validation status and validation
notes for every fact. A fact whose confidence is below `confidence_threshold`
(0.80) is **not used**: its screening cell is left empty, and its candidate
values, page, source text, strategy and reason go to `manual_review.csv`. The
`Used In Screening` column shows which facts fed the table.

Checks applied to each document:

- unit or column context not established;
- the accounting equation (`assets = liabilities + equity`) within 5%;
- net profit more than twice revenue;
- EPS and profit with opposite signs.

Checks applied to the latest annual report, whose values feed the table:

- EPS against attributable profit / CSE share count;
- share count against attributable profit / EPS and the CSE-implied count. A
  count stated in thousands or millions is rescaled only when the scaled count
  matches a reference within 5%, and the note says so. A count that matches
  nothing (a weighted average, one class of a dual-class issuer, a pre-split
  count) is withheld;
- reported book value per share against parent equity / shares. A figure
  printed on the statement itself stands and the difference is noted; a
  highlight figure that does not reconcile is replaced by the calculated one;
- DPS negative or more than five times EPS.

When no reported share count passes, the current count implied by CSE market
data (market capitalisation / last price) is used and labelled. It is a current
count, not the balance-sheet-date count, and it is not used for issuers with
more than one listed class.

`Data Confidence` is `high` when all six core metrics of the latest annual
report (revenue, net profit, EPS, total assets, total equity, operating cash
flow) are usable and none is under review, `low` when fewer than three are, and
`review` otherwise or when the latest annual report is out of date or does not
cover twelve months. It reports what the automated checks found. It is not a
manual verification.

### Periods and calculations

- Balance-sheet figures, ROE, ROA, debt-to-equity, net debt and book value per
  share come from the latest annual report only (`Balance Sheet Date`). An
  older report never fills a gap in the latest one.
- Revenue, profit and EPS are TTM when the latest interim statement gives a
  proven year-to-date pair, otherwise the latest financial year
  (`Income Period Basis`). Operating cash flow and capital expenditure follow
  the same rule separately (`Cash Flow Period Basis`). Every `03_Ratios` row
  carries its `Period Basis`.
- TTM needs the interim header to name the period ("three months ended",
  "quarter", "period ended"). Where a page shows a quarter block and a
  cumulative block, the cumulative block is read. Year-to-date revenue far out
  of proportion to the year rejects the income TTM.
- P/E and earnings yield use EPS on the income basis. Payout ratio uses DPS and
  EPS for the same financial year. OCF / net profit uses profit for the same
  period as the cash flow.
- Growth compares the current and comparative columns of the latest annual
  statement. Three-year CAGR uses the comparative from the prior year's report
  and is withheld, with the reason in `03_Ratios`, when the latest report
  restated the prior year (for example after a share split).
- P/E, P/B, ROE, debt-to-equity and payout are left empty on a zero or negative
  base; the negative EPS or equity itself, and earnings yield, are kept.
- A financial year that is not twelve months is labelled (for example
  `15 months to 2026-03-31`), flagged, and not compared with a twelve-month
  year.

`01_Screening` starts with the 27 specified columns in the specified order,
followed by supporting columns: net profit growth, operating profit, EBIT, book
value per share, shares, retained earnings, the period-basis columns and the
liquidity columns. EBIT uses a reported EBIT line when one is accepted;
otherwise it is an operating-profit proxy and `03_Ratios` says so.

`07_Flags` contains one evidence row per descriptive anomaly. Rules cover
negative EPS/equity/operating cash flow, two consecutive annual declines in EPS
or revenue, weak cash conversion, high debt-to-equity, payout above 100%,
positive P/E and P/B outliers relative to their sector medians, multi-day low
or insufficient trading-volume history, and explicit one-off/non-recurring
profit or loss wording. The decline flags compare each year with the
comparative in the same report, so a share split is not read as a decline.
Thresholds are configured under `flags` in the pipeline settings. Liquidity uses average and median volume from the
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

- **The figures have not been checked by hand against the PDFs.** The
  statement extraction was developed and checked against the cached text of
  103 filings from 27 Capital Goods issuers using accounting identities (assets
  = liabilities + equity; EPS x shares against attributable profit). Those
  checks catch wrong columns, units and rows; they do not prove a value is
  right. Treat `high` confidence as "passed the automated checks" and verify a
  company's page citations before relying on its numbers.
- Statement layouts outside that sample can defeat the locator or the layout
  reader. The value is then withheld or marked `assumed`, not guessed, and
  appears in `manual_review.csv`. Other industry groups, banks and insurers in
  particular, use different statement rows and have not been tested.
- TTM has only been exercised on first-quarter interim statements. Half-year
  and nine-month layouts (quarter and cumulative blocks) are handled by rule
  and unit tests, not yet by real filings; where the year-to-date block cannot
  be proven the latest financial year is used and labelled.
- Per-share TTM adds and subtracts reported EPS, which assumes an unchanged
  share count over the period.
- DPS comes from the annual report (income statement or highlights). Many
  issuers print it only in notes, so it is often missing. `05_Dividends` lists
  the CSE cash-dividend announcements in the current disclosure window; they
  are not yet combined into a financial-year DPS.
- Operating profit is taken only from the income statement. Issuers that do not
  print such a row have no operating profit or EBIT proxy.
- Total debt sums borrowings, term and import loans, debentures and bank
  overdrafts on the statement of financial position. Lease liabilities and
  related-party balances are excluded. A statement with no such rows gives no
  debt figure, which is not the same as zero debt.
- The CSE-implied share count is a current figure for one listed class.
  Dual-class issuers (for example RHL.N0000 and RHL.X0000) therefore get book
  value per share only from a reported share count.
- Native text, PyMuPDF table recognition, and page-level Tesseract OCR are wired
  into a layered parser. OCR depends on the optional Python packages and a
  system Tesseract installation; unavailable engines produce review warnings.
- Automatic discovery selects the latest three distinct annual periods and the
  latest interim report per issuer. Errata, prospectuses, trust deeds, articles
  and accountants' reports are excluded; CSE titles with no recognizable period
  are left unmatched rather than guessed.
- The CSE corporate-disclosure feed supplies its current announcement window,
  not a complete historical archive.
- CSE's public market endpoint is operational but undocumented; failures become
  review items rather than silent gaps.
- CSE does not expose a stable public per-security historical-volume endpoint.
  Multi-day liquidity accumulates from official daily snapshots across runs.
  Run the pipeline after each trading day (or on a daily schedule) to build the
  configured 20-day window; the default minimum is five observations.

## Milestone plan

1. Architecture and data contracts (complete).
2. End-to-end pilot for three representative companies (complete).
3. Persistent correction overlay (complete).
4. Automatic document discovery across every constituent of the selected
   industry group (complete).
5. Primary-statement extraction, period-safe metrics with lineage, and the
   reliability gate (complete for the Capital Goods sample; see the first
   limitation above).
6. Next: manual spot-checks recorded as fixtures, half-year and nine-month
   interim filings, financial-year DPS from dividend announcements, and
   statement rows for financial-sector industry groups.

## Neutrality policy

The program does not rank securities, assign a score, select a security, or
produce investment recommendations. Outputs contain raw values, calculated
metrics, sector medians, provenance, and data-quality warnings only.


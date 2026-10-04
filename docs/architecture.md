# Project architecture

## Processing flow

```text
configured universe
        |
document discovery -> document registry -> content-addressed local cache
        |                                      |
        +------------------------------> PDF parsing strategies
                                               |
                        locate primary statements + column layout
                                               |
                                    extraction candidates
                                               |
                      normalization + validation + reconciliation
                                  |                    |
                  facts at or above threshold     manual review
                                  |
              period-safe selection (latest annual, TTM or FY)
                                  |
                      calculations with input lineage
                                  |
                       anomaly and sector comparisons
                                  |
                  Excel + CSV + Markdown + audit records
```

## Modules

- `downloaders`: discover official disclosures, enforce source priority, record
  response metadata, checksum files, and avoid repeat downloads.
- `parsers`: extract text blocks and tables with PyMuPDF first; use alternate
  table strategies and OCR only when the page is demonstrably image-based.
- `extractors`: produce candidates rather than final values. `layout.py` scores
  pages to locate the primary statements, reads the header for scope order,
  year order and extra columns, and tokenises rows. `primary.py` reads metric
  rows from those statements and derives balance-sheet identities.
  `statements.py` combines them with the document-wide label scan (kept as a
  low-confidence fallback), note-level fallbacks and the share count. A
  candidate stores source text, page, scope, period length, unit, confidence
  and extraction method.
- `validators`: `extraction.py` downgrades facts that fail the accounting
  equation or the per-share reconciliations; `flags.py` produces the
  descriptive anomaly flags.
- `calculations`: `screening.py` selects one fact per metric from the latest
  annual report, builds TTM flows where the interim period is proven, and
  calculates every screening metric with its formula, inputs, source pages and
  period basis. `ratios.py` holds the null-safe arithmetic.
- `exporters`: create the eight required screening sheets plus the auditable
  `00_Universe` membership sheet, machine-readable CSVs, Markdown summary, and
  `manual_review.csv`.

## Data contracts

`models.py` defines the boundary objects. Important choices are:

- `Decimal` for financial values; floating point is reserved for presentation.
- Monetary values are normalized to base LKR while `original_value`,
  `original_unit`, and `scale_multiplier` retain the reported representation.
- `PeriodKind` differentiates annual, interim, YTD, quarterly, and TTM records.
- A null `value` is valid and indicates that no reliable number was accepted.
- Every calculated metric cites its input fact IDs; no ratio is orphaned from
  its raw values.

## Period policy

- Balance-sheet figures and the ratios built on them use the latest annual
  report only. An older report never fills a gap in the latest one.
- Income and cash-flow figures are TTM when the latest interim statement proves
  a year-to-date pair of the right length (the header names the period, or the
  cumulative block of a quarter-plus-cumulative page is identified); otherwise
  they are the latest financial year. A bare interim value is never used.
- The annual/YTD bridge is `latest FY + current YTD - matching prior YTD`; every
  input and source page is retained in `03_Ratios` and the output period is
  labelled `TTM to YYYY-MM-DD`. Income and cash-flow bases are decided
  separately and shown in `Income Period Basis` and `Cash Flow Period Basis`.
- Inputs to one ratio cover one period: payout uses FY DPS and FY EPS, and
  OCF / net profit uses profit for the same period as the cash flow.
- Year-on-year growth compares the two columns of the latest annual statement.
  Three-year CAGR chains adjacent reports and is withheld when the latest
  report restated the prior year.
- A financial year that is not twelve months is labelled and excluded from
  growth, TTM and return calculations.
- Cash-dividend declarations come from the official CSE corporate-disclosure
  feed. Declaration DPS remains separate from financial-statement DPS because
  declaration and accounting periods may differ.
- Never combine group and company-only columns.
- Never combine continuing-operations and total-company figures silently.
- Never annualize a partial period unless an output is explicitly marked
  `annualized` and documents the method.
- Growth comparisons require comparable period durations and bases.

## Debt, cash flow, and return policies

- Total debt is the sum of interest-bearing borrowings, term and import loans,
  debentures and bank overdrafts on the statement of financial position. Lease
  liabilities and related-party balances are excluded and the selected
  component rows are retained.
- Capital expenditure is cash paid for purchase/construction of property, plant,
  and equipment. Free cash flow is operating cash flow less absolute capex.
- Net debt is total debt less the cash and cash equivalents row of the statement
  of financial position.
- P/E, P/B, ROE, debt-to-equity and payout are withheld on a zero or negative
  base; the raw negative value is kept.
- ROE uses profit attributable to owners and average equity attributable to
  owners. Total equity is a documented fallback only when attributable equity is
  unavailable. ROA uses annual net profit and average total assets.
- Annual return/cash-flow ratios use facts from the same annual report and are
  not mixed with a newer interim period.

## Extraction validation and review

Each raw fact carries its extraction strategy, validation status, and
validation notes. Every document is tested for unit/column context, for assets
reconciling to liabilities plus equity within 5%, for net profit on a plausible
scale relative to revenue, and for EPS and profit sharing a sign. The latest
annual report is also reconciled per share: EPS against attributable profit and
the CSE share count, share count against profit / EPS and the CSE-implied
count, reported book value per share against parent equity / shares, and DPS
against EPS.

A failed check preserves the extracted value and lowers its confidence. Facts
below `confidence_threshold` are not selected for the screening table; they
stay in `02_Raw_Data` (`Used In Screening = no`) and in the review outputs.

Every warning is emitted with candidate values, source page/text, strategy,
validation rule, and reason to `manual_review.csv` and the line-delimited
`extraction_warnings.jsonl`. Missing metrics and document/network failures use
the same structured schema. This lets automated consumers distinguish absence,
ambiguous extraction, accounting inconsistency, and source failure.

## Source policy

Official CSE disclosures are preferred, followed by official company investor
relations pages. Each document registry record stores discovery URL, direct
download URL, publication date, retrieval timestamp, checksum, and local path.
Educational reference PDFs inform methodology only and cannot supply issuer
facts.

The financial archive is queried over a rolling three-year window. Discovery
matches the base issuer symbol (so voting and non-voting securities share issuer
filings), excludes known non-statement document types, parses the disclosed
period from the title, and selects the newest annual and interim statement.
Configured documents are fallbacks. Archive responses have a 15-minute cache;
PDF bytes and page-preserving extracted text are cached persistently.

## Manual corrections

`config/corrections.yml` is an append-only YAML overlay keyed by ticker, metric,
period, and source document. Each correction includes value, reported unit,
statement scope, source page/text, reason, author, and date. Values are normalized
through the same unit module as extracted facts. Exact targeting is mandatory;
an unmatched active entry fails the selected-company run.

Original extracted candidates remain in `02_Raw_Data`. An applied correction is
a separate confidence-1.0 fact with a unique correction ID, and accepted-fact and
ratio lineage point to that ID. Replaced entries are retained with
`status: superseded`; duplicate active targets and duplicate IDs are rejected.


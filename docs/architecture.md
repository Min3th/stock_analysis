# Project architecture

## Processing flow

```text
configured universe
        |
document discovery -> document registry -> content-addressed local cache
        |                                      |
        +------------------------------> PDF parsing strategies
                                               |
                                    extraction candidates
                                               |
                             normalization + validation
                                  |                    |
                           accepted raw values    manual review
                                  |
                         period-aware calculations
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
- `extractors`: produce candidates rather than final values. A candidate stores
  source text, page, label match, column/period match, unit, and confidence.
- `validators`: reject or downgrade ambiguous periods, inconsistent units,
  duplicate facts, and accounting relationships outside stated tolerances.
- `calculations`: operate only on normalized accepted facts and preserve a list
  of input fact identifiers, formula text, period basis, and calculation notes.
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

- Prefer TTM only when four non-overlapping quarterly periods, or compatible
  annual plus comparable YTD periods, can be demonstrated.
- The annual/YTD bridge is `latest FY + current YTD - matching prior YTD`; every
  input and source page is retained in `03_Ratios` and the output period is
  labelled `TTM ended YYYY-MM-DD`.
- Cash-dividend declarations come from the official CSE corporate-disclosure
  feed. Declaration DPS remains separate from financial-statement DPS because
  declaration and accounting periods may differ.
- Never combine group and company-only columns.
- Never combine continuing-operations and total-company figures silently.
- Never annualize a partial period unless an output is explicitly marked
  `annualized` and documents the method.
- Growth comparisons require comparable period durations and bases.

## Debt, cash flow, and return policies

- Total debt is the sum of non-current borrowings, the current portion of
  long-term borrowings, and short-term interest-bearing borrowings. Lease
  liabilities are excluded and the selected component rows are retained.
- Capital expenditure is cash paid for purchase/construction of property, plant,
  and equipment. Free cash flow is operating cash flow less absolute capex.
- Net debt is total debt less cash and cash equivalents. When the report defines
  equivalents as cash at bank plus short-term deposits, both cited rows are used.
- ROE uses profit attributable to owners and average equity attributable to
  owners. Total equity is a documented fallback only when attributable equity is
  unavailable. ROA uses annual net profit and average total assets.
- Annual return/cash-flow ratios use facts from the same annual report and are
  not mixed with a newer interim period.

## Extraction validation and review

Each accepted raw fact carries its extraction strategy, validation status, and
validation notes. Document-level validators currently test whether unit/column
context supports high confidence, whether assets reconcile to liabilities plus
equity within 5%, and whether net profit is on a plausible scale relative to
revenue. Validation warnings preserve the extracted value but reduce confidence.

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


# Initial technical risk register

| Risk | Impact | Initial control |
|---|---|---|
| CSE pages or endpoints change | Discovery fails across the universe | Isolate site adapters; retain fixture-based tests and company IR fallback |
| PDFs use inconsistent labels/layouts | Wrong row or column selected | Multi-strategy candidates, explicit period matching, confidence threshold, manual review |
| Scanned or mixed PDFs | Missing text/tables | Detect low-text pages and apply page-level OCR only as fallback |
| Units vary by page or statement | Values off by 1,000 or 1,000,000 | Page/table unit detection, retain original unit, accounting cross-checks |
| Consolidated and company columns coexist | Incomparable facts | Capture statement scope and prefer consolidated group consistently |
| Restated comparatives differ from old reports | Duplicate/conflicting history | Prefer newest audited restatement, retain both candidates and provenance |
| Fiscal years and interim durations differ | Misleading growth or TTM | Duration-aware period model; refuse incompatible comparisons |
| EPS/share counts change after splits/issues | Historical ratios distorted | Prefer reported EPS; record basic/diluted and restatement status |
| Capex presentation varies | FCF is inconsistent | Define capex policy explicitly and retain selected cash-flow line inputs |
| Dividend announcement vs accounting DPS | Double counting or timing errors | Separate declared, paid, and period-attributable dividends |
| Market price timestamp differs from statements | Valuation ratios become stale | Timestamp price and label financial denominator period |
| Thin trading distorts latest price/liquidity | Misleading valuations | Record last trade date plus configurable rolling liquidity measure |
| Anti-bot/rate limits | Incomplete downloads | Polite pacing, retries, caching, and resumable document registry |
| One-off gains/losses are narrative | False sustainable-profit impression | Keyword candidates from notes, manual-review flag, never auto-adjust earnings |
| Sector membership changes | Wrong universe | Date-stamped configurable universe with official classification provenance |

## Scale-up gate

Expansion beyond the initial 2–3 companies should occur only after fixtures
cover a conventional digital report, a difficult table layout, and a scanned or
otherwise irregular report. Required checks include statement equation
validation, correct comparative-year columns, unit normalization, output
lineage, and deterministic reruns from cache.


### Status of the gate

Fixtures live in `tests/fixtures/<TICKER>/<document>/` as `pages.json` (the located
statement pages, keyed by the report's own page number) and `expected.yml` (the
printed figures with their pages), checked by `tests/test_fixture_regression.py`:

| Layout | Fixture |
| --- | --- |
| Conventional digital report | EBCR.N0000 annual report 2026 |
| Difficult tables | ASHO.N0000 (table-parsed, single column pair), DOCK.N0000 (wrapped labels, restated comparatives, a loss year) |
| Scanned / OCR | SDB.N0000 audited statements 2024: the OCR'd cash-flow page only |
| Bank | SEYB.N0000 annual report 2025 |

Limits of this evidence, stated plainly:

- The recorded figures were transcribed from the saved page text of each
  statement and checked for internal consistency (assets = liabilities + equity
  where all three print); they were not re-read from a rendered image of the PDF
  by a second person.
- No Capital Goods report in the cache has OCR'd statement pages. The OCR
  fixture is therefore a bank's cash-flow statement, and a fully scanned
  Capital Goods report is still an open gap.
- `tests/test_pipeline_e2e.py` runs `pipeline.run(offline=True)` on a fixture
  cache and checks the output files, manifest, lineage and a byte-identical rerun.

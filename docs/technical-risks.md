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


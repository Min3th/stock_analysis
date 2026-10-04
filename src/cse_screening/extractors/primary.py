"""Row extraction from the located primary financial statements."""

from __future__ import annotations

import re
from decimal import Decimal

from .layout import (
    ColumnLayout,
    clean_lines,
    column_layout,
    consensus_unit,
    header_lines,
    page_unit,
    select_columns,
    strip_note_reference,
    trailing_values,
)

PER_SHARE_METRICS = {"eps", "bvps", "dps"}
CONTINUING = re.compile(r"\b(?:continuing|discontinued)\b", re.IGNORECASE)

# metric -> (statement kind, label patterns). Patterns are tried in order and a
# row from an earlier pattern is preferred over one from a later pattern.
PRIMARY_ROWS: dict[str, tuple[str, tuple[str, ...]]] = {
    "revenue": (
        "income",
        (
            r"^total revenue\b",
            r"^(?:gross |net )?revenue\b(?! reserves?| taxes?)",
            r"^revenue from contracts? with customers\b",
            r"^(?:gross |net )?turnover\b",
        ),
    ),
    "operating_profit": (
        "income",
        (
            r"^operating (?:profit|\(?loss\)?)(?!.*before working capital)",
            r"^profit\s*/?\s*\(?(?:loss)?\)?\s*from operati(?:ons|ng activities)\b",
            r"^results from operating activities\b",
        ),
    ),
    "ebit": (
        "income",
        (
            r"^earnings before interest (?:and|&) tax(?:\s*\(ebit\))?\b",
            r"^profit before interest (?:and|&) tax\b",
        ),
    ),
    "net_profit": (
        "income",
        (
            r"^(?:net )?profit\s*/?\s*\(?(?:loss)?\)?\s*(?:after tax )?for the (?:year|period)\b",
            r"^\(?loss\)?\s*/?\s*(?:\(?profit\)?)?\s*for the (?:year|period)\b",
        ),
    ),
    "eps": (
        "income",
        (
            r"^basic\b[\w\s/&,()-]{0,30}?(?:earnings|loss)[\s/()a-z]{0,20}per (?:ordinary )?share",
            r"^(?:earnings|\(?loss\)?)[\s/()a-z]{0,20}per (?:ordinary )?share",
        ),
    ),
    "dps": ("income", (r"^dividends? per (?:ordinary )?share\b",)),
    "total_assets": ("position", (r"^total assets\b",)),
    "total_liabilities": ("position", (r"^total liabilities\b",)),
    "total_equity": (
        "position",
        (r"^total equity\b(?!\s*(?:and|&)\s*liabilities)(?! attributable)",),
    ),
    "ordinary_equity": (
        "position",
        (
            r"^(?:total )?equity attributable to\b",
            r"^shareholders'? funds?\b",
        ),
    ),
    "bvps": (
        "position",
        (r"^net assets?(?: value)? per (?:ordinary )?share\b", r"^book value per share\b"),
    ),
    "cash": (
        "position",
        (
            r"^cash (?:and|&) cash equivalents?\b",
            r"^cash and short[- ]term deposits\b",
            r"^cash in hand and at bank\b",
            r"^cash and balances with banks\b",
            r"^(?:cash and bank|bank (?:and|&) cash) balances\b",
        ),
    ),
    "retained_earnings": (
        "position",
        (
            r"^retained (?:earnings|profits?)\b",
            r"^\(?accumulated loss(?:es)?\)?\s*/?\s*(?:retained earnings)?",
            r"^revenue reserves?\b",
        ),
    ),
    "operating_cash_flow": (
        "cash_flow",
        (r"^net cash\b[^0-9]*\boperating activities\b(?!.*\bbefore\b)",),
    ),
    "capital_expenditure": (
        "cash_flow",
        (
            (
                r"^(?:purchase|acquisition|addition)s?\s*(?:(?:and|&) construction\s*)?(?:of|to)\s*"
                r"property,?\s*plant\s*(?:and|&)\s*equipments?"
            ),
            r"^investment in property,?\s*plant\s*(?:and|&)\s*equipments?",
        ),
    ),
}
ATTRIBUTABLE_ROW = re.compile(
    r"^(?:-\s*)?(?:equity holders?|owners|shareholders|equity shareholders) of (?:the )?"
    r"(?:parent|company)\b",
    re.IGNORECASE,
)
NON_CONTROLLING_ROW = re.compile(r"^non\s*-?\s*controlling interests?\b|^minority", re.IGNORECASE)
DEBT_ROW = re.compile(
    r"^(?:(?:current|non[- ]current) portion of |short[- ]term |long[- ]term )*"
    r"(?:interest[- ]bearing (?:loans (?:and|&) )?(?:borrowings|liabilities)|"
    r"loans (?:and|&) borrowings|borrowings|term loans|import (?:demand )?loans|"
    r"bank overdrafts?|due to banks|debentures?)\b",
    re.IGNORECASE,
)
DEBT_EXCLUSION = re.compile(r"receivable|related part|advances|lease", re.IGNORECASE)
YEAR_TO_DATE = 0  # "period ended <date>": cumulative from the start of the financial year
PERIOD_PHRASES = (
    (YEAR_TO_DATE, r"period ended"),
    (3, r"(?:quarter|three months?|0?3 months?)"),
    (6, r"(?:six months?|0?6 months?|half[- ]year)"),
    (9, r"(?:nine months?|0?9 months?)"),
    (12, r"(?:twelve months?|12 months?|year ended)"),
)


def interim_period_blocks(text: str) -> list[int]:
    """Durations named in an interim statement header, in column order."""
    header = " ".join(header_lines(text))
    found = []
    for months, pattern in PERIOD_PHRASES:
        for match in re.finditer(rf"\b{pattern}\b", header, re.IGNORECASE):
            found.append((match.start(), months))
    ordered = [months for _, months in sorted(found)]
    return [
        value for index, value in enumerate(ordered) if index == 0 or ordered[index - 1] != value
    ]


WRAP_CONNECTOR = re.compile(
    r"(?:\b(?:of|and|in|from|to|on|for|the|operating|other|through|using|plant)|[,/&(-])$",
    re.IGNORECASE,
)


HEADING_END = re.compile(r"(?:attributable to|as follows|:)\s*$", re.IGNORECASE)


def _label(line: str) -> str:
    """Row text in front of its amount cells."""
    cells = trailing_values(line).tokens
    if not cells:
        return line
    tokens = line.replace("|", " ").split()
    for start in range(len(tokens) - len(cells) + 1):
        if tokens[start : start + len(cells)] == cells:
            return " ".join(tokens[:start])
    return line


def _logical_rows(lines: list[str]) -> list[tuple[str, str]]:
    """Return (label, source text) rows, rejoining labels wrapped across lines."""
    rows = []
    physical = [line for line in lines if "|" not in line]
    index = 0
    while index < len(physical):
        line = physical[index]
        following = physical[index + 1] if index + 1 < len(physical) else ""
        has_cells = bool(trailing_values(line).tokens)
        next_has_cells = bool(trailing_values(following).tokens)
        if (
            not has_cells
            and next_has_cells
            and (following[:1].islower() or WRAP_CONNECTOR.search(line))
            and not HEADING_END.search(line)
        ):
            joined = f"{line} {following}"
            rows.append((f"{line} {_label(following)}", joined))
            index += 2
            continue
        if (
            has_cells
            and following
            and not next_has_cells
            and following[:1].islower()
            and len(following.split()) <= 3
        ):
            rows.append((f"{_label(line)} {following}", line))
            index += 2
            continue
        rows.append((_label(line), line))
        index += 1
    return rows


DATE_RANGE = re.compile(
    r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\s*(?:to|-|–)\s*(?:\S+\s+){0,4}?"
    r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})",
    re.IGNORECASE,
)


def reporting_period_months(text: str) -> int | None:
    """Length of the current reporting period when the header gives a date range.

    A change of financial year-end produces statements for more or fewer than
    twelve months; those flows must not be compared with a twelve-month year.
    """
    lines = header_lines(text)
    date = r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})"
    for index, line in enumerate(lines[:-1]):
        # Stacked header: a row of "<start> to" above a row of period ends.
        start = re.search(rf"{date}\s*to\b", line, re.IGNORECASE)
        end = re.search(date, lines[index + 1])
        if start and end and line.rstrip().casefold().endswith("to"):
            first = (int(start.group(2)), int(start.group(3)))
            last = (int(end.group(2)), int(end.group(3)))
            break
    else:
        match = DATE_RANGE.search(" ".join(lines))
        if not match:
            return None
        first = (int(match.group(2)), int(match.group(3)))
        last = (int(match.group(5)), int(match.group(6)))
    months = (last[1] - first[1]) * 12 + last[0] - first[0] + 1
    return months if 1 <= months <= 24 else None


class StatementPage:
    def __init__(
        self,
        number: int,
        text: str,
        fallback_unit: tuple[str, Decimal] | None,
        interim: bool = False,
    ) -> None:
        self.number = number
        self.lines = clean_lines(text)
        self.layout: ColumnLayout = column_layout(text)
        explicit = page_unit(text)
        self.unit = explicit or fallback_unit
        self.unit_explicit = explicit is not None
        self.rows = _logical_rows(self.lines)
        self.periods = interim_period_blocks(text) if interim else []
        self.period_months: int | None = None
        self.block: int | None = None
        blocks = len(self.layout.block_starts)
        if not interim:
            self.period_months = reporting_period_months(text)
        elif not self.periods:
            pass
        elif len(set(self.periods)) == 1:
            self.period_months = self.periods[0]
        elif "group" in self.layout.scopes:
            # Blocks are Group and Company, so every column is the same period.
            # A "period ended" title above explicit "three months" columns names
            # that one period twice; anything else is ambiguous.
            named = set(self.periods) - {YEAR_TO_DATE}
            if len(named) == 1:
                self.period_months = named.pop()
        elif blocks == 1:
            # One current/prior pair leads the row; it is the first period named.
            if self.periods[0] <= 11:
                self.period_months = self.periods[0]
        elif len(self.periods) == blocks:
            # Blocks are periods: read the cumulative one (the year to date).
            cumulative = [months for months in self.periods if months <= 11]
            if YEAR_TO_DATE in cumulative:
                self.period_months = YEAR_TO_DATE
            elif cumulative:
                self.period_months = max(cumulative)
            if self.period_months is not None:
                self.block = self.periods.index(self.period_months)

    def read(self, row_text: str):
        row = strip_note_reference(trailing_values(row_text), self.layout.cell_counts() or None)
        current, previous, scope, basis = select_columns(row, self.layout, self.block)
        return row, current, previous, scope, basis


def _confidence(page: StatementPage, basis: str, per_share: bool) -> Decimal:
    if basis == "ambiguous":
        return Decimal("0.60")
    confidence = Decimal("0.90") if basis == "confirmed" else Decimal("0.85")
    if per_share:
        return confidence
    if page.unit is None:
        return Decimal("0.62")
    return confidence if page.unit_explicit else confidence - Decimal("0.02")


def _candidate(
    metric: str,
    page: StatementPage,
    source_text: str,
    current: Decimal,
    previous: Decimal | None,
    scope: str,
    basis: str,
    statement: str,
) -> dict:
    per_share = metric in PER_SHARE_METRICS
    multiplier = Decimal(1) if per_share or page.unit is None else page.unit[1]
    notes = [f"Read from the primary {statement.replace('_', ' ')} statement"]
    notes.append(f"{scope} column block ({basis} against the page header)")
    if not per_share and page.unit is not None and not page.unit_explicit:
        notes.append("unit taken from the other primary statements because this page states none")
    return {
        "metric": metric,
        "value": current * multiplier,
        "original_value": current,
        "unit": "LKR/share" if per_share else "LKR",
        "original_unit": "LKR/share" if per_share else (page.unit[0] if page.unit else "unknown"),
        "multiplier": multiplier,
        "page": page.number,
        "source_text": source_text,
        "confidence": _confidence(page, basis, per_share),
        "comparatives": [value for value in (current, previous) if value is not None],
        "previous_value": previous * multiplier if previous is not None else None,
        "statement_scope": scope,
        "extraction_method": f"primary_{statement}_row",
        "period_months": page.period_months,
        "notes": "; ".join(notes) + ".",
    }


def extract_primary_metrics(
    pages: list[str], located: dict[str, list[int]], interim: bool = False
) -> list[dict]:
    """Extract metrics from the located primary statements only."""
    every_page = sorted({number for numbers in located.values() for number in numbers})
    fallback_unit = consensus_unit(pages, every_page)
    statements = {
        kind: [
            StatementPage(number, pages[number - 1], fallback_unit, interim)
            for number in sorted(numbers)
        ]
        for kind, numbers in located.items()
    }
    results: dict[str, dict] = {}
    for metric, (kind, patterns) in PRIMARY_ROWS.items():
        found = _find_row(statements.get(kind, []), patterns)
        if found is None:
            continue
        page, text, current, previous, scope, basis = found
        results[metric] = _candidate(metric, page, text, current, previous, scope, basis, kind)

    if "eps" not in results:
        headed = _eps_under_heading(statements.get("income", []))
        if headed is not None:
            results["eps"] = headed
    attributable = _attributable_profit(statements.get("income", []), results.get("net_profit"))
    if attributable is not None:
        results["net_profit_attributable"] = attributable
    _derive_balance_sheet_identities(results, statements.get("position", []))
    debt = _total_debt(statements.get("position", []))
    if debt is not None:
        results["total_debt"] = debt
    return list(results.values())


def _find_row(pages: list[StatementPage], patterns: tuple[str, ...]):
    for pattern in patterns:
        matches = []
        for page in pages:
            for label_text, source in page.rows:
                if not re.search(pattern, label_text, re.IGNORECASE):
                    continue
                row, current, previous, scope, basis = page.read(source)
                if current is None or len(row.tokens) < 2:
                    continue
                matches.append((page, source, current, previous, scope, basis))
        if matches:
            totals = [item for item in matches if not CONTINUING.search(item[1])]
            return (totals or matches)[0]
    return None


EPS_HEADING = re.compile(
    r"^(?:earnings|\(?loss\)?)[\s/()a-z]{0,20}per (?:ordinary )?share\b", re.IGNORECASE
)


def _eps_under_heading(pages: list[StatementPage]) -> dict | None:
    """Basic EPS printed as a "Basic" row beneath an earnings-per-share heading."""
    for page in pages:
        heading_at = None
        for index, (label_text, source) in enumerate(page.rows):
            if EPS_HEADING.search(label_text) and not trailing_values(source).tokens:
                heading_at = index
                continue
            if heading_at is None or index - heading_at > 4:
                continue
            if not re.match(r"^(?:-\s*)?basic\b", label_text, re.IGNORECASE):
                continue
            _, current, previous, scope, basis = page.read(source)
            if current is None:
                continue
            heading = page.rows[heading_at][1]
            return _candidate(
                "eps", page, f"{heading} | {source}", current, previous, scope, basis, "income"
            )
    return None


def _attributable_profit(pages: list[StatementPage], net_profit: dict | None) -> dict | None:
    """Parent-attributable profit row that follows the profit-for-the-year row.

    Combined statements repeat the attribution for total comprehensive income;
    rows under a comprehensive-income total or heading are not accepted.
    """
    if net_profit is None:
        return None
    passed_profit = False
    last_total = "profit"
    heading = ""
    for page in pages:
        for label_text, source in page.rows:
            if not passed_profit:
                passed_profit = (
                    page.number == net_profit["page"] and source == net_profit["source_text"]
                )
                continue
            lowered = label_text.casefold()
            if "attributable to" in lowered and not ATTRIBUTABLE_ROW.search(label_text):
                heading = lowered
                continue
            if lowered.startswith(("total comprehensive", "other comprehensive")):
                last_total = "comprehensive"
                heading = ""
                continue
            if re.match(PRIMARY_ROWS["net_profit"][1][0], label_text, re.IGNORECASE):
                last_total = "profit"
                continue
            if not ATTRIBUTABLE_ROW.search(label_text):
                continue
            if "comprehensive" in heading or (last_total != "profit" and "profit" not in heading):
                continue
            _row, current, previous, scope, basis = page.read(source)
            if current is None:
                continue
            return _candidate(
                "net_profit_attributable", page, source, current, previous, scope, basis, "income"
            )
    return None


def _derive_balance_sheet_identities(results: dict[str, dict], pages: list[StatementPage]) -> None:
    assets, equity = results.get("total_assets"), results.get("total_equity")
    if "total_liabilities" not in results and assets and equity:
        previous = (
            assets["previous_value"] - equity["previous_value"]
            if assets.get("previous_value") is not None and equity.get("previous_value") is not None
            else None
        )
        value = assets["value"] - equity["value"]
        results["total_liabilities"] = {
            **assets,
            "metric": "total_liabilities",
            "value": value,
            "original_value": value,
            "original_unit": "LKR",
            "multiplier": Decimal(1),
            "comparatives": [item for item in (value, previous) if item is not None],
            "previous_value": previous,
            "source_text": f"{assets['source_text']} | {equity['source_text']}",
            "confidence": min(assets["confidence"], equity["confidence"]),
            "extraction_method": "derived_total_assets_less_total_equity",
            "notes": (
                "Derived as total assets less total equity because the statement prints no "
                "total-liabilities row."
            ),
        }
    minority = None
    for page in pages:
        for label, source in page.rows:
            if NON_CONTROLLING_ROW.search(label):
                _, current, previous, _, _ = page.read(source)
                if current is not None:
                    minority = (page, source, current, previous)
                    break
        if minority:
            break
    ordinary = results.get("ordinary_equity")
    if ordinary is None and equity and minority is None:
        results["ordinary_equity"] = {
            **equity,
            "metric": "ordinary_equity",
            "extraction_method": "total_equity_without_non_controlling_interest",
            "notes": (
                "Total equity used as equity attributable to ordinary shareholders: the "
                "statement shows no non-controlling interest."
            ),
        }
    elif ordinary is None and equity and minority is not None:
        page, source, current, previous = minority
        multiplier = page.unit[1] if page.unit else Decimal(1)
        value = equity["value"] - current * multiplier
        prior = (
            equity["previous_value"] - previous * multiplier
            if equity.get("previous_value") is not None and previous is not None
            else None
        )
        results["ordinary_equity"] = {
            **equity,
            "metric": "ordinary_equity",
            "value": value,
            "original_value": value,
            "original_unit": "LKR",
            "multiplier": Decimal(1),
            "comparatives": [item for item in (value, prior) if item is not None],
            "previous_value": prior,
            "source_text": f"{equity['source_text']} | {source}",
            "extraction_method": "derived_total_equity_less_non_controlling_interest",
            "notes": (
                "Derived as total equity less non-controlling interests because the statement "
                "prints no labelled parent-equity subtotal."
            ),
        }
    elif equity is None and ordinary is not None and minority is None:
        results["total_equity"] = {
            **ordinary,
            "metric": "total_equity",
            "extraction_method": "parent_equity_without_non_controlling_interest",
            "notes": (
                "Equity attributable to owners used as total equity: the statement shows no "
                "non-controlling interest and no separate total-equity row."
            ),
        }
        _derive_balance_sheet_identities(results, pages)


def _total_debt(pages: list[StatementPage]) -> dict | None:
    components = []
    for page in pages:
        for label_text, source in page.rows:
            if not DEBT_ROW.search(label_text) or DEBT_EXCLUSION.search(label_text):
                continue
            _row, current, previous, _scope, basis = page.read(source)
            if current is None and previous is None:
                continue
            components.append((page, source, current or Decimal(0), previous or Decimal(0), basis))
    if not components:
        return None
    page = components[0][0]
    multiplier = page.unit[1] if page.unit else Decimal(1)
    current = sum(item[2] for item in components) * multiplier
    previous = sum(item[3] for item in components) * multiplier
    bases = {item[4] for item in components}
    if "ambiguous" in bases:
        basis = "ambiguous"
    else:
        basis = "confirmed" if bases == {"confirmed"} else "assumed"
    return {
        "metric": "total_debt",
        "value": current,
        "original_value": current,
        "unit": "LKR",
        "original_unit": page.unit[0] if page.unit else "unknown",
        "multiplier": Decimal(1),
        "page": page.number,
        "source_text": " | ".join(item[1] for item in components),
        "confidence": min(_confidence(page, basis, False), Decimal("0.88")),
        "comparatives": [current, previous],
        "previous_value": previous,
        "statement_scope": "group" if "group" in page.layout.scopes else "primary",
        "extraction_method": "debt_component_aggregation",
        "notes": (
            "Sum of interest-bearing borrowings, term and import loans, debentures and bank "
            "overdrafts on the statement of financial position; lease liabilities and "
            "related-party balances excluded."
        ),
    }

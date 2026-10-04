"""Primary-statement location, column layout, and row tokenisation.

Annual reports repeat the same row labels in highlights, segment notes,
multi-year summaries and foreign-currency translations. Taking the first
matching label therefore mixes scopes and units. This module finds the primary
income statement, statement of financial position and cash-flow statement, and
describes how their value columns are arranged so the caller can read the
consolidated current-year column deliberately rather than by position alone.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from ..units import detect_unit, parse_number

# Amount cells: balanced parentheses mark negatives; a footnote asterisk may trail.
NUMERIC_TOKEN = re.compile(r"^(?:\(-?\d[\d,]*(?:\.\d+)?\)|-?\d[\d,]*(?:\.\d+)?)%?\*{0,2}$")
CURRENCY_TOKEN = re.compile(r"^(?:rs\.?|lkr)$", re.IGNORECASE)
NIL_TOKENS = {"-", "–", "—", "nil", "Nil", "NIL"}
NOTE_TOKEN = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,2}$")

STATEMENT_ROWS: dict[str, tuple[str, ...]] = {
    "income": (
        r"^(?:total |gross |net )?(?:revenue|turnover)\b(?! reserves?)",
        r"^cost of (?:sales|revenue)\b",
        r"^gross profit\b",
        r"^profit\s*/?\s*\(?(?:loss)?\)?\s*before (?:income )?tax",
        r"^(?:income )?tax(?:ation)?(?: expenses?| reversal| charge)?\b",
        r"^profit\s*/?\s*\(?(?:loss)?\)?\s*for the (?:year|period)\b",
        r"earnings\s*/?\s*\(?(?:loss)?\)?\s*per share",
        r"^(?:net )?(?:finance|interest) (?:costs?|expenses?|income)\b",
        r"^other (?:operating )?income\b",
        r"^administrative (?:expenses|costs)\b",
        r"^(?:selling and )?distribution (?:expenses|costs)\b",
    ),
    "position": (
        r"^total assets\b",
        r"^total equity\b",
        r"^total liabilities\b",
        r"^total equity and liabilities\b",
        r"^total non[- ]current assets\b",
        r"^total current assets\b",
        r"^stated capital\b",
        r"^retained (?:earnings|profits?)\b",
        r"^total current liabilities\b",
        r"^inventories\b",
        r"^property,? plant (?:and|&) equipment\b",
        r"^trade and other (?:receivables|payables)\b",
    ),
    "cash_flow": (
        r"operating activities",
        r"investing activities",
        r"financing activities",
        r"^cash and cash equivalents at (?:the )?(?:end|beginning)",
        r"^(?:purchase|acquisition)s? (?:and construction )?of property",
        r"^net (?:increase|decrease)",
        r"^(?:depreciation|interest paid|dividends? paid|income tax(?:es)? paid)",
    ),
}
STATEMENT_TITLES: dict[str, tuple[str, ...]] = {
    "income": (
        "statement of profit or loss",
        "income statement",
        "statement of comprehensive income",
        "statement of income",
    ),
    "position": ("statement of financial position", "balance sheet"),
    "cash_flow": ("statement of cash flows", "cash flow statement", "statement of cash flow"),
}
MINIMUM_SCORE = {"income": 5, "position": 5, "cash_flow": 4}
FOREIGN_CURRENCY = re.compile(
    r"(?:US\s?\$|\bUSD\b|\bUS dollars?\b|convenience translation)", re.IGNORECASE
)
SCOPE_GROUP = re.compile(r"\b(?:group|consolidated)", re.IGNORECASE)
SCOPE_COMPANY = re.compile(r"\bcompany", re.IGNORECASE)
# Column-header years; report-title ranges such as 2025/26 or 2025-2026 are excluded.
HEADER_YEAR = re.compile(r"(?<![/\-\d])(20\d{2})(?![/\-\d])")


def normalize_text(text: str) -> str:
    """Fold PDF ligatures and typographic quotes so labels and units match."""
    folded = unicodedata.normalize("NFKC", text)
    return folded.replace("‘", "'").replace("’", "'").replace("`", "'")


def clean_lines(text: str) -> list[str]:
    return [" ".join(line.split()) for line in normalize_text(text).splitlines() if line.strip()]


@dataclass(frozen=True)
class RowValues:
    values: list[Decimal | None]
    note_reference: str | None
    tokens: list[str]


def trailing_values(line: str) -> RowValues:
    """Return the amount cells of a statement row.

    The cells are the longest run of consecutive numeric or nil tokens, which is
    the value columns even when a neighbouring text column bleeds onto the end
    of the line. Nil dashes are kept as ``None`` so later columns do not shift.
    """
    # A currency marker repeated in front of each amount ("Rs. 1.46 Rs. 1.86")
    # is not a column break.
    tokens = [token for token in line.replace("|", " ").split() if not CURRENCY_TOKEN.match(token)]
    runs: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in NIL_TOKENS or NUMERIC_TOKEN.match(token):
            current.append(token)
            continue
        if current:
            runs.append(current)
        current = []
    if current:
        runs.append(current)
    # A run of dashes is a row of empty cells only when it ends the line; a
    # single dash elsewhere is punctuation.
    ends_with_nil_cells = bool(current) and len(current) >= 2
    runs = [
        run
        for position, run in enumerate(runs)
        if any(token not in NIL_TOKENS for token in run)
        or (ends_with_nil_cells and position == len(runs) - 1)
    ]
    run: list[str] = []
    for candidate in runs:
        if len(candidate) >= len(run):
            run = candidate
    return RowValues(
        values=[None if token in NIL_TOKENS else parse_number(token.rstrip("*")) for token in run],
        note_reference=None,
        tokens=run,
    )


def _decimal_places(token: str) -> int:
    digits = token.strip("()*%")
    return len(digits.split(".")[1]) if "." in digits else 0


def _is_note_token(token: str) -> bool:
    return bool(NOTE_TOKEN.match(token)) and Decimal(token.split(".")[0]) <= 99


def strip_note_reference(row: RowValues, expected: int | set[int] | None) -> RowValues:
    """Drop a leading note number (or label dash) that is not an amount cell.

    ``expected`` is the cell count (or the acceptable counts) the page header
    implies, or ``None`` when the layout is unknown.
    """
    tokens, values = row.tokens, row.values
    if len(tokens) < 2:
        return row
    counts = {expected} if isinstance(expected, int) else set(expected or ())
    largest = max(counts) if counts else None
    if largest is not None and len(tokens) > largest + 1:
        # Numbers that end the label precede the value columns.
        keep = largest + (1 if _is_note_token(tokens[-largest - 1]) else 0)
        tokens, values = tokens[-keep:], values[-keep:]
    if tokens[0] in NIL_TOKENS:
        if counts and len(tokens) - 1 in counts and len(tokens) not in counts:
            return RowValues(values=values[1:], note_reference=None, tokens=tokens[1:])
        return RowValues(values=values, note_reference=None, tokens=tokens)
    if not _is_note_token(tokens[0]):
        return RowValues(values=values, note_reference=None, tokens=tokens)
    rest = [token for token in tokens[1:] if token not in NIL_TOKENS]
    integer_token = "." not in tokens[0]
    # Per-share rows print every amount to the same precision, so a leading
    # token with fewer decimal places ("11", "10.1" before "2.98 2.70") is a note.
    precision = {_decimal_places(token) for token in rest}
    integer_before_decimals = (
        bool(rest) and len(precision) == 1 and _decimal_places(tokens[0]) < min(precision)
    )
    following = next((value for value in values[1:] if value is not None), None)
    first = values[0]
    # "5.1" in front of 49,660,591 is a note; "34.87" in front of 29.90 is data.
    larger = (
        following is not None
        and first is not None
        and abs(following) > max(abs(first) * 3, Decimal(200))
    )
    odd_count = len(tokens) % 2 == 1 and (integer_token or larger)
    if counts:
        if len(tokens) in counts and not integer_before_decimals:
            return RowValues(values=values, note_reference=None, tokens=tokens)
        extra_cell = len(tokens) - 1 in counts
        odd_partial = len(tokens) % 2 == 1 and len(tokens) < min(counts)
        if not (extra_cell or odd_partial or integer_before_decimals):
            return RowValues(values=values, note_reference=None, tokens=tokens)
    elif not (larger or odd_count or integer_before_decimals):
        return RowValues(values=values, note_reference=None, tokens=tokens)
    return RowValues(values=values[1:], note_reference=tokens[0], tokens=tokens[1:])


def _row_matches(lines: list[str], patterns: tuple[str, ...]) -> tuple[int, list[int]]:
    hits: set[int] = set()
    counts: list[int] = []
    for line in lines:
        if "|" in line:
            continue
        for index, pattern in enumerate(patterns):
            if index in hits or not re.search(pattern, line, re.IGNORECASE):
                continue
            cells = len(trailing_values(line).tokens)
            if cells >= 2:
                hits.add(index)
                counts.append(cells)
    return len(hits), counts


def statement_scores(text: str) -> dict[str, int]:
    """Score how strongly a page resembles each primary statement."""
    lines = clean_lines(text)
    head = " ".join(lines[:12]).casefold()
    scores: dict[str, int] = {}
    for kind, patterns in STATEMENT_ROWS.items():
        matched, counts = _row_matches(lines, patterns)
        score = matched
        if any(title in head for title in STATEMENT_TITLES[kind]):
            score += 3
        # Multi-year summaries and segment tables carry many columns per row.
        if counts and sorted(counts)[len(counts) // 2] > 6:
            score -= 6
        if FOREIGN_CURRENCY.search(" ".join(lines[:15])):
            score -= 6
        scores[kind] = score
    return scores


def locate_statements(pages: list[str]) -> dict[str, list[int]]:
    """Return 1-based page numbers of each primary statement, best page first.

    The three statements are printed together, so the chosen pages maximise the
    combined score of an income statement with a nearby position and cash-flow
    statement. Continuation pages are appended after the best page.
    """
    scores = [statement_scores(page) for page in pages]
    count = len(pages)

    def best(kind: str, start: int, stop: int) -> tuple[int, int] | None:
        candidates = [
            (scores[index][kind], -index)
            for index in range(max(0, start), min(count, stop))
            if scores[index][kind] >= MINIMUM_SCORE[kind]
        ]
        if not candidates:
            return None
        score, negative_index = max(candidates)
        return score, -negative_index

    clusters = []
    for index in range(count):
        if scores[index]["income"] < MINIMUM_SCORE["income"]:
            continue
        position = best("position", index - 4, index + 8)
        cash_flow = best("cash_flow", index - 2, index + 14)
        total = (
            scores[index]["income"]
            + (position[0] if position else 0)
            + (cash_flow[0] if cash_flow else 0)
        )
        clusters.append((total, -index, position, cash_flow))
    located: dict[str, list[int]] = {}
    if clusters:
        _, negative_index, position, cash_flow = max(clusters)
        anchors = {
            "income": -negative_index,
            "position": position[1] if position else None,
            "cash_flow": cash_flow[1] if cash_flow else None,
        }
    else:
        anchors = {}
        for kind in STATEMENT_ROWS:
            found = best(kind, 0, count)
            anchors[kind] = found[1] if found else None
    for kind, anchor in anchors.items():
        if anchor is None:
            continue
        ordered = [anchor]
        for neighbour in (anchor + 1, anchor - 1):
            if 0 <= neighbour < count and scores[neighbour][kind] >= 2:
                other_kinds = [name for name in STATEMENT_ROWS if name != kind]
                if all(scores[neighbour][name] < MINIMUM_SCORE[name] for name in other_kinds):
                    ordered.append(neighbour)
        located[kind] = [page + 1 for page in ordered]
    return located


@dataclass(frozen=True)
class ColumnLayout:
    """Arrangement of value columns on a statement page."""

    columns: int | None  # value cells per row according to the year header
    scopes: tuple[str, ...]  # order of scope blocks, e.g. ("group", "company")
    current_first: bool
    evidence: str
    block_starts: tuple[int, ...] = (0,)  # first cell of each scope block
    variance_columns: bool = False  # each block is followed by a % change cell

    def cell_counts(self) -> set[int]:
        """Row cell counts that agree with the header."""
        if self.columns is None:
            return set()
        counts = {self.columns}
        if self.variance_columns:
            counts.add(self.columns + len(self.block_starts))
        return counts

    def block_start(self, block: int, cells: int) -> int:
        start = self.block_starts[block]
        return start + block if cells != self.columns else start


VARIANCE_HEADER = re.compile(r"%|\bchange\b|\bvariance\b|\+\s*/\s*\(-\)", re.IGNORECASE)
UNIT_SENTENCE = re.compile(
    r"\b(?:values|amounts|figures)\b[^.\n]{0,40}\b(?:rupees?|rs\.?|lkr)[^.\n]{0,15}"
    r"(?:'\s?000s?|000s|thousands?|millions?|\bmn\b)",
    re.IGNORECASE,
)
MONTH_BEFORE_YEAR = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+20\d{2}\b", re.IGNORECASE
)


def header_lines(text: str) -> list[str]:
    """Lines above the first amount row, where scope, year and unit are stated."""
    output = []
    for line in clean_lines(text)[:30]:
        if "|" in line:
            continue
        cells = trailing_values(line).tokens
        amounts = [cell for cell in cells if not re.fullmatch(r"20\d{2}", cell)]
        has_label = bool(re.search(r"[A-Za-z]{3}", line))
        if len(amounts) >= 2 and has_label and not HEADER_YEAR.search(line):
            break
        output.append(line)
    return output


def _year_columns(line: str) -> list[int]:
    """Column years on a header line, without the year of a spelled-out date."""
    years = [int(year) for year in HEADER_YEAR.findall(line)]
    dated = len(years) >= 3 and len(years) % 2 == 1 and MONTH_BEFORE_YEAR.search(line)
    if dated and years[0] == years[1]:
        years = years[1:]
    return years


def _block_starts(years: list[int]) -> tuple[int, ...]:
    """Split the year header into scope blocks where the year order restarts."""
    if len(years) < 2:
        return (0,)
    descending = years[0] > years[1]
    starts = [0]
    for index in range(1, len(years)):
        restarted = (
            years[index] > years[index - 1] if descending else years[index] < years[index - 1]
        )
        if restarted:
            starts.append(index)
    return tuple(starts)


def column_layout(text: str) -> ColumnLayout:
    """Read scope order, column count and year order from a statement header."""
    lines = header_lines(text)
    evidence = []
    columns: int | None = None
    current_first = True
    block_starts: tuple[int, ...] = (0,)
    for line in lines:
        years = _year_columns(line)
        if len(years) >= 2 and len(set(years)) >= 2:
            columns = len(years)
            current_first = years[0] > years[1]
            block_starts = _block_starts(years)
            evidence.append(f"year header '{line[:70]}'")
            break
    scopes: tuple[str, ...] = ()
    for line in lines:
        group, company = SCOPE_GROUP.search(line), SCOPE_COMPANY.search(line)
        if group and company and len(line) <= 110:
            scopes = (
                ("group", "company") if group.start() < company.start() else ("company", "group")
            )
            evidence.append(f"scope header '{line[:70]}'")
            break
    if not scopes:
        scopes = ("primary",) * len(block_starts)
        evidence.append("no Group/Company header; leading column block treated as primary")
    variance = any(VARIANCE_HEADER.search(line) for line in lines)
    return ColumnLayout(
        columns=columns,
        scopes=scopes,
        current_first=current_first,
        evidence="; ".join(evidence),
        block_starts=block_starts,
        variance_columns=variance,
    )


def select_columns(
    row: RowValues, layout: ColumnLayout, block: int | None = None
) -> tuple[Decimal | None, Decimal | None, str, str]:
    """Return (current, previous, scope, basis) for the consolidated column block.

    ``block`` overrides the scope block, for interim pages whose blocks are
    periods (quarter and year to date) rather than Group and Company.
    ``basis`` is ``confirmed`` when the cell count agrees with the page header,
    ``assumed`` when the leading pair is taken without that agreement, and
    ``ambiguous`` when a company-first layout cannot be aligned.
    """
    values = row.values
    if not values:
        return None, None, "unknown", "ambiguous"
    group_index = layout.scopes.index("group") if "group" in layout.scopes else 0
    if block is not None:
        group_index = block
    scope = "group" if "group" in layout.scopes else "primary"
    aligned = len(values) in layout.cell_counts() and group_index < len(layout.block_starts)
    if aligned:
        start = layout.block_start(group_index, len(values))
        block = values[start : start + 2]
        basis = "confirmed"
    elif group_index == 0:
        block = values[:2]
        basis = "assumed"
    else:
        block = values[-2:]
        basis = "ambiguous"
    if len(block) < 2:
        block = [*block, None]
    current, previous = (block[0], block[1]) if layout.current_first else (block[1], block[0])
    return current, previous, scope, basis


def page_unit(text: str) -> tuple[str, Decimal] | None:
    """Reported unit from the statement header or an explicit unit sentence.

    Narrative amounts elsewhere on the page ("Rs. 26.6 Bn") are ignored.
    """
    header = " ".join(header_lines(text))
    unit = detect_unit(header) if header else None
    if unit is not None:
        return unit
    sentence = UNIT_SENTENCE.search(normalize_text(text))
    return detect_unit(sentence.group(0)) if sentence else None


def consensus_unit(pages: list[str], page_numbers: list[int]) -> tuple[str, Decimal] | None:
    """Most common explicit unit across the located primary statement pages."""
    votes: dict[tuple[str, Decimal], int] = {}
    for number in page_numbers:
        unit = page_unit(pages[number - 1])
        if unit is not None:
            votes[unit] = votes.get(unit, 0) + 1
    if not votes:
        return None
    ranked = sorted(votes.items(), key=lambda item: (-item[1], -item[0][1]))
    return ranked[0][0]

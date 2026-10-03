"""Core data contracts shared across pipeline modules."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl


class DocumentKind(StrEnum):
    ANNUAL_REPORT = "annual_report"
    INTERIM_STATEMENT = "interim_statement"
    DIVIDEND_ANNOUNCEMENT = "dividend_announcement"


class PeriodKind(StrEnum):
    ANNUAL = "annual"
    INTERIM = "interim"
    QUARTER = "quarter"
    YEAR_TO_DATE = "year_to_date"
    TRAILING_TWELVE_MONTHS = "ttm"


class StatementScope(StrEnum):
    GROUP = "group"
    COMPANY = "company"
    UNKNOWN = "unknown"


class Company(BaseModel):
    ticker: str
    name: str
    profile_url: HttpUrl
    sector: str
    classification_as_of: date
    classification_source_url: HttpUrl
    enabled: bool = True


class SourceDocument(BaseModel):
    id: str
    ticker: str
    kind: DocumentKind
    title: str
    publication_date: date | None = None
    period_end: date | None = None
    source_url: HttpUrl
    discovery_url: HttpUrl | None = None
    retrieved_at: datetime
    local_path: Path
    sha256: str


class FinancialPeriod(BaseModel):
    start_date: date | None = None
    end_date: date
    kind: PeriodKind
    months: int | None = Field(default=None, ge=1, le=12)
    label: str
    annualized: bool = False


class ExtractionCandidate(BaseModel):
    metric: str
    candidate_value: Decimal | None
    raw_text: str
    page_number: int = Field(ge=1)
    detected_unit: str | None = None
    detected_period_label: str | None = None
    confidence: Decimal = Field(ge=0, le=1)
    strategy: str
    uncertainty_reason: str | None = None


class RawFact(BaseModel):
    id: str
    ticker: str
    metric: str
    period: FinancialPeriod
    value: Decimal | None
    currency: str | None = "LKR"
    normalized_unit: str
    original_value: Decimal | None = None
    original_unit: str | None = None
    scale_multiplier: Decimal = Decimal("1")
    document_id: str
    source_url: HttpUrl
    page_number: int = Field(ge=1)
    document_kind: DocumentKind
    scope: StatementScope = StatementScope.UNKNOWN
    confidence: Decimal = Field(ge=0, le=1)
    extraction_method: str
    source_text: str
    notes: str | None = None


class CalculationInput(BaseModel):
    role: str
    fact_id: str
    metric: str
    value: Decimal
    period_label: str
    source_pages: list[int]


class CalculatedMetric(BaseModel):
    ticker: str
    metric: str
    value: Decimal | None
    unit: str
    period_label: str
    formula: str
    inputs: list[CalculationInput]
    notes: str | None = None


class ManualReviewItem(BaseModel):
    ticker: str
    company: str
    metric: str
    period_label: str
    candidates: list[ExtractionCandidate]
    source_document: str
    source_page: int
    source_text: str
    reason: str


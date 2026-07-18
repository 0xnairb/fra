"""Normalized public-company filing facts used by exposure research."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from fra.domain.errors import DomainValidationError
from fra.domain.time import as_utc


@dataclass(frozen=True, slots=True)
class CompanyFact:
    cik: str
    entity_name: str
    taxonomy: str
    concept: str
    label: str
    unit: str
    value: Decimal
    period_start: date | None
    period_end: date
    filed_at: datetime
    form: str
    accession_number: str

    def __post_init__(self) -> None:
        required = (
            self.cik,
            self.entity_name,
            self.taxonomy,
            self.concept,
            self.label,
            self.unit,
            self.form,
            self.accession_number,
        )
        if any(not item.strip() for item in required):
            raise DomainValidationError("company fact identity fields must not be empty")
        object.__setattr__(self, "filed_at", as_utc(self.filed_at, field="filed_at"))

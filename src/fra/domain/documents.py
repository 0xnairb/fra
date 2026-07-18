"""Normalized document values returned by document-provider ports."""

from dataclasses import dataclass
from datetime import datetime

from fra.domain.errors import DomainValidationError
from fra.domain.time import as_utc


@dataclass(frozen=True, slots=True)
class DocumentQuery:
    text: str
    published_after: datetime | None = None
    published_before: datetime | None = None
    point_in_time_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise DomainValidationError("document query must not be empty")
        for field in ("published_after", "published_before", "point_in_time_at"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, as_utc(value, field=field))


@dataclass(frozen=True, slots=True)
class DocumentRef:
    provider_record_id: str
    title: str
    source: str
    published_at: datetime | None = None
    updated_at: datetime | None = None
    corrects_provider_record_id: str | None = None
    withdrawn: bool = False

    def __post_init__(self) -> None:
        if not self.provider_record_id.strip() or not self.title.strip() or not self.source.strip():
            raise DomainValidationError("document references require ID, title, and source")
        for field in ("published_at", "updated_at"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, as_utc(value, field=field))
        if self.updated_at and self.published_at and self.updated_at < self.published_at:
            raise DomainValidationError("document update cannot precede publication")


@dataclass(frozen=True, slots=True)
class Document:
    provider_record_id: str
    title: str
    source: str
    content: str
    published_at: datetime | None = None
    updated_at: datetime | None = None
    corrects_provider_record_id: str | None = None
    withdrawn: bool = False

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise DomainValidationError("document content must not be empty")
        for field in ("published_at", "updated_at"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, as_utc(value, field=field))
        if self.updated_at and self.published_at and self.updated_at < self.published_at:
            raise DomainValidationError("document update cannot precede publication")


@dataclass(frozen=True, slots=True)
class DocumentCapabilities:
    search: bool
    fetch: bool
    point_in_time: bool

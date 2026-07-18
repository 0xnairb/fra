"""Provider-neutral regional identifiers and capability-pack decisions."""

from dataclasses import dataclass
from enum import StrEnum


class RegionalPackState(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class RegionalIdentifierMapping:
    name: str
    format: str
    authority: str


@dataclass(frozen=True, slots=True)
class RegionalPack:
    code: str
    name: str
    state: RegionalPackState
    identifiers: tuple[RegionalIdentifierMapping, ...]
    document_providers: tuple[str, ...]
    market_providers: tuple[str, ...]
    limitations: tuple[str, ...] = ()

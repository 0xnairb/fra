"""Immutable research signal versions."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from fra.domain.errors import DomainValidationError
from fra.domain.ids import EvidenceId, ResearchRunId, SignalId
from fra.domain.time import as_utc


class SignalStance(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class SignalStrength(StrEnum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalStatus(StrEnum):
    ACTIVE = "active"
    WEAKENED = "weakened"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class Signal:
    id: SignalId
    version: int
    run_id: ResearchRunId
    subject_ids: tuple[str, ...]
    summary: str
    stance: SignalStance
    strength: SignalStrength
    confidence: Confidence
    horizon: str
    issued_at: datetime
    knowledge_cutoff_at: datetime
    evidence_ids: tuple[EvidenceId, ...]
    invalidation_conditions: tuple[str, ...]
    status: SignalStatus
    calculation_ids: tuple[str, ...] = ()
    rationale: str = ""
    limitations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    next_review_at: datetime | None = None
    supersedes_version: int | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise DomainValidationError("signal version must be positive")
        if not self.subject_ids or not self.summary.strip() or not self.horizon.strip():
            raise DomainValidationError("signal requires subjects, summary, and horizon")
        if not self.evidence_ids and not self.calculation_ids:
            raise DomainValidationError("signal requires supporting evidence or calculations")
        if not self.invalidation_conditions:
            raise DomainValidationError("signal requires invalidation conditions")
        object.__setattr__(self, "issued_at", as_utc(self.issued_at, field="issued_at"))
        object.__setattr__(
            self,
            "knowledge_cutoff_at",
            as_utc(self.knowledge_cutoff_at, field="knowledge_cutoff_at"),
        )
        if self.next_review_at is not None:
            object.__setattr__(
                self, "next_review_at", as_utc(self.next_review_at, field="next_review_at")
            )
        if self.knowledge_cutoff_at > self.issued_at:
            raise DomainValidationError("signal knowledge cutoff cannot follow issued_at")
        if self.supersedes_version is not None and self.supersedes_version >= self.version:
            raise DomainValidationError("signal may only supersede an earlier version")

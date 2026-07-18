"""Research mandate, evidence, claim, and run-state policies."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from fra.domain.errors import (
    DomainValidationError,
    InvalidStateTransitionError,
    LookAheadEvidenceError,
)
from fra.domain.ids import ClaimId, EvidenceId, MandateId, ResearchRunId
from fra.domain.shared import Failure
from fra.domain.sources import DataEnvelope, DataKind
from fra.domain.time import as_utc


class ResearchMandateType(StrEnum):
    GENERAL_RESEARCH = "general_research"
    CRYPTO_MARKET_TIMING = "crypto_market_timing"
    ASSET_ALLOCATION = "asset_allocation"
    CRISIS_IMPACT = "crisis_impact"


@dataclass(frozen=True, slots=True)
class ResearchMandate:
    id: MandateId
    kind: ResearchMandateType
    question: str
    created_at: datetime
    user_facts: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    horizon: str | None = None

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise DomainValidationError("research question must not be empty")
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))


@dataclass(frozen=True, slots=True)
class Evidence[EvidenceValueT]:
    id: EvidenceId
    run_id: ResearchRunId
    kind: DataKind
    summary: str
    envelope: DataEnvelope[EvidenceValueT]
    knowledge_cutoff_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise DomainValidationError("evidence summary must not be empty")
        object.__setattr__(
            self,
            "knowledge_cutoff_at",
            as_utc(self.knowledge_cutoff_at, field="knowledge_cutoff_at"),
        )
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))
        if self.envelope.available_at > self.knowledge_cutoff_at:
            raise LookAheadEvidenceError(
                "available_at cannot occur after the evidence knowledge cutoff"
            )

    @classmethod
    def from_envelope(
        cls,
        *,
        id: EvidenceId,
        run_id: ResearchRunId,
        kind: DataKind,
        summary: str,
        envelope: DataEnvelope[EvidenceValueT],
        knowledge_cutoff_at: datetime,
        created_at: datetime,
    ) -> Evidence[EvidenceValueT]:
        return cls(
            id=id,
            run_id=run_id,
            kind=kind,
            summary=summary,
            envelope=envelope,
            knowledge_cutoff_at=knowledge_cutoff_at,
            created_at=created_at,
        )

    @property
    def provider_id(self) -> str:
        return self.envelope.descriptor.provider_id

    @property
    def value(self) -> EvidenceValueT:
        return self.envelope.value

    @property
    def available_at(self) -> datetime:
        return self.envelope.available_at


class ClaimMateriality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ClaimStatus(StrEnum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    REJECTED = "rejected"
    CONFLICTING = "conflicting"


class ClaimConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class Claim:
    id: ClaimId
    run_id: ResearchRunId
    statement: str
    materiality: ClaimMateriality
    status: ClaimStatus
    confidence: ClaimConfidence
    evidence_ids: tuple[EvidenceId, ...]
    created_at: datetime
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise DomainValidationError("claim statement must not be empty")
        if self.materiality is ClaimMateriality.HIGH and not self.evidence_ids:
            raise DomainValidationError("a material claim requires supporting evidence")
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))


class ResearchRunState(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    COLLECTING_EVIDENCE = "collecting_evidence"
    ANALYZING = "analyzing"
    VERIFYING = "verifying"
    NEEDS_RESEARCH = "needs_research"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_USER_INPUT = "needs_user_input"


_ACTIVE_STATES = frozenset(
    {
        ResearchRunState.CREATED,
        ResearchRunState.PLANNING,
        ResearchRunState.COLLECTING_EVIDENCE,
        ResearchRunState.ANALYZING,
        ResearchRunState.VERIFYING,
        ResearchRunState.NEEDS_RESEARCH,
        ResearchRunState.SYNTHESIZING,
    }
)
_INTERRUPTED_STATES = frozenset(
    {ResearchRunState.FAILED, ResearchRunState.CANCELLED, ResearchRunState.NEEDS_USER_INPUT}
)
_NEXT_STATES: dict[ResearchRunState, frozenset[ResearchRunState]] = {
    ResearchRunState.CREATED: frozenset({ResearchRunState.PLANNING}),
    ResearchRunState.PLANNING: frozenset({ResearchRunState.COLLECTING_EVIDENCE}),
    ResearchRunState.COLLECTING_EVIDENCE: frozenset({ResearchRunState.ANALYZING}),
    ResearchRunState.ANALYZING: frozenset({ResearchRunState.VERIFYING}),
    ResearchRunState.VERIFYING: frozenset(
        {ResearchRunState.NEEDS_RESEARCH, ResearchRunState.SYNTHESIZING}
    ),
    ResearchRunState.NEEDS_RESEARCH: frozenset({ResearchRunState.COLLECTING_EVIDENCE}),
    ResearchRunState.SYNTHESIZING: frozenset({ResearchRunState.COMPLETED}),
}


@dataclass(frozen=True, slots=True)
class ResearchRun:
    id: ResearchRunId
    mandate: ResearchMandate
    state: ResearchRunState
    created_at: datetime
    updated_at: datetime
    state_history: tuple[ResearchRunState, ...]
    completed_at: datetime | None = None
    failure: Failure | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", as_utc(self.created_at, field="created_at"))
        object.__setattr__(self, "updated_at", as_utc(self.updated_at, field="updated_at"))
        if self.completed_at is not None:
            object.__setattr__(
                self, "completed_at", as_utc(self.completed_at, field="completed_at")
            )
        if self.updated_at < self.created_at:
            raise DomainValidationError("research run updated_at cannot precede created_at")
        if not self.state_history or self.state_history[-1] is not self.state:
            raise DomainValidationError("research run history must end at its current state")
        if self.state is ResearchRunState.COMPLETED and self.completed_at is None:
            raise DomainValidationError("completed research run requires completed_at")

    @classmethod
    def create(
        cls, id: ResearchRunId, mandate: ResearchMandate, created_at: datetime
    ) -> ResearchRun:
        created_at = as_utc(created_at, field="created_at")
        return cls(
            id=id,
            mandate=mandate,
            state=ResearchRunState.CREATED,
            created_at=created_at,
            updated_at=created_at,
            state_history=(ResearchRunState.CREATED,),
        )

    def transition(
        self,
        target: ResearchRunState,
        transitioned_at: datetime,
        *,
        failure: Failure | None = None,
    ) -> ResearchRun:
        transitioned_at = as_utc(transitioned_at, field="transitioned_at")
        if transitioned_at < self.updated_at:
            raise DomainValidationError("transition time cannot precede the previous update")
        allowed = set(_NEXT_STATES.get(self.state, frozenset()))
        if self.state in _ACTIVE_STATES:
            allowed.update(_INTERRUPTED_STATES)
        if target not in allowed:
            raise InvalidStateTransitionError(
                f"research run cannot transition from {self.state.value} to {target.value}"
            )
        if failure is not None and target not in {
            ResearchRunState.FAILED,
            ResearchRunState.NEEDS_USER_INPUT,
        }:
            raise DomainValidationError("failure may only accompany a failed or input-needed run")
        completed_at = transitioned_at if target is ResearchRunState.COMPLETED else None
        return replace(
            self,
            state=target,
            updated_at=transitioned_at,
            state_history=(*self.state_history, target),
            completed_at=completed_at,
            failure=failure,
        )

"""Repository ports for initial research and signal aggregates."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fra.domain.ids import ClaimId, EvidenceId, ResearchRunId, SignalId
from fra.domain.research import Claim, Evidence, ResearchRun, ResearchRunState
from fra.domain.shared import ArtifactRef
from fra.domain.signals import Signal, SignalStatus


@dataclass(frozen=True, slots=True)
class ResearchRunQuery:
    states: frozenset[ResearchRunState] = frozenset()
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ResearchRunSummary:
    id: ResearchRunId
    question: str
    state: ResearchRunState
    updated_at: datetime
    artifact: ArtifactRef | None = None


@dataclass(frozen=True, slots=True)
class ResearchReport:
    title: str
    body: str
    artifact: ArtifactRef | None = None


class ResearchRepository(Protocol):
    def create(self, run: ResearchRun) -> None: ...

    def get(self, run_id: ResearchRunId) -> ResearchRun: ...

    def save(self, run: ResearchRun) -> None: ...

    def list(self, query: ResearchRunQuery | None = None) -> tuple[ResearchRunSummary, ...]: ...

    def add_evidence(self, run_id: ResearchRunId, item: Evidence[object]) -> None: ...

    def get_evidence(self, run_id: ResearchRunId, evidence_id: EvidenceId) -> Evidence[object]: ...

    def add_claim(self, run_id: ResearchRunId, claim: Claim) -> None: ...

    def get_claim(self, run_id: ResearchRunId, claim_id: ClaimId) -> Claim: ...

    def save_report(self, run_id: ResearchRunId, report: ResearchReport) -> None: ...


class SignalRepository(Protocol):
    def save(self, signal: Signal) -> None: ...

    def get(self, signal_id: SignalId, version: int | None = None) -> Signal: ...

    def list(self, statuses: frozenset[SignalStatus] = frozenset()) -> tuple[Signal, ...]: ...

"""Hermetic repository implementations with production-like conflict semantics."""

from fra.domain.errors import RepositoryConflictError, RepositoryNotFoundError
from fra.domain.ids import ClaimId, EvidenceId, ResearchRunId, SignalId
from fra.domain.research import Claim, Evidence, ResearchRun
from fra.domain.signals import Signal, SignalStatus
from fra.ports.repositories import (
    ResearchReport,
    ResearchRunQuery,
    ResearchRunSummary,
)


class InMemoryResearchRepository:
    def __init__(self) -> None:
        self._runs: dict[ResearchRunId, ResearchRun] = {}
        self._evidence: dict[tuple[ResearchRunId, EvidenceId], Evidence[object]] = {}
        self._claims: dict[tuple[ResearchRunId, ClaimId], Claim] = {}
        self._reports: dict[ResearchRunId, ResearchReport] = {}

    def create(self, run: ResearchRun) -> None:
        if run.id in self._runs:
            raise RepositoryConflictError(f"research run {run.id} already exists")
        self._runs[run.id] = run

    def get(self, run_id: ResearchRunId) -> ResearchRun:
        try:
            return self._runs[run_id]
        except KeyError as error:
            raise RepositoryNotFoundError(f"research run {run_id} does not exist") from error

    def save(self, run: ResearchRun) -> None:
        existing = self.get(run.id)
        if run.updated_at < existing.updated_at:
            raise RepositoryConflictError(f"research run {run.id} update is stale")
        self._runs[run.id] = run

    def list(self, query: ResearchRunQuery | None = None) -> tuple[ResearchRunSummary, ...]:
        query = query or ResearchRunQuery()
        runs = sorted(self._runs.values(), key=lambda item: item.updated_at, reverse=True)
        if query.states:
            runs = [run for run in runs if run.state in query.states]
        if query.limit is not None:
            runs = runs[: query.limit]
        return tuple(
            ResearchRunSummary(
                id=run.id,
                question=run.mandate.question,
                state=run.state,
                updated_at=run.updated_at,
            )
            for run in runs
        )

    def add_evidence(self, run_id: ResearchRunId, item: Evidence[object]) -> None:
        self.get(run_id)
        key = (run_id, item.id)
        if key in self._evidence:
            raise RepositoryConflictError(f"evidence {item.id} already exists")
        self._evidence[key] = item

    def get_evidence(self, run_id: ResearchRunId, evidence_id: EvidenceId) -> Evidence[object]:
        try:
            return self._evidence[(run_id, evidence_id)]
        except KeyError as error:
            raise RepositoryNotFoundError(f"evidence {evidence_id} does not exist") from error

    def add_claim(self, run_id: ResearchRunId, claim: Claim) -> None:
        self.get(run_id)
        key = (run_id, claim.id)
        if key in self._claims:
            raise RepositoryConflictError(f"claim {claim.id} already exists")
        self._claims[key] = claim

    def get_claim(self, run_id: ResearchRunId, claim_id: ClaimId) -> Claim:
        try:
            return self._claims[(run_id, claim_id)]
        except KeyError as error:
            raise RepositoryNotFoundError(f"claim {claim_id} does not exist") from error

    def save_report(self, run_id: ResearchRunId, report: ResearchReport) -> None:
        self.get(run_id)
        if run_id in self._reports:
            raise RepositoryConflictError(f"report for {run_id} already exists")
        self._reports[run_id] = report


class InMemorySignalRepository:
    def __init__(self) -> None:
        self._signals: dict[tuple[SignalId, int], Signal] = {}

    def save(self, signal: Signal) -> None:
        key = (signal.id, signal.version)
        if key in self._signals:
            raise RepositoryConflictError(
                f"signal {signal.id} version {signal.version} is immutable and already exists"
            )
        if signal.version > 1 and (signal.id, signal.version - 1) not in self._signals:
            raise RepositoryConflictError("signal versions must be contiguous")
        self._signals[key] = signal

    def get(self, signal_id: SignalId, version: int | None = None) -> Signal:
        if version is None:
            versions = [key_version for key_id, key_version in self._signals if key_id == signal_id]
            if not versions:
                raise RepositoryNotFoundError(f"signal {signal_id} does not exist")
            version = max(versions)
        try:
            return self._signals[(signal_id, version)]
        except KeyError as error:
            raise RepositoryNotFoundError(
                f"signal {signal_id} version {version} does not exist"
            ) from error

    def list(self, statuses: frozenset[SignalStatus] = frozenset()) -> tuple[Signal, ...]:
        latest = {signal_id: self.get(signal_id) for signal_id, _version in self._signals}
        signals = tuple(latest.values())
        if statuses:
            signals = tuple(signal for signal in signals if signal.status in statuses)
        return tuple(sorted(signals, key=lambda signal: signal.issued_at, reverse=True))

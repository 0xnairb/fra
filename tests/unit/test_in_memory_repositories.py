from datetime import UTC, datetime

import pytest

from fra.adapters.in_memory.repositories import InMemoryResearchRepository, InMemorySignalRepository
from fra.domain.errors import RepositoryConflictError, RepositoryNotFoundError
from fra.domain.ids import EvidenceId, MandateId, ResearchRunId, SignalId
from fra.domain.research import ResearchMandate, ResearchMandateType, ResearchRun
from fra.domain.signals import Confidence, Signal, SignalStance, SignalStatus, SignalStrength

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def make_run() -> ResearchRun:
    mandate = ResearchMandate(
        id=MandateId("mandate_0001"),
        kind=ResearchMandateType.GENERAL_RESEARCH,
        question="What changed?",
        created_at=NOW,
    )
    return ResearchRun.create(ResearchRunId("run_0001"), mandate, NOW)


def make_signal() -> Signal:
    return Signal(
        id=SignalId("signal_0001"),
        version=1,
        run_id=ResearchRunId("run_0001"),
        subject_ids=("instrument_0001",),
        summary="Fixture observation",
        stance=SignalStance.NEUTRAL,
        strength=SignalStrength.MODERATE,
        confidence=Confidence.MEDIUM,
        horizon="3 months",
        issued_at=NOW,
        knowledge_cutoff_at=NOW,
        evidence_ids=(EvidenceId("evidence_0001"),),
        invalidation_conditions=("Fixture changes",),
        status=SignalStatus.ACTIVE,
    )


def test_research_repository_rejects_duplicate_creation_and_missing_updates() -> None:
    repository = InMemoryResearchRepository()
    run = make_run()
    repository.create(run)

    with pytest.raises(RepositoryConflictError):
        repository.create(run)
    with pytest.raises(RepositoryNotFoundError):
        repository.get(ResearchRunId("run_missing"))


def test_signal_versions_are_immutable() -> None:
    repository = InMemorySignalRepository()
    signal = make_signal()
    repository.save(signal)

    with pytest.raises(RepositoryConflictError, match="immutable"):
        repository.save(signal)

    assert repository.get(signal.id, 1) == signal

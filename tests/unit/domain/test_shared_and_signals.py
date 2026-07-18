from datetime import UTC, datetime, timedelta

import pytest

from fra.domain.errors import DomainValidationError
from fra.domain.ids import EvidenceId, ResearchRunId, SignalId
from fra.domain.shared import (
    ArtifactKind,
    ArtifactRef,
    Failure,
    FailureKind,
    HealthState,
    HealthStatus,
)
from fra.domain.signals import (
    Confidence,
    Signal,
    SignalStance,
    SignalStatus,
    SignalStrength,
)

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def test_artifact_references_are_portable_and_cannot_escape_the_workspace() -> None:
    ref = ArtifactRef(ArtifactKind.RESEARCH_RUN, "runs/2026/07/run_0001/run.md")

    assert ref.location == "runs/2026/07/run_0001/run.md"

    with pytest.raises(DomainValidationError, match="relative"):
        ArtifactRef(ArtifactKind.RESEARCH_RUN, "../outside.md")


def test_health_status_carries_a_typed_failure() -> None:
    failure = Failure(FailureKind.ADAPTER_UNAVAILABLE, "fixture is offline", retryable=True)
    status = HealthStatus(
        state=HealthState.UNAVAILABLE,
        checked_at=NOW,
        summary="unavailable",
        failure=failure,
    )

    assert status.ok is False
    assert status.failure is failure


def test_signal_requires_support_and_a_non_future_knowledge_cutoff() -> None:
    with pytest.raises(DomainValidationError, match="supporting evidence"):
        Signal(
            id=SignalId("signal_0001"),
            version=1,
            run_id=ResearchRunId("run_0001"),
            subject_ids=("instrument_0001",),
            summary="A supported observation",
            stance=SignalStance.NEUTRAL,
            strength=SignalStrength.MODERATE,
            confidence=Confidence.MEDIUM,
            horizon="3 months",
            issued_at=NOW,
            knowledge_cutoff_at=NOW,
            evidence_ids=(),
            invalidation_conditions=("New evidence contradicts the observation",),
            status=SignalStatus.ACTIVE,
        )

    with pytest.raises(DomainValidationError, match="knowledge cutoff"):
        Signal(
            id=SignalId("signal_0001"),
            version=1,
            run_id=ResearchRunId("run_0001"),
            subject_ids=("instrument_0001",),
            summary="A supported observation",
            stance=SignalStance.NEUTRAL,
            strength=SignalStrength.MODERATE,
            confidence=Confidence.MEDIUM,
            horizon="3 months",
            issued_at=NOW,
            knowledge_cutoff_at=NOW + timedelta(seconds=1),
            evidence_ids=(EvidenceId("evidence_0001"),),
            invalidation_conditions=("New evidence contradicts the observation",),
            status=SignalStatus.ACTIVE,
        )

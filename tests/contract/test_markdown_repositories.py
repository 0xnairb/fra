from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from fra.adapters.in_memory.repositories import InMemoryResearchRepository, InMemorySignalRepository
from fra.adapters.storage.markdown_research import MarkdownResearchRepository
from fra.adapters.storage.markdown_signals import MarkdownSignalRepository
from fra.adapters.storage.workspace import Workspace
from fra.domain.errors import RepositoryConflictError, RepositoryCorruptError
from fra.domain.ids import (
    ClaimId,
    EvidenceId,
    InstrumentId,
    MandateId,
    PlanId,
    ResearchRunId,
    ScenarioId,
    SignalId,
    VerificationId,
)
from fra.domain.instruments import Currency
from fra.domain.market_data import MarketQuote
from fra.domain.research import (
    Claim,
    ClaimConfidence,
    ClaimMateriality,
    ClaimStatus,
    Evidence,
    ResearchDataRequirement,
    ResearchMandate,
    ResearchMandateType,
    ResearchPlan,
    ResearchPlanTask,
    ResearchRun,
    ResearchRunState,
    ResearchScenario,
    VerificationResult,
)
from fra.domain.signals import Confidence, Signal, SignalStance, SignalStatus, SignalStrength
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    DataKind,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    UsageProfile,
)
from fra.ports.repositories import ResearchReport, ResearchRepository, SignalRepository

NOW = datetime(2026, 7, 18, 8, 30, tzinfo=UTC)


def make_run() -> ResearchRun:
    mandate = ResearchMandate(
        id=MandateId("mandate_0001"),
        kind=ResearchMandateType.GENERAL_RESEARCH,
        question="What changed?",
        created_at=NOW,
        user_facts=("fixture",),
        assumptions=("stable fixture",),
    )
    return ResearchRun.create(ResearchRunId("run_0001"), mandate, NOW)


def make_evidence() -> Evidence[object]:
    descriptor = SourceDescriptor(
        provider_id="fixture",
        adapter_version="1.0.0",
        source_kinds=frozenset({SourceKind.MARKET_DATA}),
        authority_class=AuthorityClass.AGGREGATOR,
        point_in_time_support=True,
        allowed_usage_profiles=frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
        raw_retention=RawRetentionPolicy.PROHIBITED,
        terms_url="https://example.test/terms",
        terms_reviewed_at=date(2026, 7, 1),
        independence_group="fixture",
    )
    quote = MarketQuote(
        instrument_id=InstrumentId("crypto:bitcoin"),
        price=Decimal("65000.00"),
        currency=Currency("USD"),
        observed_at=NOW - timedelta(minutes=2),
    )
    envelope = DataEnvelope(
        value=quote,
        descriptor=descriptor,
        provider_record_id="record-1",
        source="fixture://quote/1",
        observed_at=quote.observed_at,
        available_at=NOW - timedelta(minutes=1),
        retrieved_at=NOW,
        content_hash="sha256:abc",
    )
    return Evidence.from_envelope(
        id=EvidenceId("evidence_0001"),
        run_id=ResearchRunId("run_0001"),
        kind=DataKind.MARKET_QUOTE,
        summary="Bitcoin fixture quote",
        envelope=envelope,
        knowledge_cutoff_at=NOW,
        created_at=NOW,
    )


def make_claim() -> Claim:
    return Claim(
        id=ClaimId("claim_0001"),
        run_id=ResearchRunId("run_0001"),
        statement="The fixture price is available.",
        materiality=ClaimMateriality.HIGH,
        status=ClaimStatus.VERIFIED,
        confidence=ClaimConfidence.HIGH,
        evidence_ids=(EvidenceId("evidence_0001"),),
        created_at=NOW,
    )


def make_plan() -> ResearchPlan:
    return ResearchPlan(
        PlanId("plan_0001"),
        ResearchRunId("run_0001"),
        "Answer the fixture question",
        (ResearchPlanTask("task_1", "Collect the fixture quote"),),
        (
            ResearchDataRequirement(
                "data_1",
                "Bitcoin fixture quote",
                DataKind.MARKET_QUOTE,
                ("crypto:bitcoin",),
                ("price",),
                freshness="5 minutes",
            ),
        ),
        NOW,
    )


def make_scenario() -> ResearchScenario:
    return ResearchScenario(
        ScenarioId("scenario_0001"),
        ResearchRunId("run_0001"),
        "Base",
        "The fixture quote remains available.",
        (EvidenceId("evidence_0001"),),
        ("the fixture quote is withdrawn",),
        NOW,
    )


def make_verification() -> VerificationResult:
    return VerificationResult(
        VerificationId("verification_0001"),
        ResearchRunId("run_0001"),
        True,
        True,
        True,
        (),
        NOW,
    )


def make_signal(version: int = 1) -> Signal:
    return Signal(
        id=SignalId("signal_0001"),
        version=version,
        run_id=ResearchRunId("run_0001"),
        subject_ids=("crypto:bitcoin",),
        summary=f"Fixture signal v{version}",
        stance=SignalStance.NEUTRAL,
        strength=SignalStrength.MODERATE,
        confidence=Confidence.MEDIUM,
        horizon="3 months",
        issued_at=NOW + timedelta(minutes=version - 1),
        knowledge_cutoff_at=NOW,
        evidence_ids=(EvidenceId("evidence_0001"),),
        invalidation_conditions=("Fixture changes",),
        status=SignalStatus.ACTIVE,
        supersedes_version=version - 1 if version > 1 else None,
    )


def repositories(root: Path) -> tuple[MarkdownResearchRepository, MarkdownSignalRepository]:
    workspace = Workspace(root)
    workspace.initialize()
    return MarkdownResearchRepository(workspace), MarkdownSignalRepository(workspace)


@pytest.mark.parametrize("backend", ["memory", "markdown"])
def test_research_and_signal_repository_shared_contract(backend: str, tmp_path: Path) -> None:
    research: ResearchRepository
    signals: SignalRepository
    if backend == "memory":
        research = InMemoryResearchRepository()
        signals = InMemorySignalRepository()
    else:
        research, signals = repositories(tmp_path / "workspace")
    run = make_run()
    evidence = make_evidence()
    claim = make_claim()
    plan = make_plan()
    scenario = make_scenario()
    verification = make_verification()
    signal = make_signal()

    research.create(run)
    research.save_plan(run.id, plan)
    research.add_evidence(run.id, evidence)
    research.add_claim(run.id, claim)
    research.add_scenario(run.id, scenario)
    research.save_verification(run.id, verification)
    research.save_report(run.id, ResearchReport("Fixture report", "# Report\n"))
    signals.save(signal)

    assert research.get(run.id) == run
    assert research.get_plan(run.id) == plan
    assert research.get_evidence(run.id, evidence.id) == evidence
    assert research.get_claim(run.id, claim.id) == claim
    assert research.get_scenario(run.id, scenario.id) == scenario
    assert research.get_verification(run.id) == verification
    assert research.list()[0].id == run.id
    assert signals.get(signal.id) == signal
    assert signals.list() == (signal,)
    with pytest.raises(RepositoryConflictError):
        research.create(run)
    with pytest.raises(RepositoryConflictError):
        research.add_evidence(run.id, evidence)
    with pytest.raises(RepositoryConflictError):
        signals.save(signal)


def test_markdown_research_repository_reconstructs_complete_run_from_files(
    tmp_path: Path,
) -> None:
    research, _signals = repositories(tmp_path / "workspace")
    run = make_run()
    research.create(run)
    research.add_evidence(run.id, make_evidence())
    research.add_claim(run.id, make_claim())
    updated = run.transition(ResearchRunState.PLANNING, NOW + timedelta(minutes=1))
    research.save(updated)

    reconstructed = MarkdownResearchRepository(Workspace(tmp_path / "workspace"))

    assert reconstructed.get(run.id) == updated
    assert reconstructed.get_evidence(run.id, EvidenceId("evidence_0001")) == make_evidence()
    assert reconstructed.get_claim(run.id, ClaimId("claim_0001")) == make_claim()
    summary = reconstructed.list()[0]
    assert summary.artifact is not None
    assert summary.artifact.location.endswith("/run.md")
    run_path = tmp_path / "workspace" / summary.artifact.location
    metadata, _body = Workspace(tmp_path / "workspace").codec.parse(
        run_path.read_text(), expected_schema="fra.research_run"
    )
    assert metadata["created_at"] == "2026-07-18T08:30:00Z"
    assert metadata["updated_at"] == "2026-07-18T08:31:00Z"


def test_markdown_signal_versions_are_immutable_contiguous_and_explicitly_superseded(
    tmp_path: Path,
) -> None:
    _research, signals = repositories(tmp_path / "workspace")
    v1 = make_signal()
    signals.save(v1)

    with pytest.raises(RepositoryConflictError, match="immutable"):
        signals.save(replace(v1, summary="rewritten"))
    with pytest.raises(RepositoryConflictError, match="contiguous"):
        signals.save(make_signal(3))
    with pytest.raises(RepositoryConflictError, match="supersede"):
        signals.save(replace(make_signal(2), supersedes_version=None))

    v2 = make_signal(2)
    signals.save(v2)
    reconstructed = MarkdownSignalRepository(Workspace(tmp_path / "workspace"))
    assert reconstructed.get(v1.id) == v2
    assert reconstructed.list() == (v2,)


def test_unsupported_schema_version_fails_visibly(tmp_path: Path) -> None:
    research, _signals = repositories(tmp_path / "workspace")
    research.create(make_run())
    path = tmp_path / "workspace" / "runs" / "2026" / "07" / "run_0001" / "run.md"
    path.write_text(path.read_text().replace("schema_version: 1", "schema_version: 99", 1))

    with pytest.raises(RepositoryCorruptError, match="unsupported"):
        MarkdownResearchRepository(Workspace(tmp_path / "workspace")).get(ResearchRunId("run_0001"))


def test_partial_sibling_write_is_ignored_during_reconstruction(tmp_path: Path) -> None:
    research, _signals = repositories(tmp_path / "workspace")
    run = make_run()
    research.create(run)
    run_file = tmp_path / "workspace" / "runs" / "2026" / "07" / "run_0001" / "run.md"
    (run_file.parent / ".run.md.interrupted.tmp").write_text("partial")

    reconstructed = MarkdownResearchRepository(Workspace(tmp_path / "workspace"))

    assert reconstructed.get(run.id) == run

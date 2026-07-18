from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fra.adapters.in_memory.repositories import InMemoryResearchRepository
from fra.adapters.system.deterministic import FixedClock, SequenceIdGenerator
from fra.application.verification_service import VerificationService
from fra.domain.ids import (
    CalculationId,
    ClaimId,
    EvidenceId,
    InstrumentId,
    MandateId,
    PlanId,
    ResearchRunId,
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
    VerificationIssue,
    VerificationSeverity,
)
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    DataKind,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    UsageProfile,
)

NOW = datetime(2026, 7, 19, 8, tzinfo=UTC)


def test_research_plan_uses_typed_tasks_and_data_requirements() -> None:
    plan = ResearchPlan(
        PlanId("plan_0001"),
        ResearchRunId("run_0001"),
        "Assess the fixture",
        (
            ResearchPlanTask("task_1", "Collect official evidence"),
            ResearchPlanTask("task_2", "Analyze it", ("task_1",)),
        ),
        (
            ResearchDataRequirement(
                "data_1",
                "Official fixture quote",
                DataKind.MARKET_QUOTE,
                ("fixture:asset",),
                ("price",),
            ),
        ),
        NOW,
    )

    assert plan.tasks[1].depends_on == ("task_1",)
    assert plan.data_requirements[0].data_kind is DataKind.MARKET_QUOTE


def test_deterministic_verification_cannot_be_overridden_by_agent_pass() -> None:
    repository = InMemoryResearchRepository()
    run = _run()
    repository.create(run)
    unsupported = Claim(
        ClaimId("claim_unsupported"),
        run.id,
        "The unsupported material claim passes only because the agent says so.",
        ClaimMateriality.HIGH,
        ClaimStatus.PROPOSED,
        ClaimConfidence.HIGH,
        (),
        NOW,
        calculation_ids=(CalculationId("calculation_missing"),),
    )
    repository.add_claim(run.id, unsupported)

    result = VerificationService(
        repository,
        FixedClock(NOW),
        SequenceIdGenerator(),
    ).verify(run, (unsupported,), agent_passed=True, agent_issues=())

    assert result.passed is False
    assert any(issue.code == "citation_missing" for issue in result.issues)
    assert repository.get_claim(run.id, unsupported.id).status is ClaimStatus.REJECTED


def test_deterministic_verification_accepts_existing_point_in_time_evidence() -> None:
    repository = InMemoryResearchRepository()
    run = _run()
    repository.create(run)
    evidence = _evidence(run.id)
    repository.add_evidence(run.id, evidence)
    supported = Claim(
        ClaimId("claim_supported"),
        run.id,
        "The persisted quote was available by the research cutoff.",
        ClaimMateriality.HIGH,
        ClaimStatus.PROPOSED,
        ClaimConfidence.MEDIUM,
        (evidence.id,),
        NOW,
    )
    repository.add_claim(run.id, supported)

    result = VerificationService(
        repository,
        FixedClock(NOW),
        SequenceIdGenerator(),
    ).verify(run, (supported,), agent_passed=True, agent_issues=())

    assert result.passed is True
    assert repository.get_claim(run.id, supported.id).status is ClaimStatus.VERIFIED


def test_agent_advisories_are_retained_without_blocking_a_passing_verification() -> None:
    repository = InMemoryResearchRepository()
    run = _run()
    repository.create(run)
    evidence = _evidence(run.id)
    repository.add_evidence(run.id, evidence)
    supported = Claim(
        ClaimId("claim_supported"),
        run.id,
        "The persisted quote was available by the research cutoff.",
        ClaimMateriality.HIGH,
        ClaimStatus.PROPOSED,
        ClaimConfidence.MEDIUM,
        (evidence.id,),
        NOW,
    )
    repository.add_claim(run.id, supported)
    advisory = VerificationIssue(
        "source_warning",
        "The fixture source is suitable only for personal research.",
        VerificationSeverity.LOW,
    )

    result = VerificationService(
        repository,
        FixedClock(NOW),
        SequenceIdGenerator(),
    ).verify(run, (supported,), agent_passed=True, agent_issues=(advisory,))

    assert result.passed is True
    assert result.issues[-1] == advisory
    assert repository.get_claim(run.id, supported.id).status is ClaimStatus.VERIFIED


def _run() -> ResearchRun:
    mandate = ResearchMandate(
        MandateId("mandate_0001"),
        ResearchMandateType.GENERAL_RESEARCH,
        "What changed?",
        NOW,
    )
    return ResearchRun.create(ResearchRunId("run_0001"), mandate, NOW)


def _evidence(run_id: ResearchRunId) -> Evidence[object]:
    descriptor = SourceDescriptor(
        "fixture_official",
        "1",
        frozenset({SourceKind.MARKET_DATA}),
        AuthorityClass.OFFICIAL,
        True,
        frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
        RawRetentionPolicy.PROHIBITED,
        "https://fixture.test/terms",
        date(2026, 7, 1),
        "fixture",
    )
    observed = NOW - timedelta(minutes=2)
    envelope = DataEnvelope(
        MarketQuote(InstrumentId("fixture:asset"), Decimal("100"), Currency("USD"), observed),
        descriptor,
        "fixture-record",
        "https://fixture.test/quote",
        NOW - timedelta(minutes=1),
        NOW,
        observed_at=observed,
    )
    return Evidence(
        EvidenceId("evidence_0001"),
        run_id,
        DataKind.MARKET_QUOTE,
        "Fixture quote",
        envelope,
        NOW,
        NOW,
    )

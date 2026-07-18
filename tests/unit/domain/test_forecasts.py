from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from fra.adapters.in_memory.repositories import (
    InMemoryForecastRepository,
    InMemoryOutcomeRepository,
)
from fra.adapters.system.deterministic import FixedClock, SequenceIdGenerator
from fra.application.forecast_service import (
    ForecastDraft,
    IssueForecast,
    ResolveForecast,
    ScoreForecast,
)
from fra.domain.errors import DomainValidationError, LookAheadEvidenceError
from fra.domain.forecasts import (
    ExposureEdge,
    ExposureGraph,
    ExposureNode,
    ExposureNodeKind,
    ForecastResolutionValue,
    ForecastStatus,
    ForecastTrigger,
    InvalidationCondition,
    ResolutionRule,
)
from fra.domain.ids import (
    EvidenceId,
    ExposureGraphId,
    InstrumentId,
    ResearchRunId,
)
from fra.domain.instruments import Currency
from fra.domain.market_data import MarketQuote
from fra.domain.research import Evidence
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


def test_issue_forecast_freezes_probability_and_rejects_look_ahead_evidence() -> None:
    forecasts = InMemoryForecastRepository()
    service = IssueForecast(forecasts, FixedClock(NOW), SequenceIdGenerator())
    draft = _draft()

    version = service.issue(draft, (_evidence(available_at=NOW),))

    assert version.version == 1
    assert version.status is ForecastStatus.ACTIVE
    assert version.probability == Decimal("0.35")
    assert forecasts.get(version.forecast.id).probability == Decimal("0.35")
    with pytest.raises(LookAheadEvidenceError):
        service.issue(draft, (_evidence(available_at=NOW + timedelta(seconds=1)),))


@pytest.mark.parametrize("probability", [Decimal("-0.01"), Decimal("1.01")])
def test_forecast_probability_must_be_inclusive_zero_to_one(probability: Decimal) -> None:
    with pytest.raises(DomainValidationError, match="probability"):
        _draft(probability=probability)


def test_binary_brier_score_is_deterministic_and_ambiguous_outcomes_remain_unscored() -> None:
    forecasts = InMemoryForecastRepository()
    outcomes = InMemoryOutcomeRepository()
    clock = FixedClock(NOW)
    ids = SequenceIdGenerator()
    forecast = IssueForecast(forecasts, clock, ids).issue(
        _draft(horizon_end=NOW), (_evidence(available_at=NOW),)
    )
    resolved = ResolveForecast(forecasts, outcomes, clock, ids).resolve(
        forecast.forecast.id,
        ForecastResolutionValue.TRUE,
        (_evidence(available_at=NOW),),
        resolver="fixture",
    )

    score = ScoreForecast(forecasts, outcomes, clock, ids).score(resolved.id)

    assert score.brier_score == Decimal("0.4225")
    ambiguous_forecast = IssueForecast(forecasts, clock, ids).issue(
        _draft(horizon_end=NOW), (_evidence(available_at=NOW),)
    )
    ambiguous = ResolveForecast(forecasts, outcomes, clock, ids).resolve(
        ambiguous_forecast.forecast.id,
        ForecastResolutionValue.AMBIGUOUS,
        (_evidence(available_at=NOW),),
        resolver="fixture",
        ambiguity_notes="Official observations conflict.",
    )
    ambiguous_score = ScoreForecast(forecasts, outcomes, clock, ids).score(ambiguous.id)

    assert ambiguous_score.brier_score is None
    assert len(outcomes.list()) == 2


def test_exposure_edges_require_evidence_confidence_and_invalidation() -> None:
    with pytest.raises(DomainValidationError):
        ExposureEdge(
            from_node="event:strait",
            to_node="commodity:oil",
            relationship="constrains",
            direction="positive",
            expected_lag="days",
            confidence=Decimal("0.7"),
            jurisdiction="GLOBAL",
            evidence_ids=(),
            invalidation_condition="Flows normalize",
        )

    graph = ExposureGraph(
        id=ExposureGraphId("graph_0001"),
        version=1,
        title="Fixture exposure path",
        nodes=(
            ExposureNode("event:strait", ExposureNodeKind.EVENT, "Strait restriction"),
            ExposureNode("commodity:oil", ExposureNodeKind.COMMODITY, "Oil"),
        ),
        edges=(
            ExposureEdge(
                from_node="event:strait",
                to_node="commodity:oil",
                relationship="constrains",
                direction="positive",
                expected_lag="days",
                confidence=Decimal("0.7"),
                jurisdiction="GLOBAL",
                evidence_ids=(EvidenceId("evidence_0001"),),
                invalidation_condition="Flows normalize",
            ),
        ),
        created_at=NOW,
    )

    assert graph.edges[0].confidence == Decimal("0.7")


def _draft(
    *,
    probability: Decimal = Decimal("0.35"),
    horizon_end: datetime = NOW + timedelta(days=30),
) -> ForecastDraft:
    return ForecastDraft(
        run_id=ResearchRunId("run_0001"),
        question="Will the fixture event occur?",
        hypothesis="The fixture event occurs before the horizon.",
        probability=probability,
        horizon_end=horizon_end,
        trigger=ForecastTrigger("Authoritative indicator crosses the threshold"),
        invalidation_conditions=(InvalidationCondition("Indicator normalizes"),),
        resolution_rule=ResolutionRule(
            version=1,
            statement="Resolve true if the official series crosses the threshold.",
            authoritative_source="fixture-official",
        ),
        transmission_path="indicator -> event",
        alternatives=("The indicator reverses",),
    )


def _evidence(*, available_at: datetime) -> Evidence[MarketQuote]:
    descriptor = SourceDescriptor(
        provider_id="fixture",
        adapter_version="1",
        source_kinds=frozenset({SourceKind.MARKET_DATA}),
        authority_class=AuthorityClass.OFFICIAL,
        point_in_time_support=True,
        allowed_usage_profiles=frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
        raw_retention=RawRetentionPolicy.PERMITTED,
        terms_url="https://fixture.test/terms",
        terms_reviewed_at=NOW.date(),
        independence_group="fixture",
    )
    envelope = DataEnvelope(
        value=MarketQuote(InstrumentId("fixture:asset"), Decimal("100"), Currency("USD"), NOW),
        descriptor=descriptor,
        provider_record_id="record-1",
        source="https://fixture.test/evidence",
        available_at=available_at,
        retrieved_at=available_at,
    )
    return Evidence(
        id=EvidenceId("evidence_0001"),
        run_id=ResearchRunId("run_0001"),
        kind=DataKind.MARKET_QUOTE,
        summary="Fixture official observation",
        envelope=envelope,
        knowledge_cutoff_at=available_at,
        created_at=available_at,
    )

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from fra.domain.errors import DomainValidationError, LookAheadEvidenceError
from fra.domain.ids import EvidenceId, InstrumentId, ResearchRunId
from fra.domain.instruments import Currency
from fra.domain.market_data import MarketQuote
from fra.domain.research import Evidence
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    DataKind,
    EvidenceRequirement,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    UsageProfile,
)

NOW = datetime(2026, 7, 18, 8, 30, tzinfo=UTC)


def descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        provider_id="fixture_market",
        adapter_version="1.0.0",
        source_kinds=frozenset({SourceKind.MARKET_DATA}),
        authority_class=AuthorityClass.AGGREGATOR,
        point_in_time_support=True,
        allowed_usage_profiles=frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
        raw_retention=RawRetentionPolicy.PROHIBITED,
        terms_url="https://example.test/terms",
        terms_reviewed_at=date(2026, 7, 1),
        independence_group="fixture-market",
    )


def quote() -> MarketQuote:
    return MarketQuote(
        instrument_id=InstrumentId("instrument_0001"),
        price=Decimal("65000.00"),
        currency=Currency("USD"),
        observed_at=NOW - timedelta(minutes=2),
    )


def test_data_envelope_rejects_look_ahead_evidence() -> None:
    with pytest.raises(LookAheadEvidenceError, match="available_at"):
        DataEnvelope(
            value=quote(),
            descriptor=descriptor(),
            provider_record_id="record-1",
            source="fixture://quote/1",
            available_at=NOW,
            retrieved_at=NOW,
            historical_cutoff_at=NOW - timedelta(seconds=1),
        )


def test_data_envelope_normalizes_provenance_without_external_payloads() -> None:
    envelope = DataEnvelope(
        value=quote(),
        descriptor=descriptor(),
        provider_record_id="record-1",
        source="fixture://quote/1",
        observed_at=NOW - timedelta(minutes=2),
        published_at=NOW - timedelta(minutes=1),
        available_at=NOW - timedelta(minutes=1),
        retrieved_at=NOW,
        content_hash="sha256:abc",
        request_fingerprint="sha256:def",
        usage_policy_id="fixture-policy-v1",
    )

    evidence = Evidence.from_envelope(
        id=EvidenceId("evidence_0001"),
        run_id=ResearchRunId("run_0001"),
        kind=DataKind.MARKET_QUOTE,
        summary="Bitcoin fixture quote",
        envelope=envelope,
        knowledge_cutoff_at=NOW,
        created_at=NOW,
    )

    assert evidence.provider_id == "fixture_market"
    assert evidence.value == quote()
    assert evidence.available_at == NOW - timedelta(minutes=1)


def test_evidence_requirement_requires_aware_cutoff() -> None:
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        EvidenceRequirement(
            data_kind=DataKind.MARKET_QUOTE,
            subject_ids=(InstrumentId("instrument_0001"),),
            allowed_usage_profile=UsageProfile.LOCAL_PERSONAL_RESEARCH,
            point_in_time_at=datetime(2026, 7, 18, 8),
        )

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.common.manifests import validate_source_manifest
from fra.adapters.fakes.documents import FakeDocumentProvider
from fra.adapters.in_memory.repositories import InMemorySourceStatusRepository
from fra.application.source_platform import SourceRegistry, SourceRouter
from fra.config.models import FRAConfig
from fra.domain.errors import DomainValidationError
from fra.domain.ids import InstrumentId
from fra.domain.shared import Failure, FailureKind, HealthState, HealthStatus
from fra.domain.sources import (
    AuthorityClass,
    DataKind,
    EvidenceRequirement,
    SourceRole,
    SourceStatusRecord,
    UsageProfile,
)
from fra.errors import ConfigurationError
from fra.factories.sources import BuiltInSourceFactory

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def _manifest(**overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "manifest_version": 1,
        "provider_id": "official_documents",
        "adapter_version": "1.0.0",
        "source_kinds": ["document"],
        "authority_class": "official",
        "point_in_time_support": True,
        "allowed_usage_profiles": ["local_personal_research"],
        "raw_retention": "permitted",
        "terms_url": "https://example.test/terms",
        "terms_reviewed_at": "2026-07-01",
        "independence_group": "official-publisher",
        "geographies": ["GLOBAL"],
        "frequencies": ["daily"],
        "normal_update_cadence": "daily",
        "maximum_expected_age_seconds": 86400,
        "required_attribution": "Example publisher",
    }
    manifest.update(overrides)
    return manifest


def test_manifest_validation_is_strict_and_fails_closed() -> None:
    descriptor = validate_source_manifest(_manifest())

    assert descriptor.provider_id == "official_documents"
    assert descriptor.terms_reviewed_at == date(2026, 7, 1)
    assert descriptor.maximum_expected_age == timedelta(days=1)

    with pytest.raises(DomainValidationError, match="unknown source usage rights"):
        validate_source_manifest(_manifest(allowed_usage_profiles=[]))
    with pytest.raises(DomainValidationError, match="unknown manifest option"):
        validate_source_manifest(_manifest(credential_value="must-not-be-accepted"))
    with pytest.raises(DomainValidationError, match="raw_retention"):
        validate_source_manifest(_manifest(raw_retention="unknown"))
    with pytest.raises(DomainValidationError, match="must use HTTPS"):
        validate_source_manifest(_manifest(terms_url="http://example.test/terms"))


def test_registry_rejects_duplicate_provider_ids() -> None:
    registry = SourceRegistry()
    registry.register(FakeDocumentProvider(), roles=(SourceRole.PRIMARY,))

    with pytest.raises(DomainValidationError, match="duplicate source provider ID"):
        registry.register(FakeDocumentProvider(), roles=(SourceRole.FALLBACK,))


def test_registry_rejects_a_manifest_capability_mismatch() -> None:
    provider = FakeDocumentProvider()
    registry = SourceRegistry()

    with pytest.raises(DomainValidationError, match="does not expose"):
        registry.register_descriptor(
            validate_source_manifest(_manifest(source_kinds=["economic_series"])),
            capabilities=provider.capabilities(),
            roles=(SourceRole.PRIMARY,),
        )


def test_source_factory_registers_coingecko_from_environment_without_exposing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = FRAConfig.model_validate(
        {
            "data_sources": {
                "coingecko": {
                    "enabled": True,
                    "options": {"api_key_env": "TEST_COINGECKO_KEY"},
                }
            }
        }
    )
    secret = "must-stay-out-of-errors"
    monkeypatch.setenv("TEST_COINGECKO_KEY", secret)
    raw_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    )
    try:
        registry = SourceRegistry()
        BuiltInSourceFactory.register_all(config, HttpClient(raw_client), registry)
    finally:
        asyncio.run(raw_client.aclose())

    assert registry.get("coingecko").descriptor.required_attribution == (
        "Data provided by CoinGecko"
    )
    monkeypatch.delenv("TEST_COINGECKO_KEY")
    second_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    )
    try:
        with pytest.raises(ConfigurationError) as captured:
            BuiltInSourceFactory.register_all(config, HttpClient(second_client), SourceRegistry())
    finally:
        asyncio.run(second_client.aclose())
    assert "TEST_COINGECKO_KEY" in str(captured.value)
    assert secret not in str(captured.value)


def test_router_records_selection_and_every_policy_exclusion() -> None:
    registry = SourceRegistry()
    selected = FakeDocumentProvider()
    registry.register(selected, roles=(SourceRole.PRIMARY, SourceRole.CROSS_CHECK))
    registry.register_descriptor(
        validate_source_manifest(
            _manifest(
                provider_id="wrong_usage",
                allowed_usage_profiles=["internal_research"],
            )
        ),
        capabilities=selected.capabilities(),
        roles=(SourceRole.FALLBACK,),
    )
    registry.register_descriptor(
        validate_source_manifest(_manifest(provider_id="no_vintages", point_in_time_support=False)),
        capabilities=selected.capabilities(),
        roles=(SourceRole.FALLBACK,),
    )
    registry.register_descriptor(
        validate_source_manifest(
            _manifest(
                provider_id="too_stale",
                maximum_expected_age_seconds=86400 * 7,
            )
        ),
        capabilities=selected.capabilities(),
        roles=(SourceRole.FALLBACK,),
    )
    registry.register_descriptor(
        validate_source_manifest(
            _manifest(provider_id="retention_forbidden", raw_retention="prohibited")
        ),
        capabilities=selected.capabilities(),
        roles=(SourceRole.FALLBACK,),
    )
    registry.register_descriptor(
        validate_source_manifest(
            _manifest(provider_id="low_authority", authority_class="secondary")
        ),
        capabilities=selected.capabilities(),
        roles=(SourceRole.FALLBACK,),
    )

    decision = SourceRouter(registry, policy_version="source-policy-v1").route(
        EvidenceRequirement(
            data_kind=DataKind.DOCUMENT,
            subject_ids=(InstrumentId("country:US"),),
            allowed_usage_profile=UsageProfile.LOCAL_PERSONAL_RESEARCH,
            geography_or_market="GLOBAL",
            maximum_age=timedelta(days=2),
            point_in_time_at=NOW,
            minimum_authority=AuthorityClass.OFFICIAL,
            raw_retention_required=True,
        )
    )

    assert decision.policy_version == "source-policy-v1"
    assert [item.provider_id for item in decision.selected] == ["fake_documents"]
    exclusions = {item.provider_id: item.exclusions for item in decision.candidates}
    assert exclusions["wrong_usage"] == ("usage_profile_incompatible",)
    assert exclusions["no_vintages"] == ("point_in_time_unavailable",)
    assert exclusions["too_stale"] == ("freshness_insufficient",)
    assert exclusions["retention_forbidden"] == ("raw_retention_incompatible",)
    assert exclusions["low_authority"] == ("authority_insufficient",)


def test_router_reports_when_independent_source_requirement_is_unmet() -> None:
    registry = SourceRegistry()
    registry.register(FakeDocumentProvider(), roles=(SourceRole.PRIMARY,))

    decision = SourceRouter(registry, policy_version="source-policy-v1").route(
        EvidenceRequirement(
            data_kind=DataKind.DOCUMENT,
            subject_ids=(),
            allowed_usage_profile=UsageProfile.LOCAL_PERSONAL_RESEARCH,
            minimum_independent_sources=2,
        )
    )

    assert decision.warnings == ("minimum independent sources unmet: required 2, found 1",)


def test_router_rejects_last_known_unavailable_or_exhausted_sources() -> None:
    registry = SourceRegistry()
    registry.register(FakeDocumentProvider(), roles=(SourceRole.PRIMARY,))
    statuses = InMemorySourceStatusRepository()
    failure = Failure(FailureKind.QUOTA_EXCEEDED, "quota exhausted", retryable=True)
    health = HealthStatus(
        HealthState.UNAVAILABLE,
        NOW,
        "quota exhausted",
        failure=failure,
    )
    statuses.save(SourceStatusRecord("fake_documents", NOW, health))

    decision = SourceRouter(
        registry,
        policy_version="source-policy-v1",
        statuses=statuses,
    ).route(
        EvidenceRequirement(
            data_kind=DataKind.DOCUMENT,
            subject_ids=(),
            allowed_usage_profile=UsageProfile.LOCAL_PERSONAL_RESEARCH,
        )
    )

    assert decision.candidates[0].exclusions == ("quota_unavailable",)

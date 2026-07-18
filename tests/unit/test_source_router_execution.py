import asyncio
from datetime import date

from fra.application.source_platform import SourceRegistry, SourceRouter
from fra.domain.errors import CapabilityUnavailableError
from fra.domain.ids import InstrumentId
from fra.domain.market_data import MarketDataCapabilities
from fra.domain.sources import (
    AuthorityClass,
    DataKind,
    EvidenceRequirement,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    SourceRole,
    UsageProfile,
)


class _Source:
    def __init__(self, provider_id: str, authority: AuthorityClass, *, fails: bool = False) -> None:
        self.provider_id = provider_id
        self.authority = authority
        self.fails = fails
        self.calls = 0

    def descriptor(self) -> SourceDescriptor:
        return SourceDescriptor(
            provider_id=self.provider_id,
            adapter_version="1",
            source_kinds=frozenset({SourceKind.MARKET_DATA}),
            authority_class=self.authority,
            point_in_time_support=True,
            allowed_usage_profiles=frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
            raw_retention=RawRetentionPolicy.PERMITTED,
            terms_url=f"https://{self.provider_id}.example.test/terms",
            terms_reviewed_at=date(2026, 1, 1),
            independence_group=self.provider_id,
        )

    def capabilities(self) -> MarketDataCapabilities:
        return MarketDataCapabilities(quotes=True, history=True)

    async def fetch(self) -> str:
        self.calls += 1
        if self.fails:
            raise CapabilityUnavailableError(f"{self.provider_id} unavailable")
        return self.provider_id


def _requirement() -> EvidenceRequirement:
    return EvidenceRequirement(
        DataKind.MARKET_QUOTE,
        (InstrumentId("crypto:bitcoin"),),
        UsageProfile.LOCAL_PERSONAL_RESEARCH,
        minimum_authority=AuthorityClass.AGGREGATOR,
    )


async def _fetch(adapter: object) -> str:
    assert isinstance(adapter, _Source)
    return await adapter.fetch()


def test_router_executes_fallback_only_after_selected_primary_fails() -> None:
    primary = _Source("primary", AuthorityClass.OFFICIAL, fails=True)
    fallback = _Source("fallback", AuthorityClass.AGGREGATOR)
    registry = SourceRegistry()
    registry.register(primary, roles=(SourceRole.PRIMARY,))
    registry.register(fallback, roles=(SourceRole.FALLBACK,))
    router = SourceRouter(registry, policy_version="test.v1")

    result = asyncio.run(router.execute(_requirement(), _fetch))

    assert [item.provider_id for item in result.values] == ["fallback"]
    assert [item.provider_id for item in result.failures] == ["primary"]
    assert primary.calls == 1
    assert fallback.calls == 1


def test_router_never_executes_policy_excluded_adapter() -> None:
    selected = _Source("selected", AuthorityClass.OFFICIAL)
    excluded = _Source("excluded", AuthorityClass.SECONDARY)
    registry = SourceRegistry()
    registry.register(selected, roles=(SourceRole.PRIMARY,))
    registry.register(excluded, roles=(SourceRole.FALLBACK,))
    router = SourceRouter(registry, policy_version="test.v1")

    result = asyncio.run(router.execute(_requirement(), _fetch))

    assert [item.provider_id for item in result.values] == ["selected"]
    assert excluded.calls == 0
    excluded_candidate = next(
        item for item in result.decision.candidates if item.provider_id == "excluded"
    )
    assert excluded_candidate.exclusions == ("authority_insufficient",)

import httpx
import pytest

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.fakes.market_data import FakeMarketDataProvider
from fra.application.source_platform import SourceRegistry
from fra.config.models import FRAConfig
from fra.domain.errors import DomainValidationError
from fra.errors import ConfigurationError
from fra.factories.source_plugins import SourcePluginDiscovery
from fra.factories.sources import BuiltInSourceFactory


class _EntryPoint:
    def __init__(self, name: str, factory: object) -> None:
        self.name = name
        self._factory = factory

    def load(self) -> object:
        return self._factory


def test_enabled_fixture_plugin_registers_and_disabled_plugin_is_not_loaded() -> None:
    loads = 0

    def factory() -> FakeMarketDataProvider:
        nonlocal loads
        loads += 1
        return FakeMarketDataProvider()

    discovery = SourcePluginDiscovery(lambda: (_EntryPoint("fixture", factory),))
    enabled = FRAConfig.model_validate(
        {
            "data_sources": {
                "plugins": {
                    "fixture": {
                        "enabled": True,
                        "roles": ["fallback"],
                        "allowed_usage_profiles": ["local_personal_research"],
                    }
                }
            }
        }
    )
    disabled = FRAConfig.model_validate(
        {"data_sources": {"plugins": {"fixture": {"enabled": False}}}}
    )

    raw = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    try:
        registry = SourceRegistry()
        BuiltInSourceFactory.register_all(
            enabled, HttpClient(raw), registry, plugin_discovery=discovery
        )
        disabled_registry = SourceRegistry()
        BuiltInSourceFactory.register_all(
            disabled, HttpClient(raw), disabled_registry, plugin_discovery=discovery
        )
    finally:
        import asyncio

        asyncio.run(raw.aclose())

    assert registry.get("fake_market").descriptor.provider_id == "fake_market"
    assert disabled_registry.list() == ()
    assert loads == 1


def test_plugin_discovery_rejects_duplicate_names_and_provider_ids() -> None:
    duplicate_names = SourcePluginDiscovery(
        lambda: (
            _EntryPoint("fixture", FakeMarketDataProvider),
            _EntryPoint("fixture", FakeMarketDataProvider),
        )
    )
    with pytest.raises(ConfigurationError, match="duplicate source plugin entry point"):
        duplicate_names.load_enabled(frozenset({"fixture"}))

    invalid = SourcePluginDiscovery(lambda: (_EntryPoint("invalid", lambda: object()),))
    with pytest.raises(DomainValidationError, match="does not expose"):
        invalid.load_enabled(frozenset({"invalid"}))

"""Configuration-driven construction of built-in source adapters."""

import os
from typing import Protocol, cast

from fra.adapters.data_sources.common.http import HttpClient
from fra.adapters.data_sources.documents.manual import ManualDocument, ManualDocumentAdapter
from fra.adapters.data_sources.documents.opendart import OpenDartAdapter
from fra.adapters.data_sources.documents.rss_atom import RssAtomDocumentAdapter
from fra.adapters.data_sources.documents.sec_edgar import SECEdgarAdapter
from fra.adapters.data_sources.economic.eia import EIAEnergyAdapter
from fra.adapters.data_sources.economic.fred import FREDVintageAdapter
from fra.adapters.data_sources.economic.pink_sheet import WorldBankPinkSheetAdapter
from fra.adapters.data_sources.economic.world_bank import WorldBankIndicatorsAdapter
from fra.adapters.data_sources.market.coingecko import CoinGeckoMarketDataAdapter
from fra.adapters.data_sources.market.yfinance import YFinanceMarketDataAdapter
from fra.config.models import FRAConfig
from fra.config.models import SourceRole as ConfigSourceRole
from fra.config.models import UsageProfile as ConfigUsageProfile
from fra.domain.sources import SourceDescriptor, SourceRole, UsageProfile
from fra.errors import ConfigurationError
from fra.factories.source_plugins import SourcePluginDiscovery


class BuiltInSourceFactory:
    @staticmethod
    def register_all(
        config: FRAConfig,
        client: HttpClient,
        registry: "SourceRegistrar",
        *,
        plugin_discovery: SourcePluginDiscovery | None = None,
    ) -> None:
        sources = config.data_sources
        if sources.yfinance.enabled:
            yfinance_config = sources.yfinance
            _register(
                registry,
                YFinanceMarketDataAdapter(),
                yfinance_config.roles,
                yfinance_config.allowed_usage_profiles,
                config,
            )
        if sources.coingecko.enabled:
            coingecko_config = sources.coingecko
            key_name = coingecko_config.options.api_key_env
            if key_name is None:
                raise ConfigurationError(
                    "CoinGecko Demo requires data_sources.coingecko.options.api_key_env"
                )
            api_key = os.environ.get(key_name)
            if not api_key:
                raise ConfigurationError(
                    f"CoinGecko Demo credential environment variable is not set: {key_name}"
                )
            coingecko_adapter = CoinGeckoMarketDataAdapter(
                client,
                api_key=api_key,
                base_url=str(coingecko_config.options.base_url),
            )
            _register(
                registry,
                coingecko_adapter,
                coingecko_config.roles,
                coingecko_config.allowed_usage_profiles,
                config,
            )
        if sources.manual_documents.enabled:
            manual_config = sources.manual_documents
            manual_adapter = ManualDocumentAdapter(
                documents=tuple(
                    ManualDocument(
                        provider_record_id=document.provider_record_id,
                        title=document.title,
                        url=str(document.url),
                        published_at=document.published_at,
                        updated_at=document.updated_at,
                        corrects_provider_record_id=document.corrects_provider_record_id,
                        withdrawn=document.withdrawn,
                    )
                    for document in manual_config.documents
                ),
                client=client,
                terms_url=str(manual_config.terms_url),
                terms_reviewed_at=manual_config.terms_reviewed_at,
                allowed_usage_profiles=tuple(manual_config.allowed_usage_profiles),
            )
            _register(
                registry,
                manual_adapter,
                manual_config.roles,
                manual_config.allowed_usage_profiles,
                config,
            )
        if sources.rss_atom.enabled:
            rss_config = sources.rss_atom
            rss_adapter = RssAtomDocumentAdapter(
                feed_url=str(rss_config.options.feed_url),
                client=client,
                terms_url=str(rss_config.terms_url),
                terms_reviewed_at=rss_config.terms_reviewed_at,
                allowed_usage_profiles=tuple(rss_config.allowed_usage_profiles),
            )
            _register(
                registry,
                rss_adapter,
                rss_config.roles,
                rss_config.allowed_usage_profiles,
                config,
            )
        if sources.world_bank_indicators.enabled:
            world_bank_config = sources.world_bank_indicators
            world_bank_adapter = WorldBankIndicatorsAdapter(
                client, base_url=str(world_bank_config.options.base_url)
            )
            _register(
                registry,
                world_bank_adapter,
                world_bank_config.roles,
                world_bank_config.allowed_usage_profiles,
                config,
            )
        if sources.eia.enabled:
            eia_config = sources.eia
            key_name = eia_config.options.api_key_env
            if key_name is None or not os.environ.get(key_name):
                raise ConfigurationError(
                    "EIA requires a populated data_sources.eia.options.api_key_env"
                )
            _register(
                registry,
                EIAEnergyAdapter(
                    client,
                    api_key=os.environ[key_name],
                    base_url=str(eia_config.options.base_url),
                ),
                eia_config.roles,
                eia_config.allowed_usage_profiles,
                config,
            )
        if sources.world_bank_pink_sheet.enabled:
            pink_config = sources.world_bank_pink_sheet
            _register(
                registry,
                WorldBankPinkSheetAdapter(
                    client, workbook_url=str(pink_config.options.workbook_url)
                ),
                pink_config.roles,
                pink_config.allowed_usage_profiles,
                config,
            )
        if sources.fred_alfred.enabled:
            fred_config = sources.fred_alfred
            key_name = fred_config.options.api_key_env
            if key_name is None or not os.environ.get(key_name):
                raise ConfigurationError(
                    "FRED/ALFRED requires a populated data_sources.fred_alfred.options.api_key_env"
                )
            _register(
                registry,
                FREDVintageAdapter(
                    client,
                    api_key=os.environ[key_name],
                    base_url=str(fred_config.options.base_url),
                ),
                fred_config.roles,
                fred_config.allowed_usage_profiles,
                config,
            )
        if sources.sec_edgar.enabled:
            sec_config = sources.sec_edgar
            user_agent = sec_config.options.user_agent
            if user_agent is None:
                raise ConfigurationError(
                    "SEC EDGAR requires data_sources.sec_edgar.options.user_agent"
                )
            _register(
                registry,
                SECEdgarAdapter(
                    client,
                    user_agent=user_agent,
                    base_url=str(sec_config.options.base_url),
                ),
                sec_config.roles,
                sec_config.allowed_usage_profiles,
                config,
            )
        if sources.opendart.enabled:
            dart_config = sources.opendart
            key_name = dart_config.options.api_key_env
            if key_name is None or not os.environ.get(key_name):
                raise ConfigurationError(
                    "OpenDART requires a populated data_sources.opendart.options.api_key_env"
                )
            _register(
                registry,
                OpenDartAdapter(
                    client,
                    api_key=os.environ[key_name],
                    base_url=str(dart_config.options.base_url),
                ),
                dart_config.roles,
                dart_config.allowed_usage_profiles,
                config,
            )
        discovery = plugin_discovery or SourcePluginDiscovery()
        enabled_plugins = frozenset(
            name for name, plugin_config in sources.plugins.items() if plugin_config.enabled
        )
        for name, adapter in discovery.load_enabled(enabled_plugins):
            plugin_config = sources.plugins[name]
            _register(
                registry,
                cast(_SourceAdapter, adapter),
                plugin_config.roles,
                plugin_config.allowed_usage_profiles,
                config,
            )


class SourceRegistrar(Protocol):
    def register(self, adapter: object, *, roles: tuple[SourceRole, ...]) -> None: ...


class _SourceAdapter(Protocol):
    def descriptor(self) -> SourceDescriptor: ...

    def capabilities(self) -> object: ...


def _register(
    registry: SourceRegistrar,
    adapter: _SourceAdapter,
    roles: list[ConfigSourceRole],
    configured_usage: list[ConfigUsageProfile],
    config: FRAConfig,
) -> None:
    descriptor = adapter.descriptor()
    declared = frozenset(UsageProfile(item) for item in configured_usage)
    if not declared <= descriptor.allowed_usage_profiles:
        raise ConfigurationError(
            f"source {descriptor.provider_id} configuration broadens manifest usage rights"
        )
    active = UsageProfile(config.workspace.usage_profile)
    if active not in declared:
        raise ConfigurationError(
            f"source {descriptor.provider_id} configuration does not allow active workspace "
            f"usage profile {active.value}"
        )
    if active not in descriptor.allowed_usage_profiles:
        raise ConfigurationError(
            f"source {descriptor.provider_id} does not permit workspace usage profile "
            f"{active.value}"
        )
    registry.register(adapter, roles=tuple(SourceRole(item) for item in roles))

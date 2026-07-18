"""Strict models for the FRA TOML boundary."""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
EnvironmentVariableName = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", min_length=1),
]
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://[^\s]+$")]
PositiveInteger = Annotated[int, Field(strict=True, gt=0)]
StrictBoolean = Annotated[bool, Field(strict=True)]
SourceRole = Literal["primary", "fallback", "cross_check", "discovery"]
UsageProfile = Literal["local_personal_research", "internal_research", "commercial"]


def _primary_roles() -> list[SourceRole]:
    return ["primary"]


def _fallback_roles() -> list[SourceRole]:
    return ["fallback"]


def _market_data_roles() -> list[SourceRole]:
    return ["primary", "cross_check"]


def _personal_usage() -> list[UsageProfile]:
    return ["local_personal_research"]


def _all_usage_profiles() -> list[UsageProfile]:
    return ["local_personal_research", "internal_research", "commercial"]


class StrictConfigModel(BaseModel):
    """Reject options that FRA does not understand."""

    model_config = ConfigDict(extra="forbid", validate_default=True)


class WorkspaceConfig(StrictConfigModel):
    root: Path = Path("fra-workspace")
    usage_profile: UsageProfile = "local_personal_research"


class AgentOptions(StrictConfigModel):
    binary: NonEmptyString = "codex"
    profile: NonEmptyString | None = None
    sandbox: Literal["read-only", "workspace-write"] = "read-only"


class AgentConfig(StrictConfigModel):
    provider: Literal["codex_cli", "claude_cli", "antigravity_cli"] = "codex_cli"
    timeout_seconds: PositiveInteger = 900
    options: AgentOptions = Field(default_factory=AgentOptions)


class CoinGeckoOptions(StrictConfigModel):
    base_url: HttpsUrl = "https://api.coingecko.com/api/v3"
    api_key_env: EnvironmentVariableName | None = None


class EiaOptions(StrictConfigModel):
    base_url: HttpsUrl = "https://api.eia.gov/v2/petroleum/stoc/wstk/data"
    api_key_env: EnvironmentVariableName | None = None


class WorldBankOptions(StrictConfigModel):
    base_url: HttpsUrl = "https://api.worldbank.org/v2"


class FredOptions(StrictConfigModel):
    base_url: HttpsUrl = "https://api.stlouisfed.org/fred/series/observations"
    api_key_env: EnvironmentVariableName | None = None


class PinkSheetOptions(StrictConfigModel):
    workbook_url: HttpsUrl = (
        "https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-"
        "0350012021/related/CMO-Historical-Data-Monthly.xlsx"
    )


class SecEdgarOptions(StrictConfigModel):
    base_url: HttpsUrl = "https://data.sec.gov"
    user_agent: NonEmptyString | None = None


class OpenDartOptions(StrictConfigModel):
    base_url: HttpsUrl = "https://engopendart.fss.or.kr/engapi"
    api_key_env: EnvironmentVariableName | None = None


class EmptySourceOptions(StrictConfigModel):
    pass


class CoinGeckoSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_market_data_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_personal_usage)
    options: CoinGeckoOptions = Field(default_factory=CoinGeckoOptions)


class YFinanceSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_fallback_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_personal_usage)
    options: EmptySourceOptions = Field(default_factory=EmptySourceOptions)


class EiaSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_primary_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_all_usage_profiles)
    options: EiaOptions = Field(default_factory=EiaOptions)


class WorldBankSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_primary_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_all_usage_profiles)
    options: WorldBankOptions = Field(default_factory=WorldBankOptions)


class FredSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_primary_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_all_usage_profiles)
    options: FredOptions = Field(default_factory=FredOptions)


class PinkSheetSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_primary_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_all_usage_profiles)
    options: PinkSheetOptions = Field(default_factory=PinkSheetOptions)


class SecEdgarSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_primary_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_all_usage_profiles)
    options: SecEdgarOptions = Field(default_factory=SecEdgarOptions)


class OpenDartSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_primary_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_all_usage_profiles)
    options: OpenDartOptions = Field(default_factory=OpenDartOptions)


class PluginSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_fallback_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_personal_usage)


class ManualDocumentConfig(StrictConfigModel):
    provider_record_id: NonEmptyString
    title: NonEmptyString
    url: HttpsUrl
    published_at: datetime | None = None
    updated_at: datetime | None = None
    corrects_provider_record_id: NonEmptyString | None = None
    withdrawn: StrictBoolean = False


class ManualDocumentsSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_primary_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_all_usage_profiles)
    terms_url: HttpsUrl = "https://example.invalid/manual-source-terms"
    terms_reviewed_at: date = date(1970, 1, 1)
    documents: list[ManualDocumentConfig] = Field(default_factory=list)


class RssAtomOptions(StrictConfigModel):
    feed_url: HttpsUrl = "https://example.invalid/feed.xml"


class RssAtomSourceConfig(StrictConfigModel):
    enabled: StrictBoolean = False
    roles: list[SourceRole] = Field(default_factory=_primary_roles)
    allowed_usage_profiles: list[UsageProfile] = Field(default_factory=_all_usage_profiles)
    terms_url: HttpsUrl = "https://www.rssboard.org/rss-specification"
    terms_reviewed_at: date = date(1970, 1, 1)
    options: RssAtomOptions = Field(default_factory=RssAtomOptions)


class DataSourcesConfig(StrictConfigModel):
    manual_documents: ManualDocumentsSourceConfig = Field(
        default_factory=ManualDocumentsSourceConfig
    )
    rss_atom: RssAtomSourceConfig = Field(default_factory=RssAtomSourceConfig)
    coingecko: CoinGeckoSourceConfig = Field(default_factory=CoinGeckoSourceConfig)
    yfinance: YFinanceSourceConfig = Field(default_factory=YFinanceSourceConfig)
    eia: EiaSourceConfig = Field(default_factory=EiaSourceConfig)
    world_bank_indicators: WorldBankSourceConfig = Field(default_factory=WorldBankSourceConfig)
    world_bank_pink_sheet: PinkSheetSourceConfig = Field(default_factory=PinkSheetSourceConfig)
    fred_alfred: FredSourceConfig = Field(default_factory=FredSourceConfig)
    sec_edgar: SecEdgarSourceConfig = Field(default_factory=SecEdgarSourceConfig)
    opendart: OpenDartSourceConfig = Field(default_factory=OpenDartSourceConfig)
    plugins: dict[str, PluginSourceConfig] = Field(default_factory=dict)


class SourcePolicyConfig(StrictConfigModel):
    material_claim_minimum_authority: Literal["official_or_corroborated"] = (
        "official_or_corroborated"
    )
    unknown_usage_rights: Literal["reject"] = "reject"
    discovery_only_can_support_material_claims: StrictBoolean = False
    require_point_in_time_for_forecasts: StrictBoolean = True


class DashboardConfig(StrictConfigModel):
    refresh_seconds: PositiveInteger = 5
    plain_text: StrictBoolean = False


class StorageOptions(StrictConfigModel):
    root: Path = Path("fra-workspace")


class StorageConfig(StrictConfigModel):
    provider: Literal["markdown"] = "markdown"
    options: StorageOptions = Field(default_factory=StorageOptions)


class FRAConfig(StrictConfigModel):
    """Validated root configuration."""

    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    data_sources: DataSourcesConfig = Field(default_factory=DataSourcesConfig)
    source_policy: SourcePolicyConfig = Field(default_factory=SourcePolicyConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

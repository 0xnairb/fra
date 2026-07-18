# Components and Contracts

## Component Model

The following interfaces are conceptual contracts. Exact Python syntax may change during implementation, but dependency direction and responsibilities should remain stable.

## Composition Root

File: `src/fra/bootstrap.py`

Responsibilities:

1. load validated configuration;
2. invoke adapter factories;
3. construct application services;
4. register research-domain and market packs;
5. pass use cases to CLI handlers;
6. own adapter shutdown.

No other module should create concrete adapters directly.

## Configuration

Configuration is provider-neutral at the top level and provider-specific only inside an adapter options block.

```toml
[workspace]
root = "./fra-workspace"
usage_profile = "local_personal_research"

[agent]
provider = "codex_cli"
timeout_seconds = 900

[agent.options]
binary = "codex"
profile = "fra"
sandbox = "read-only"

[data_sources.coingecko]
enabled = true
roles = ["primary", "cross_check"]

[data_sources.coingecko.options]
base_url = "https://api.coingecko.com/api/v3"
api_key_env = "COINGECKO_DEMO_API_KEY"

[data_sources.yfinance]
enabled = false
roles = ["fallback"]
allowed_usage_profiles = ["local_personal_research"]

[data_sources.eia]
enabled = true
roles = ["primary"]

[data_sources.eia.options]
api_key_env = "EIA_API_KEY"

[data_sources.world_bank_indicators]
enabled = true
roles = ["primary"]

[source_policy]
material_claim_minimum_authority = "official_or_corroborated"
unknown_usage_rights = "reject"
discovery_only_can_support_material_claims = false
require_point_in_time_for_forecasts = true

[dashboard]
refresh_seconds = 5
plain_text = false

[storage]
provider = "markdown"

[storage.options]
root = "./fra-workspace"
```

Secrets are referenced by environment-variable name. They are never written into research Markdown.

Configuration enables sources; it does not hard-code them into a workflow. At bootstrap, the source factory validates each adapter manifest against the workspace usage profile and registers its typed capabilities. A rejected source cannot be selected later by an agent prompt.

## `AgentBackend`

Purpose: provide vendor-neutral structured agent execution.

```python
class AgentBackend(Protocol):
    def capabilities(self) -> AgentCapabilities: ...
    async def health(self) -> HealthStatus: ...
    async def execute(
        self,
        request: AgentStageRequest,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult: ...
    async def resume(
        self,
        provider_session_id: str,
        request: AgentStageRequest,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult: ...
```

`AgentStageRequest` includes:

- run and stage IDs;
- stage type: plan, analyze, verify, or synthesize;
- rendered instructions;
- evidence bundle;
- output schema path or schema value;
- working directory;
- timeout;
- allowed tools or capabilities;
- optional provider session ID.

`AgentStageResult` includes:

- normalized status;
- structured output;
- final text when applicable;
- provider session ID;
- provider name, CLI version, and selected model when reported;
- start/end time and duration;
- normalized usage or cost when reported;
- warnings and typed failure.

### CLI agent adapters

Each CLI adapter owns:

- binary discovery and version detection;
- authentication health commands when supported;
- command argument construction;
- provider-specific permission and sandbox flags;
- JSON/JSONL/text event parsing;
- session resumption syntax;
- process cancellation;
- provider error classification.

Capabilities are detected rather than inferred from provider name. Antigravity may report `structured_output = false`; the orchestrator can then reject schema-critical stages or use a bounded text-to-structure repair path.

## Data-Source Adapter Model

FRA supports many sources through a shared descriptor and small typed capability ports. It does not use one `fetch(kind, params) -> dict` interface because that would move vendor interpretation into workflows.

### `SourceDescriptor`

Every source adapter exposes machine-readable operational and policy metadata:

```text
provider_id
adapter_version
source_kinds
authority_class
geographies and markets
frequencies and history bounds
point_in_time_support
authentication_kind and credential environment names
quota and normal update cadence
allowed_usage_profiles
attribution and raw-retention policy
terms_url and terms_reviewed_at
experimental and discovery_only flags
```

The descriptor is configuration and adapter metadata, not evidence. Unknown usage rights fail closed.

### Typed provider ports

| Port | Normalized responsibility |
| --- | --- |
| `MarketDataProvider` | instruments, quotes, bars, actions, and market snapshots |
| `EconomicSeriesProvider` | series metadata, observations, releases, and vintages |
| `DocumentProvider` | permitted document search or fetch, publication metadata, and corrections |
| `EventProvider` | event discovery, actors, locations, classifications, and supporting mentions |
| `FundamentalsProvider` | filing facts, statements, segments, and report metadata |
| `TradeFlowProvider` | reporter-partner-product flows and classification versions |
| `PhysicalFlowProvider` | production, inventory, demand, refinery, port, and passage observations |
| `PositioningProvider` | open interest and participant-position aggregates |
| `OnChainDataProvider` | network, supply, fee, activity, and exchange metrics |

An adapter may implement more than one port, but each method accepts and returns FRA-owned typed requests and values.

```python
class MarketDataProvider(Protocol):
    def descriptor(self) -> SourceDescriptor: ...
    def capabilities(self) -> MarketDataCapabilities: ...
    async def health(self) -> HealthStatus: ...
    async def resolve_instrument(self, query: InstrumentQuery) -> list[InstrumentMatch]: ...
    async def quote(self, instrument: InstrumentRef) -> DataEnvelope[MarketQuote]: ...
    async def history(self, request: HistoryRequest) -> DataEnvelope[MarketSeries]: ...
```

### `EvidenceRequirement`

Workflows request evidence without naming a provider:

```text
data_kind
subject IDs and acceptable aliases
fields and units
geography or market
time range and resolution
maximum age
point_in_time_at
minimum authority
minimum independent sources
allowed usage profile
raw-retention requirement
```

### `DataEnvelope`

Every normalized response includes its value plus provenance:

```text
provider and adapter version
provider record and subject IDs
FRA subject IDs
source URL or description
authority class and independence group
observed_at or event_time
period_start and period_end
published_at
available_at
effective_at
revised_at and vintage
retrieved_at
timezone, currency, units, and classification version
is_stale and is_delayed
content hash and request fingerprint
usage_policy_id and required attribution
warnings and missing fields
```

The time fields are intentionally separate. A CFTC report, for example, observes Tuesday positions but is normally first available on Friday; using Tuesday as `available_at` would introduce look-ahead leakage.

### `SourceRegistry`

The registry contains constructed adapters indexed by typed capabilities. Built-ins register during bootstrap; future packages may register through a `fra.data_sources` entry-point group. Duplicate provider IDs or incompatible manifest versions fail startup.

### `SourceRouter`

The router filters sources by capability, usage rights, scope, resolution, history, authority, freshness, point-in-time cutoff, cost, quota, and health. It assigns one of four explicit roles: `primary`, `fallback`, `cross_check`, or `discovery`.

Routing produces a decision record containing candidates, exclusions, selected providers, and policy version. Sources remain separate evidence when they disagree. The router never silently averages values or downgrades from official to unofficial authority.

### Initial adapters

| Adapter | Role |
| --- | --- |
| `ManualDocumentAdapter`, `RssAtomDocumentAdapter` | MVP official and user-supplied documents |
| `CoinGeckoMarketDataAdapter` | conditional local-evaluation crypto prices |
| `YFinanceMarketDataAdapter` | conditional personal-research fallback only |
| `WorldBankIndicatorsAdapter` | MVP structural macro and country indicators |
| `EiaPhysicalFlowAdapter` | MVP physical energy data for crisis research |
| `FredEconomicSeriesAdapter` | MVP macro series and ALFRED vintages |
| `WorldBankPinkSheetAdapter` | MVP monthly commodity benchmarks |
| `SecEdgarFundamentalsAdapter` | MVP US filings and XBRL facts |
| `GdeltEventAdapter` | experimental discovery, never sole material support |

The researched provider matrix and future candidates are in [Data source strategy and feasibility](08-data-source-strategy.md).

## Repository Ports

### `ResearchRepository`

```python
class ResearchRepository(Protocol):
    def create(self, run: ResearchRun) -> None: ...
    def get(self, run_id: ResearchRunId) -> ResearchRun: ...
    def save(self, run: ResearchRun) -> None: ...
    def list(self, query: ResearchRunQuery) -> list[ResearchRunSummary]: ...
    def add_evidence(self, run_id: ResearchRunId, item: Evidence) -> None: ...
    def add_claim(self, run_id: ResearchRunId, claim: Claim) -> None: ...
    def save_report(self, run_id: ResearchRunId, report: ResearchReport) -> None: ...
```

### `ProfileRepository`

Stores the inputs required for suitability-aware research without coupling them to any one allocation model.

### `PortfolioRepository`

Stores observed portfolios and proposed research allocations. These are signaling inputs and results, not external account state.

### `SignalRepository`

Stores immutable signal versions, stance, strength, confidence, horizon, knowledge cutoff, evidence, invalidation conditions, freshness, and lifecycle state.

### `SourceStatusRepository`

Stores the result of an explicit source check, including provider, checked time, normalized health, quota or rate-limit warning, and error classification. The dashboard reads the last persisted check and never performs one implicitly.

### `ForecastRepository`

Stores immutable forecast versions, their stated horizon, probability, evidence cutoff, invalidation conditions, and lifecycle state. Corrections create a new version instead of rewriting what FRA originally knew.

### `ExposureGraphRepository`

Stores versioned event-to-transmission-to-industry-to-instrument relationships, including edge direction, lag, confidence, jurisdiction, and supporting evidence. The graph is a Markdown-backed domain model, not a graph database requirement.

### `OutcomeRepository`

Stores resolution observations and deterministic scores for forecasts. Outcomes remain separate from forecasts so later facts cannot leak into the original record.

## `ResearchOrchestrator`

Purpose: own the workflow state machine.

Responsibilities:

- choose a research workflow from `ResearchRegistry`;
- execute valid state transitions;
- persist after every completed stage;
- invoke the agent backend through its port;
- invoke evidence collection and verification services;
- persist any resulting signal before reporting stage completion;
- issue, monitor, resolve, and score forecasts through explicit use cases;
- stop for user input when required;
- resume from durable state;
- enforce maximum research and repair iterations.

It must not know whether the agent is Codex or whether storage is Markdown.

## `SignalService`

Purpose: validate and lifecycle research signals independently from their CLI presentation.

Responsibilities:

- require evidence and an explicit knowledge cutoff;
- create immutable signal versions;
- calculate freshness and next review time;
- transition signals to weakened, invalidated, expired, or resolved;
- persist through `SignalRepository`;
- expose no external account or action capability.

## `DashboardService`

Purpose: build a read-only `DashboardSnapshot` from persisted application state.

The snapshot contains active signals, forecasts, risk-watch entries, source status, and recent research. It carries stable artifact references so the CLI can show the corresponding Markdown result. The service does not render terminal tables, read filesystem paths directly, call agents, or refresh sources.

## `ResearchRegistry`

Maps a research mandate type to an asset-domain workflow.

```text
crypto_market_timing -> CryptoMarketTimingWorkflow
asset_allocation     -> AssetAllocationWorkflow
crisis_impact        -> CrisisImpactWorkflow
```

Each workflow declares:

- required user inputs;
- allowed asset classes and markets;
- typical data requirements;
- deterministic calculations;
- verification rules;
- final report sections.

## `EvidenceService`

Responsibilities:

- convert plan data requirements into provider requests;
- resolve instruments and surface ambiguity;
- ask `SourceRouter` for compatible typed providers;
- call market, macro, filing, event, trade, physical-flow, positioning, and on-chain ports;
- normalize and deduplicate evidence;
- preserve conflicting observations and independence groups;
- calculate freshness and expiry;
- persist the routing decision, request fingerprint, and source policy version;
- persist evidence before returning it to the agent;
- produce bounded evidence bundles.

## `VerificationService`

Performs deterministic checks before optional agent critique.

Checks include:

- every material claim cites existing evidence IDs;
- citations support the claimed instrument and time window;
- numerical values match evidence within declared tolerance;
- price-sensitive evidence is fresh enough for the workflow;
- the evidence was available at or before the research or forecast cutoff;
- the source usage profile and retention policy permit the requested use;
- discovery-only sources do not solely support material claims;
- nominally separate citations are not copies from one independence group;
- units, currencies, and percentage bases are explicit;
- probability language does not imply certainty;
- allocation weights sum to the expected total;
- unsupported claims and contradictions are listed.

## Analytics Components

Analytics are pure deterministic functions.

| Component | Initial outputs |
| --- | --- |
| `ReturnsCalculator` | absolute and percentage returns |
| `VolatilityCalculator` | annualized volatility and downside volatility |
| `DrawdownCalculator` | current and maximum drawdown |
| `AllocationCalculator` | normalized weights and constraint checks |
| `ExposureCalculator` | asset, currency, market, and theme concentration |
| `StressCalculator` | scenario P/L or sensitivity estimates |

Agents explain these results but do not replace them.

## `MarkdownCodec`

Purpose: convert domain aggregates to and from versioned Markdown.

Responsibilities:

- parse and render YAML front matter;
- render stable headings and tables;
- validate required metadata;
- preserve unknown future-compatible metadata where safe;
- reject unsupported schema versions;
- avoid silently accepting malformed numeric data.

Every user-visible signal, forecast, and research result must pass through a Markdown codec. A cache or in-memory dashboard index is not a durable result.

## `DoctorService`

Checks the local environment without initiating research:

- workspace is writable;
- selected agent binary exists;
- installed version can report required capabilities;
- authentication is present when the provider supports a safe status check;
- source manifests and usage-profile declarations are valid;
- terms review dates, attribution requirements, and point-in-time capabilities are present;
- a lightweight source health call succeeds when explicitly requested;
- registered adapters expose the capabilities required by enabled research packs;
- Markdown repository can atomically write and read a probe file;
- configuration contains no inline secrets.

The default doctor check should avoid consuming agent quota.

## Factories and Plugin Registration

Factories are simple mappings:

```python
class AgentBackendFactory:
    def create(self, config: AgentConfig) -> AgentBackend:
        if config.provider == "codex_cli":
            return CodexCliAgentAdapter(...)
        if config.provider == "claude_cli":
            return ClaudeCliAgentAdapter(...)
        if config.provider == "antigravity_cli":
            return AntigravityCliAgentAdapter(...)
        raise UnsupportedAdapter(config.provider)
```

Agent construction can start as the explicit mapping above. Data sources are registry-based from the first MVP because FRA must support many independently evolving adapters:

```python
class SourceAdapterFactory:
    def create_all(self, config: DataSourcesConfig) -> list[SourceAdapter]:
        # Resolve built-ins and installed `fra.data_sources` entry points,
        # validate manifests, then construct enabled adapters.
        ...
```

The factory constructs adapters; `SourceRegistry` indexes capabilities; `SourceRouter` makes policy-bound selections. Workflows receive ports and services, never factory or provider implementation objects.

## Error Model

Adapters translate external errors into FRA-owned errors:

```text
AdapterUnavailable
AuthenticationRequired
CapabilityUnsupported
CapabilityUnavailable
ExternalRateLimited
SourceQuotaExceeded
ExternalTimeout
ExternalDataInvalid
UsagePolicyViolation
PointInTimeUnavailable
SourceTermsReviewExpired
StructuredOutputInvalid
RepositoryConflict
RepositoryCorrupt
ResearchNeedsInput
ResearchIncomplete
```

Use cases decide recovery policy. Adapters provide facts about the failure, not business decisions.

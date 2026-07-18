# Factories, Adapters, and Evolution

## Pattern Boundary

FRA applies adapters to replaceable external boundaries and factories to their construction.

It does not create a factory for every domain object. `Evidence`, `Claim`, and `Scenario` are ordinary domain models. Unnecessary factories would obscure the finance logic without improving replaceability.

The rule is:

> If an implementation depends on a vendor, protocol, process, or persistence technology, place it behind a port and construct it through a factory.

## Adapter Families

### Agent backends

```text
AgentBackend
├── CodexCliAgentAdapter          MVP
├── ClaudeCliAgentAdapter         MVP
├── AntigravityCliAgentAdapter    experimental
├── OpenAIApiAgentAdapter         future
├── AnthropicApiAgentAdapter      future
└── LocalModelAgentAdapter        future
```

### Evidence data sources

FRA uses small capability ports rather than one universal data-provider interface:

```text
MarketDataProvider       -> CoinGecko, yfinance, future licensed feeds
EconomicSeriesProvider  -> FRED/ALFRED, World Bank Indicators
DocumentProvider        -> manual URL/file, RSS/Atom, SEC, OpenDART
EventProvider           -> GDELT discovery, future conflict feeds
FundamentalsProvider    -> SEC EDGAR, OpenDART
TradeFlowProvider       -> UN Comtrade, FAOSTAT
PhysicalFlowProvider    -> EIA, JODI, World Bank Pink Sheet, IMF PortWatch
PositioningProvider     -> CFTC COT
OnChainDataProvider     -> Coin Metrics Community
```

One adapter may implement multiple ports, but the adapter returns FRA-owned types for each capability. A universal `fetch(dict) -> dict` is deliberately forbidden because it would leak provider semantics into workflows.

### Persistence

```text
ResearchRepository
├── MarkdownResearchRepository    MVP
└── InMemoryResearchRepository    tests
```

The same pattern applies to signal, profile, portfolio, forecast, outcome, exposure-graph, and cache repositories. Markdown implementations remain mandatory for user-visible results.

## Capability-Based Selection

Adapters expose capabilities so the application can choose safe workflows.

Example agent capabilities:

```text
non_interactive
structured_output
streaming_events
resume_session
output_schema
tool_allowlist
sandbox_modes
usage_reporting
```

Example source capabilities and constraints:

```text
source_kinds and typed ports
geographies, markets, instruments, and classifications
fields, units, frequencies, and history bounds
point-in-time vintages and known publication delay
authentication and quota model
authority and independence class
allowed usage profiles and attribution
raw-retention and redistribution rights
experimental and discovery-only status
```

The source factory validates manifests at construction. At request time, `SourceRouter` verifies that evidence requirements and workspace policy are compatible. A workflow may require more capabilities or higher authority than another workflow.

## Factory Configuration

Factories consume typed configuration and return ports.

```text
fra.toml
   |
   v
ConfigLoader -> FraConfig
                  |
                  +-> AgentBackendFactory -> AgentBackend
                  +-> SourceAdapterFactory -> SourceRegistry
                  |                              |
                  |                              v
                  |                         SourceRouter
                  +-> RepositoryFactory -> repositories
                                      |
                                      v
                               Application services
```

Provider-specific options remain inside the matching configuration block. Unknown options should fail validation instead of being silently ignored.

Built-in sources and future third-party packages use the same `SourceDescriptor`. Packages may expose adapters through the Python entry-point group `fra.data_sources`. Plugin discovery never bypasses manifest validation, usage policy, or contract tests.

## Adding a New Data Source

Adding a source is an adapter task, not a workflow rewrite:

1. identify the smallest typed port or ports the source actually supports;
2. document official endpoints, authentication, quota, update schedule, history, corrections, and terms;
3. create a `SourceDescriptor` with authority, independence, point-in-time, usage, attribution, and retention metadata;
4. map provider identifiers, classifications, units, and timestamps into FRA-owned domain types;
5. preserve `observed_at`, `published_at`, `available_at`, `revised_at`, and `retrieved_at` separately;
6. implement typed health and error translation without placing provider objects in application code;
7. register the adapter as a built-in or `fra.data_sources` entry point;
8. run the shared source contract plus fixture, policy, and point-in-time tests;
9. add a short operational note and a dated terms review;
10. enable it for a research pack only after the router can express its legitimate role: primary, fallback, cross-check, or discovery.

A source is not production-ready merely because an HTTP request succeeds. The Definition of Done in [Data source strategy and feasibility](08-data-source-strategy.md) also requires stable identity, time semantics, reproducible fixtures, and explicit allowed use.

## Adding a New Agentic CLI

To add a CLI:

1. implement `AgentBackend`;
2. add binary discovery and a non-quota health check;
3. build subprocess arguments without shell interpolation;
4. normalize events and errors;
5. expose a capability object;
6. implement session resumption only if the CLI has a stable identifier;
7. add the adapter to `AgentBackendFactory`;
8. run the shared agent-backend contract tests;
9. document required installation, authentication, and permission behavior.

The adapter must not alter workflow rules to accommodate vendor output. It translates vendor output into FRA contracts.

## Moving from CLI to API-Key Agents

Future API adapters implement the same `AgentBackend` port.

Example future configuration:

```toml
[agent]
provider = "openai_api"
timeout_seconds = 900

[agent.options]
model = "configured-model"
api_key_env = "OPENAI_API_KEY"
```

Migration impact:

| Area | Required change |
| --- | --- |
| Domain models | None |
| Research workflows | None unless new capabilities are intentionally used |
| Application services | None |
| Prompt and output schemas | Reuse; provider-specific tuning may be versioned |
| Factory | Add provider mapping |
| Adapter | New API implementation |
| Configuration | Select new provider and secret reference |
| Tests | Run shared contract tests plus provider integration tests |

The API adapter owns authentication headers, streaming protocol, retries, provider usage metadata, and remote session handling.

## Preserving the Markdown Output Boundary

Markdown repositories remain authoritative for every release. Performance work may add an in-memory or disposable local index, but the index must rebuild completely from Markdown and cannot become a write target for signals or research results.

This preserves the repository contracts for tests and internal evolution without creating an alternative result surface. Schema migrations always produce versioned Markdown and a Markdown migration report.

## Moving to Paid or Licensed Data

A licensed provider adapter can replace or complement free data without changing research workflows.

The application selects providers through an `EvidenceRequirement`, the source registry, and explicit routing policy. It must not silently treat two providers as interchangeable when their timestamps, authority, adjustments, classifications, independence, or licensing differ.

When provider reconciliation is enabled, FRA stores:

- every contributing provider;
- each provider's observation, publication, availability, revision, and retrieval times;
- the reconciliation rule;
- discrepancies and tolerances;
- the selected value and reason.

License metadata is operational policy, not a README footnote. A workspace declares a usage profile such as `local_personal_research`, `internal_commercial_research`, or `redistributable_product`. The router fails closed when the source's allowed use or raw-retention rights are unknown or incompatible. This permits a future paid feed without contaminating old artifacts or assuming that free-access data can be redistributed.

## Contract Tests

Every adapter family has a shared behavioral test suite.

### Agent backend contract

- reports capabilities;
- returns a normalized health result;
- executes a schema-valid fixture request;
- preserves run and stage IDs;
- classifies timeout and authentication failures;
- cancels child work;
- does not leak secrets;
- resumes only when supported.

### Shared data-source contract

- exposes a valid, uniquely identified `SourceDescriptor`;
- returns only the typed capabilities it declares;
- returns normalized identifiers, classifications, units, currency, and timezone where applicable;
- preserves observation/period, publication, availability, revision/vintage, and retrieval timestamps;
- enforces the declared point-in-time cutoff or reports `PointInTimeUnavailable`;
- rejects an incompatible usage profile and raw-retention request;
- records request fingerprints, content hashes, attribution, and warnings;
- classifies authentication, quota, rate-limit, timeout, and malformed-source failures;
- never exposes vendor-native objects;
- produces deterministic output from checked-in fixtures.

Each typed port adds its own tests. For example, market adapters test symbol ambiguity and corporate-action behavior; economic-series adapters test vintages; trade adapters test classification versions; document adapters test correction and publication metadata.

### Repository contract

- creates, loads, saves, and lists aggregates;
- prevents lost updates;
- persists state before reporting success;
- round-trips all required fields;
- preserves IDs and citations;
- rejects corruption and unsupported schema versions.

In-memory implementations run these tests quickly. Concrete adapters run the same suite with fixtures or controlled integrations.

## Versioning

Track independently:

- FRA application version;
- domain schema version;
- Markdown schema version;
- prompt template version;
- agent adapter version and detected CLI version;
- source descriptor schema and routing-policy version;
- each data-source adapter version and dated terms review;
- calculation version;
- signal schema, exposure-graph, and forecast-resolution-rule versions;
- report template version.

Every research run stores the versions necessary to explain how its report was produced.

## MVP Implementation Sequence

This section summarizes the architectural milestones. The dependency-ordered work packages, test gates, release boundaries, and first backlog are defined in the [implementation plan](10-implementation-plan.md).

### Milestone 1: Core skeleton

- package and CLI entry point;
- domain models and errors;
- typed source and repository ports;
- configuration and factories;
- in-memory test adapters.

### Milestone 2: Markdown vertical slice

- Markdown codecs and repositories;
- signal repository and read-only terminal dashboard snapshot;
- research run state machine;
- `fra dashboard`, `fra signals`, `fra runs`, and `fra show`;
- atomicity and repository contract tests.

### Milestone 3: Source substrate

- source descriptors, registry, router, routing-decision artifacts, and shared contracts;
- manual file/URL and RSS/Atom document adapters;
- World Bank Indicators adapter;
- source policy, cache, and fixture-backed contracts.

### Milestone 4: First working research path

- Codex CLI adapter and shared agent contract;
- durable orchestration, resume, and cancellation;
- conditional CoinGecko adapter;
- crypto market-timing workflow;
- deterministic return, volatility, and drawdown analytics;
- evidence, claim, verification, and report artifacts.

### Milestone 5: Forecast and oil/fertilizer vertical slice

- immutable forecast, outcome, monitoring, and scoring artifacts;
- EIA, World Bank Pink Sheet, FRED/ALFRED, and SEC EDGAR adapters;
- JODI, UN Comtrade, and CFTC only when the vertical slice demonstrates the corresponding evidence gap;
- event-to-exposure graph and crisis workflow;
- oil supply/passage, fertilizer input cost, and affected-business research path;
- point-in-time and no-look-ahead tests.

### Milestone 6: Three-question MVP and provider portability

- suitability-aware allocation workflow;
- conditional yfinance personal-research fallback;
- Claude Code adapter and backend selection through configuration;
- the shared research fixtures passing through both agent backends.

### Milestone 7: Regional disclosures and hardening

- US market mappings and a permitted price source;
- South Korea filings through OpenDART and approved KRX service adapters;
- Vietnam official disclosure/document adapters after a dedicated provider spike;
- licensed price adapters where distribution or commercial use requires them.

### Later milestones

- experimental Antigravity adapter when structured integration is stable;
- API-key agent adapters;
- IMF PortWatch, Coin Metrics, FAOSTAT, GDELT discovery, UCDP, and other researched adapters as their slices require;
- licensed price, news, transcript, derivatives, AIS, and facility/supply-chain adapters;
- scheduled local monitoring and richer terminal dashboard views.

## Architecture Fitness Checks

During implementation, regularly verify:

1. Can an in-memory adapter run the workflow with no network or installed agent CLI?
2. Can the agent backend switch from Codex to Claude using configuration only?
3. Can a source fixture replace a network source using configuration only?
4. Can a research run be rebuilt entirely from Markdown artifacts?
5. Does any vendor type cross into `domain` or `application`?
6. Does any factory contain business logic?
7. Does any agent-generated number bypass deterministic calculation or evidence validation?
8. Can deleting every disposable index leave all signals and results intact and allow the dashboard to rebuild?
9. Can a new data source register without editing a research workflow?
10. Does routing reject incompatible usage rights and evidence published after a forecast cutoff?
11. Are discovery signals prevented from becoming sole support for material claims?
12. Can forecast performance be recomputed from immutable Markdown forecasts and outcomes?

If any answer is wrong, the adapter boundary has leaked.

# Architecture

## Architectural Style

FRA uses **ports and adapters**, also known as hexagonal architecture.

- The **domain layer** defines finance-research concepts and invariants.
- The **application layer** coordinates use cases and workflow state.
- **Ports** define what the application needs from external systems.
- **Adapters** translate between a port and a concrete CLI, HTTP provider, or filesystem format.
- **Factories** select and construct adapters from configuration at startup.
- The **composition root** wires the application together.

The dependency direction always points inward:

```text
CLI presentation
      |
      v
Application use cases -----> Domain models and policies
      ^                              ^
      |                              |
   Ports                         Pure logic
      ^
      |
Adapters: agent CLI, evidence sources, Markdown storage
```

The application core must continue to work when all external adapters are replaced with in-memory test adapters.

## System Context

```text
                            +-------------------------+
                            | Installed agentic CLI   |
                            | Codex / Claude / agy    |
                            +------------+------------+
                                         ^
                                         | AgentBackend port
                                         |
+----------+       +---------------------+---------------------+
| User     +------>| FRA CLI, Dashboard, and Application Core  |
+----------+       | signals + research + forecasts + routing  |
                   +-----------+------------------+-------------+
                               |                  |
              typed source ports                 | repositories
                               v                  v
                 +-------------+------+  +--------+-------------+
                 | Source registry     |  | Local Markdown       |
                 | market / macro /    |  | signals / runs /     |
                 | events / filings /  |  | forecasts / outcomes|
                 | physical / trade    |  +----------------------+
                 +-------------+-------+
                               |
                               v
                 +-------------+-------------------------------+
                 | Public, official, experimental, or licensed |
                 | providers selected under explicit policy    |
                 +---------------------------------------------+
```

## Logical Layers

### 1. Presentation layer

Owns terminal input and output.

Responsibilities:

- parse commands and options;
- display progress and partial failures;
- render the read-only signal and forecast dashboard;
- choose a workspace and configuration profile;
- render a concise terminal result;
- return meaningful exit codes.

It does not perform research or call providers directly.

### 2. Application layer

Owns use cases and workflow coordination.

Initial use cases:

- `RunResearch`
- `ResumeResearch`
- `ShowResearchRun`
- `ListResearchRuns`
- `ShowDashboard`
- `ListSignals`
- `ShowSignal`
- `CreateInvestorProfile`
- `EvaluateCryptoMarket`
- `ProposeAssetAllocation`
- `AnalyzeCrisisScenario`
- `IssueForecast`
- `MonitorForecast`
- `ResolveForecast`
- `ScoreForecast`
- `Doctor`

The application layer works with ports and domain models only.

### 3. Domain layer

Owns stable business concepts:

- research mandate, plan, task, and run;
- instrument, asset class, market, and currency;
- evidence, source, claim, citation, and freshness;
- signal, signal version, stance, strength, horizon, and invalidation;
- scenario, transmission channel, probability band, and impact;
- forecast, forecast version, trigger, invalidation, outcome, and score;
- event, document, economic series, physical flow, trade flow, and company fundamental;
- entity, dependency edge, company exposure, and causal exposure graph;
- investor profile, constraint, allocation, exposure, and risk metric;
- research status and validation result.

Domain code contains no subprocess, HTTP, filesystem, YAML, Markdown, or vendor-specific logic.

### 4. Ports

Ports are Python protocols or abstract interfaces owned by FRA.

Primary ports:

| Port | Purpose |
| --- | --- |
| `AgentBackend` | Execute or resume a structured agent stage |
| `MarketDataProvider` | Retrieve normalized quotes, bars, instruments, and market snapshots |
| `EconomicSeriesProvider` | Retrieve macro series, releases, and point-in-time vintages |
| `DocumentProvider` | Search or fetch permitted releases, filings, feeds, and user-supplied documents |
| `EventProvider` | Retrieve normalized events and supporting mentions for discovery |
| `FundamentalsProvider` | Retrieve company facts, filing metadata, segments, and disclosures |
| `TradeFlowProvider` | Retrieve bilateral country-product imports and exports |
| `PhysicalFlowProvider` | Retrieve production, inventory, demand, port, and shipping-passage observations |
| `PositioningProvider` | Retrieve normalized positioning observations and their release times |
| `OnChainDataProvider` | Retrieve normalized crypto network, supply, activity, and fee metrics |
| `ResearchRepository` | Save and load research artifacts |
| `SignalRepository` | Save immutable signal versions and lifecycle state |
| `SourceStatusRepository` | Save the last explicit source check for dashboard observation |
| `ForecastRepository` | Save immutable forecast versions and lifecycle state |
| `OutcomeRepository` | Save forecast resolutions and deterministic scores separately from forecasts |
| `ExposureGraphRepository` | Save provider-independent entities and evidence-backed dependency edges |
| `ProfileRepository` | Save and load investor profiles |
| `PortfolioRepository` | Save and load portfolios and proposed allocations |
| `CachePort` | Cache provider results without leaking provider formats |
| `Clock` | Make timestamps deterministic in tests |
| `IdGenerator` | Create stable IDs independent of storage |

### 5. Adapters

Adapters implement ports.

Adapter targets, staged by the implementation plan:

- `CodexCliAgentAdapter`
- `ClaudeCliAgentAdapter`
- `AntigravityCliAgentAdapter` deferred until it can satisfy the shared contract
- `CoinGeckoMarketDataAdapter`
- `YFinanceMarketDataAdapter` enabled only by a compatible usage policy
- `WorldBankIndicatorsAdapter`
- `ManualDocumentAdapter` and `RssAtomDocumentAdapter`
- initial crisis adapters for EIA, FRED/ALFRED, World Bank Pink Sheet, and SEC EDGAR
- `GdeltEventAdapter` marked experimental and discovery-only
- `SourceRegistry` and `SourceRouter` for explicit primary, fallback, and cross-check selection
- `MarkdownResearchRepository`
- `MarkdownSignalRepository`
- `MarkdownProfileRepository`
- `MarkdownPortfolioRepository`
- in-memory adapters for tests

Future input adapters may use provider APIs, MCP, an agent SDK, or licensed data feeds without changing use cases. Markdown remains the mandatory result adapter; any later index is derived and disposable.

### 6. Factories and composition root

Factories translate configuration into adapters:

```text
AgentBackendFactory.create(agent_config)
SourceAdapterFactory.create_all(source_configs)
RepositoryFactory.create(storage_config)
```

The composition root calls the factories once, constructs application services, and passes them to the CLI command handlers.

Factories are not service locators. Constructed dependencies are passed explicitly.

## Research State Machine

Every research run follows an explicit state machine:

```text
CREATED
   |
   v
PLANNING
   |
   v
COLLECTING_EVIDENCE
   |
   v
ANALYZING
   |
   v
VERIFYING -----> NEEDS_RESEARCH ----+
   |                                |
   |                                +--> COLLECTING_EVIDENCE
   v
SYNTHESIZING
   |
   v
COMPLETED
```

Any active state may transition to `FAILED`, `CANCELLED`, or `NEEDS_USER_INPUT`. State changes are persisted through the repository port.

## Forecast Lifecycle

A research run produces a report and may issue one or more forecasts. Research completion does not end the life of a forecast.

```text
DRAFT
  |
  v
ACTIVE <----------+
  |               |
  v               |
MONITORING --> UPDATED
  |
  +-------> INVALIDATED
  |
  v
RESOLVED
  |
  v
SCORED
```

An update creates an immutable forecast version. It never edits an earlier probability in place. Resolution records the observed outcome, resolution evidence, effective time, and resolver. Scoring uses only the forecast version and information available when it was issued.

## Agent Boundary

The agent backend is a reasoning engine, not the system of record.

FRA sends a stage request containing:

- a bounded instruction;
- relevant evidence IDs and rendered evidence content;
- an output JSON Schema;
- allowed workspace paths;
- timeout and budget information;
- previous backend session ID when resuming.

The backend returns normalized events and a structured result. The concrete adapter handles CLI flags, stdout, stderr, exit codes, session IDs, and vendor event formats.

The application never parses vendor output directly.

## Evidence-Source Boundary

Every provider response is normalized into FRA-owned values such as `MarketQuote`, `EconomicObservation`, `DocumentEvidence`, `EventObservation`, `CompanyFact`, `TradeFlow`, and `PhysicalFlow`.

Every normalized result uses a common provenance envelope that includes:

- provider name;
- provider record and subject identifiers;
- FRA provider-independent subject IDs;
- source kind and authority class;
- retrieval timestamp;
- observation or event time;
- publication and first-available times when known;
- effective and revision times when applicable;
- period start and end;
- timezone and currency;
- units and classification version;
- stale or delayed status when known;
- content hash and request fingerprint;
- usage-policy and attribution identifiers;
- independence group used for corroboration;
- warnings and missing fields.

`as_of` may remain as a display convenience, but it never replaces these distinct time meanings. The provider's raw JSON, DataFrame, XML, spreadsheet, or document object never crosses the adapter boundary.

## Source Registry and Routing

Every source adapter publishes a `SourceDescriptor` and one or more small typed capabilities. The descriptor records access method, scopes, history, normal cadence, point-in-time support, authority, quota behavior, terms URL, allowed uses, attribution, raw-retention policy, and the date on which the terms were reviewed.

The `SourceRegistry` contains available adapters. `SourceRouter` matches an `EvidenceRequirement` to compatible sources and assigns explicit roles:

```text
primary     authoritative source for the requested fact
fallback    used only when policy permits and the primary fails
cross-check independent corroborating or discrepancy source
discovery   locates candidate evidence but cannot solely support a material claim
```

Routing considers capability, subject, geography, history, frequency, freshness, point-in-time cutoff, authority, independence, cost, quota, and allowed use. The router then executes only the selected adapters, attempts a fallback only after primary failure, records typed failures, and never silently averages disagreements.

## Storage Boundary

Repositories work with domain aggregates and return domain aggregates. They may return a stable `ArtifactRef` for dashboard navigation, but use cases never construct or traverse filesystem paths directly.

The Markdown adapter owns:

- path layout;
- YAML front matter;
- Markdown rendering and parsing;
- schema versions;
- atomic writes;
- file locking;
- indexing by scanning front matter;
- migration between Markdown schema versions.

Markdown repositories are the authoritative result stores. A future in-memory or embedded index may accelerate reads, but it is rebuilt from Markdown and cannot replace Markdown emission.

## Dashboard Boundary

`DashboardService` builds a provider-independent snapshot from signal, forecast, outcome, research, and source-status repositories. The CLI presenter renders that snapshot as terminal tables.

The dashboard:

- reads persisted Markdown-backed state;
- does not call an agent or data source by default;
- reloads local files in watch mode;
- links every detailed item to a Markdown artifact;
- contains no research, ranking, or signal-generation logic.

The complete output contract is defined in [CLI dashboard and Markdown output contract](09-cli-dashboard-and-output-contract.md).

## Cross-Cutting Policies

### Evidence policy

- A material claim requires at least one citation.
- Price-sensitive claims require an observation time, market timezone, and retrieval time; forecasts additionally require a defensible `available_at` cutoff.
- Unsupported claims are rejected or visibly labelled.
- Conflicting sources remain visible; synthesis does not silently discard them.
- Discovery sources cannot solely support high-materiality causal or investment claims.

### Signaling and safety policy

- FRA has no financial-account action port or credential model.
- Signals are evidence-backed observations and never trigger an external action.
- Agent subprocesses receive the narrowest filesystem and command permissions possible.
- FRA never enables dangerous permission-bypass flags by default.
- Secrets are provided through environment variables only to the adapter that needs them.
- Provider credentials owned by an agent CLI are never copied into the FRA workspace.

### Reliability policy

- All external calls have timeouts.
- Retries use bounded exponential backoff and respect provider responses.
- Partial data produces a partial result with warnings, not invented values.
- A source whose terms or allowed use are unknown fails closed.
- Quota budgets and circuit breakers apply per source rather than globally.
- Agent output is structurally validated before it enters the domain.
- Markdown writes are atomic.

## Why This Architecture Fits the MVP

The MVP remains one local process with one composition root, a terminal dashboard, and Markdown persistence. It remains extensible because vendor choices are isolated at the input edges and sources are selected from typed capabilities. Replacing an agent CLI with an API or adding a new source plugin changes factories, registries, and adapters—not research workflows, domain rules, or the CLI-and-Markdown output boundary.

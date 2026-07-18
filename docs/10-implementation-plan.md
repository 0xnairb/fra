# Implementation Plan

## Objective

Implement FRA as a sequence of usable vertical slices while preserving the approved ports-and-adapters architecture. The plan starts with deterministic domain behavior and local Markdown, then adds the observational CLI dashboard, public data sources, one agentic CLI, forecasting, and the broader research mandates.

The implementation must prove two things early:

1. FRA can complete a small research run without depending on hidden agent state.
2. Any agent, source, or storage adapter can be replaced by an in-memory implementation without changing a use case.

## Delivery Strategy

Use a walking-skeleton approach. Each work package ends with a runnable command or a contract test; avoid building all domain models, all sources, or all workflows before demonstrating one end-to-end path.

```text
Foundation
    |
    v
Domain + in-memory ports
    |
    v
Markdown persistence + basic CLI
    |
    v
Source registry/router + first sources
    |
    v
Agent backend + research state machine
    |
    v
Crypto research vertical slice
    |
    v
Forecast ledger + exposure graph
    |
    v
Oil/fertilizer crisis vertical slice
    |
    v
Allocation + second agent backend
    |
    v
Regional packs + hardening
```

Do not parallelize dependent work merely to appear faster. Source adapters can be developed independently only after their shared descriptor, envelope, and contract suite are stable.

## Implementation Baseline

The initial implementation should use:

| Concern | Decision |
| --- | --- |
| Language | Python 3.12 or newer |
| Package layout | `src/fra` with PEP 621 metadata in `pyproject.toml` |
| CLI | Typer command tree; handlers remain presentation-only |
| Domain models | Standard-library dataclasses, enums, and explicit value objects |
| Boundary validation | Pydantic for configuration, source DTOs, agent results, and generated JSON Schema |
| Async execution | Standard-library `asyncio`; no general agent framework |
| HTTP | One lifecycle-managed HTTPX `AsyncClient`, explicit timeouts and connection limits |
| Configuration | TOML loaded through `tomllib`, then validated into typed configuration |
| Results | Versioned Markdown repositories with YAML front matter behind `MarkdownCodec` |
| Observation | Read-only Typer dashboard built from Markdown-backed application snapshots |
| Tests | pytest-style unit, contract, fixture-integration, and CLI tests |
| Static quality | Formatter/linter, strict-enough type checking, dependency-boundary tests |

Typer supports nested command applications and isolated CLI testing. Pydantic should validate untrusted boundary data and generate the JSON Schemas sent to agent backends; it should not become a requirement for pure finance calculations. HTTPX clients should be constructed once at bootstrap and closed with the application rather than created in each source call.

Toolchain references: [Typer nested commands](https://typer.tiangolo.com/tutorial/subcommands/nested-subcommands/), [Typer testing](https://typer.tiangolo.com/tutorial/testing/), [Pydantic models and validation](https://docs.pydantic.dev/latest/concepts/models/), [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/), [HTTPX async clients](https://www.python-httpx.org/async/), and [HTTPX connection limits](https://www.python-httpx.org/advanced/resource-limits/).

Pin compatible dependency ranges in `pyproject.toml`, commit a resolved lock file if the selected environment manager supports one, and record detected agent CLI versions at runtime. Exact dependency versions are an implementation-time compatibility decision, not a domain contract.

Work-package sizes are relative complexity indicators, not calendar estimates: **S** is bounded foundation work, **M** is one cohesive subsystem, **L** crosses several contracts, and **XL** must be delivered as multiple increments.

## Implementation Readiness Review

The approved design is sufficiently complete to begin WP0. Implementation details that do not alter a project boundary—such as the build backend, environment manager, YAML codec dependency, and terminal table renderer—are selected in WP0 through a small compatibility spike, documented in `pyproject.toml` and the root README, and covered by a smoke test. They are not reasons to delay the first vertical slice.

### Coverage matrix

| Approved concern | Delivery location | Proof |
| --- | --- | --- |
| Package, CLI entry point, configuration, and composition root | WP0-WP1 | clean build, configuration tests, CLI smoke tests |
| Domain identity, time, state, evidence, and signal invariants | WP1 | deterministic unit and architecture-boundary tests |
| Markdown results, atomicity, artifact references, and dashboard | WP2 | repository contracts and hermetic R0 test |
| Source manifests, routing, licensing, quota, cache, and source status | WP3 | shared source contracts and fixture integrations |
| Agent subprocess, schemas, orchestration, resume, and cancellation | WP4 | fake-process contracts and restart tests |
| Crypto timing signal and deterministic analytics | WP5 | hermetic workflow plus opt-in local smoke test |
| Forecast versions, monitoring, outcomes, scoring, and exposure graph | WP6 | no-look-ahead and recomputation tests |
| Oil/fertilizer crisis prediction and affected-business reasoning | WP7 | frozen historical case and end-to-end scored forecast |
| Allocation, second agent backend, and source plugin discovery | WP8 | shared contracts and configuration-only swaps |
| Regional packs, migrations, installation, recovery, and performance | WP9 | regional fixtures, migration tests, and recovery exercise |
| Security, privacy, typed failures, logging redaction, and documentation | Every work package | focused tests plus continuous-integration gates |

### Cross-cutting delivery rules

- Configuration, factories, and the composition root evolve with each vertical slice; no CLI command constructs adapters directly.
- `fra doctor` is staged: runtime/configuration checks in WP0, workspace/Markdown checks in WP2, source checks in WP3, and agent-backend checks in WP4.
- Every CLI increment defines stable success, incomplete, user-input, configuration, external-dependency, and corruption exit behavior as applicable.
- Diagnostic logs redact configured secrets and remain supplementary; user-visible durable results are Markdown.
- Security, file permissions, schema compatibility, recovery, and documentation are requirements from their first relevant work package, not cleanup deferred to WP9.
- Persisted contract changes update codecs, fixtures, compatibility tests, examples, and documentation together.

### Readiness conclusion

No unresolved architectural decision blocks implementation. The first real change should follow TDD: add a failing hermetic test for the packaged `fra --version` behavior, then complete the smallest WP0 slice that makes build, CLI help, version, lint, types, and tests pass.

## Work Packages

### WP0: Repository and quality foundation

Size: **S**

Deliverables:

- `pyproject.toml` with runtime and development dependency groups;
- a documented compatibility choice for build backend, environment workflow, YAML codec, and terminal rendering;
- `src/fra/__init__.py`, `src/fra/__main__.py`, and a minimal `fra` console entry point;
- initial `src/fra/bootstrap.py` composition root with no business logic;
- strict typed configuration loading, `fra.example.toml`, and rejection of unknown options and inline secrets;
- `tests/unit`, `tests/contract`, `tests/integration`, and `tests/fixtures` roots;
- formatter, lint, type-check, and test commands documented in the root README;
- CI configuration that runs without network credentials;
- version module and basic `fra --version`, `fra --help`, and staged `fra doctor` commands;
- typed CLI exception-to-exit-code mapping and secret-redaction utility foundations.

Exit gate:

```text
fra --version
fra --help
fra doctor
test suite
lint
type check
package build
```

All pass from a clean checkout. `fra doctor` validates runtime and configuration only at this stage. No source API or agent CLI is invoked, and an inline secret fixture is rejected without echoing its value.

### WP1: Domain kernel and port contracts

Size: **M**

Implement only the models required by the first vertical slice, then expand them when a later work package needs them.

Deliverables:

- IDs, UTC time helpers, money/currency, instrument references, and typed errors;
- `SourceDescriptor`, `EvidenceRequirement`, `DataEnvelope`, `Evidence`, `Claim`, `Signal`, and `ResearchMandate`;
- research-run state and valid-transition policy;
- `ArtifactRef`, health status, and typed failure values used across boundaries;
- initial `AgentBackend`, `MarketDataProvider`, `DocumentProvider`, research/signal repository, clock, and ID-generator ports;
- in-memory repositories and deterministic fake adapters;
- explicit factories and a fully in-memory object graph constructed only by `bootstrap.py`;
- architecture import rules enforced by tests.

Key invariants:

- domain IDs never depend on a provider symbol;
- time fields are timezone-aware;
- `available_at` cannot occur after a historical evidence cutoff;
- completed stages cannot be skipped or silently reopened;
- external payload types never appear in a port return value.

Exit gate:

- a fully in-memory research run can transition from creation through completion;
- invalid transitions and look-ahead evidence are rejected;
- bootstrap can replace repositories, clock, IDs, agent, and sources without changing a use case;
- expected domain and adapter failures map to typed application results rather than broad exception handling;
- domain and application tests run with no filesystem, HTTP, or agent CLI.

### WP2: Markdown persistence vertical slice

Size: **M**

Deliverables:

- versioned front-matter codec;
- atomic file writer and per-aggregate lock;
- `MarkdownResearchRepository` and `MarkdownSignalRepository` plus evidence and claim persistence;
- workspace initialization, owner-only permission where supported, path-containment policy, and stable `ArtifactRef` generation;
- `DashboardService` and a provider-independent `DashboardSnapshot`;
- `fra init`, `fra dashboard`, `fra signals`, `fra runs`, and `fra show RUN_ID`;
- workspace and atomic repository probes added to `fra doctor`;
- fixtures for valid, older, newer, malformed, and partially written documents.

Implementation order:

1. render a domain object to a deterministic string;
2. parse it back and compare all required fields;
3. add atomic files and locks;
4. implement repository queries;
5. expose read-oriented CLI commands.

Exit gate:

- repository contract tests pass for both in-memory and Markdown implementations;
- `fra init` is idempotent and never overwrites existing user content;
- terminating a write before atomic replace does not corrupt the previous aggregate;
- issued signal versions reject in-place replacement and corrections create explicit supersession;
- a run can be reconstructed using only its workspace files;
- the dashboard reconstructs active signals and recent runs from Markdown without an external call;
- dashboard plain-text output is deterministic and every detail carries a valid Markdown artifact reference;
- unsupported schema versions fail visibly.

### WP3: Source platform and deterministic ingestion

Size: **L**

Deliverables:

- `MarketDataProvider`, `DocumentProvider`, and `EconomicSeriesProvider` first; add other typed ports only with the slice that exercises them;
- source-manifest validation;
- `SourceRegistry`, `SourceRouter`, and routing-decision records;
- shared HTTP and file-download utilities with timeouts, rate limits, content hashing, and request fingerprints;
- source cache respecting freshness, usage profile, and retention rules;
- Markdown-backed last-known source status written only by explicit checks;
- shared source contract suite;
- `ManualDocumentAdapter`, `RssAtomDocumentAdapter`, and `WorldBankIndicatorsAdapter`;
- configuration-based built-in registration, with the same manifest contract future plugins will use;
- `fra sources list`, `fra sources describe PROVIDER`, and opt-in `fra sources check`, which persists its status result;
- source-manifest, required-capability, and terms-review validation added to `fra doctor` without a live call by default.

The manual and feed adapters come first because they prove document ingestion without depending on an API key. World Bank Indicators then proves paginated structured ingestion and normalization.

Exit gate:

- the router records why every candidate was selected or excluded;
- incompatible usage rights, authority, freshness, and point-in-time support are rejected;
- unknown usage or retention rights fail closed without leaking credential values;
- an explicit source check persists a Markdown status while dashboard reads never trigger a check;
- all live HTTP tests are opt-in; default CI uses checked-in fixtures and fake transports;
- adding a fixture source requires no workflow change.

Do not stabilize a third-party plugin API yet. Activate `fra.data_sources` entry-point discovery after R2, when at least two heterogeneous adapter families have exercised the contracts; the registry and workflows must already be compatible with that addition.

### WP4: Agent backend and orchestration skeleton

Size: **L**

Start with one backend: Codex CLI. Do not implement Claude Code simultaneously.

Deliverables:

- subprocess runner using argument arrays, separate standard streams, timeout, cancellation, and process-group cleanup;
- Codex capability and authentication health checks;
- event parser and normalized `AgentStageResult`;
- JSON Schema generation from FRA-owned boundary models;
- versioned prompt templates, output schemas, and persisted prompt/adapter/CLI version metadata;
- bounded structured-output repair;
- `ResearchOrchestrator` for plan, collect, analyze, verify, and synthesize;
- durable checkpoint and resume behavior;
- `fra research`, `fra resume`, and cancellation behavior with typed exit results;
- agent binary, capability, and safe authentication checks added to `fra doctor`;
- diagnostic event redaction before terminal or Markdown persistence;
- fake executable fixtures for success, malformed output, timeout, cancellation, and authentication failure.

Exit gate:

- orchestrator tests run primarily against `FakeAgentBackend`;
- Codex contract tests pass against a fake process in default CI;
- one opt-in local smoke test invokes the installed Codex CLI;
- timeout and user cancellation terminate the complete subprocess group and preserve a resumable Markdown state;
- structured-output repair is bounded and its failure remains visible;
- restarting FRA after any completed stage resumes from Markdown without hidden conversation state.

### WP5: First usable release—crypto market timing

Size: **M**

Deliverables:

- `CoinGeckoMarketDataAdapter` under the local-personal-research policy;
- crypto instrument resolution using CoinGecko IDs rather than symbols alone;
- returns, volatility, and drawdown calculators;
- crypto research requirements, verification rules, prompt templates, and report renderer;
- an immutable crypto signal persisted before completion;
- `fra research crypto` command;
- recorded source routing and attribution in the report.

Keep the first workflow narrow: BTC and ETH, a declared currency, a bounded lookback, and explicit user horizon/risk inputs. General token discovery and portfolio optimization are not required here.

Exit gate:

- the complete workflow succeeds against source fixtures and `FakeAgentBackend`;
- an opt-in local run succeeds against CoinGecko and Codex;
- every material conclusion cites persisted evidence or a deterministic calculation;
- the dashboard displays the signal and its Markdown path;
- missing risk inputs produce `NEEDS_USER_INPUT`;
- stale data, exhausted quota, and malformed agent output produce explicit partial or failed results;
- completed, incomplete, cancelled, and failed runs retain an inspectable Markdown status and report or limitation artifact.

Release checkpoint: **R1 Evidence-backed research MVP**.

### WP6: Forecast, outcome, and exposure-graph kernel

Size: **L**

Deliverables:

- forecast, forecast-version, trigger, invalidation, resolution, outcome, and score models;
- Markdown forecast, outcome, and exposure-graph repositories;
- `IssueForecast`, `MonitorForecast`, `ResolveForecast`, and `ScoreForecast` use cases;
- probability validation and deterministic Brier scoring for binary forecasts;
- point-in-time evidence snapshot and no-look-ahead policy;
- `fra forecasts`, `fra forecast show`, `fra monitor`, and `fra resolve` commands;
- append-only probability updates with explicit supersession;
- forecast, risk-watch, and score projections added to the CLI dashboard.

Exit gate:

- an issued probability cannot be edited in place;
- future-published evidence cannot enter a historical forecast version;
- forecast scores can be recomputed entirely from Markdown;
- unresolved and ambiguous outcomes remain visible in aggregate performance;
- `fra monitor` is an explicit local operation that persists before display; dashboard watch mode never performs monitoring;
- exposure-graph edges require evidence, confidence, and an invalidation condition.

### WP7: Predictive oil-and-fertilizer crisis slice

Size: **XL**

This is FRA's differentiating vertical slice and should be built as several adapter increments, not one large merge.

Adapter order:

1. EIA physical supply, inventory, and energy series;
2. World Bank Pink Sheet commodity benchmarks;
3. FRED/ALFRED macro observations and vintages;
4. SEC EDGAR filing metadata and selected XBRL facts;
5. optional GDELT discovery after the primary-source path works;
6. JODI, UN Comtrade, and CFTC only when the workflow demonstrates a concrete missing requirement.

Workflow deliverables:

- normalized events and causal transmission channels;
- event-to-country-to-commodity-to-industry-to-company exposure graph;
- scenario alternatives and skeptic stage;
- leading indicators with update cadence and monitoring rules;
- deterministic exposure and stress calculations;
- `fra research crisis` command;
- one checked-in historical case with a frozen knowledge cutoff and known outcome.

Exit gate:

- official facts and discovery signals are visually and structurally distinct;
- the historical case contains no post-cutoff observations or revised values masquerading as original vintages;
- the report explains both the supported causal chain and the strongest counter-scenario;
- affected-business rankings expose their evidence coverage and confidence;
- at least one forecast can be issued, monitored, resolved, and scored end to end.

Release checkpoint: **R2 Predictive research MVP**.

### WP8: Allocation workflow and agent portability

Size: **L**

Deliverables:

- investor profile, constraints, portfolio, and proposed-allocation repositories;
- allocation, concentration, exposure, and stress calculators;
- suitability-aware `fra research allocation` workflow;
- conditional yfinance fallback with explicit usage warning;
- Claude Code adapter using the shared `AgentBackend` contract;
- backend selection and resume behavior when the configured backend changes;
- `fra.data_sources` entry-point discovery with manifest validation, duplicate-ID rejection, and no workflow imports.

Exit gate:

- weights are deterministic outputs and meet all declared constraints;
- missing suitability information blocks a recommendation;
- the proposed allocation remains a versioned Markdown signal;
- the same fixture-backed research run passes with both agent adapters;
- a fixture plugin can register and be disabled through configuration without changing a workflow;
- changing the backend requires configuration only.

Release checkpoint: **R3 Three-question MVP**.

### WP9: Regional packs and hardening

Size: **XL**, staged after R3

Deliverables:

- US market and filing mappings;
- OpenDART integration and South Korean identifiers;
- KRX integration only after service approval and terms validation;
- Vietnam official-document mappings and a completed authoritative-price provider decision;
- consolidated provider-health and capability summaries in the CLI dashboard and `fra doctor` output;
- workspace schema migrations, Markdown-only workspace copy/export, disposable performance indexes, and recovery documentation;
- final security, privacy, packaging, installation, and cross-platform behavior review.

This work package must not delay the three-question MVP unless a specific launch audience requires a regional market. It hardens security and recovery controls already introduced earlier; it does not postpone them until R4.

## Release Boundaries

| Release | User-visible outcome | Completion boundary |
| --- | --- | --- |
| R0 Walking skeleton | Initialize a workspace and observe a fake Markdown-backed signal in the dashboard | Through WP2 |
| R1 Evidence-backed research MVP | Run and observe a bounded crypto signal and Markdown report locally | Through WP5 |
| R2 Predictive research MVP | Issue and score an oil/fertilizer crisis forecast | Through WP7 |
| R3 Three-question MVP | Support market timing, allocation, and crisis research through two agent CLIs | Through WP8 |
| R4 Regional research | Add production-ready US/KR/VN market packs where data rights allow | Through WP9 |

R2 is the recommended product-validation target. R1 validates plumbing; R2 validates FRA's proposed moat.

## Testing Strategy

### Unit tests

Cover configuration rejection, domain invariants, state transitions, routing policy, analytics, normalization, verification, scoring, dashboard projection, exit-result mapping, redaction, and Markdown codecs. Unit tests use fixed clocks and IDs.

### Contract tests

Run the same behavioral suite against:

- every `AgentBackend`;
- every typed source adapter;
- every repository implementation.

Contract tests must be reusable by future source plugins and repository test doubles while preserving mandatory Markdown emission.

### CLI and doctor tests

Exercise commands through an isolated runner. Verify deterministic plain-text output, stable exit behavior, no implicit network access, idempotent workspace initialization, staged doctor checks, and secret-free diagnostics.

### Fixture integration tests

Store representative provider responses with secrets and irrelevant bulk content removed. Test parsing, pagination, empty responses, corrections, rate limits, schema drift, unit changes, and provider warnings without live network access.

### Live integration tests

Live tests are opt-in, tagged by provider, rate-limited, and excluded from default CI. Their role is to detect provider drift, not to prove deterministic business behavior.

### End-to-end tests

Maintain two levels:

1. hermetic: fake agent, fixture sources, temporary Markdown workspace;
2. local smoke: installed agent CLI and permitted live source credentials.

The hermetic path is the release gate. A third-party outage must not make default CI nondeterministic.

### Forecast integrity tests

Every forecasting release must include:

- fixed knowledge cutoff tests;
- vintage/revision fixtures;
- publication-lag tests;
- immutable version tests;
- deterministic resolution and scoring tests;
- a check that duplicated news syndication does not count as independent corroboration.

## Continuous Integration Gates

Every change must pass:

1. formatting and lint;
2. type checking;
3. unit tests;
4. adapter and repository contract tests;
5. hermetic end-to-end test after R1;
6. Markdown schema compatibility tests;
7. dependency-direction checks;
8. secret and fixture-safety checks;
9. documentation link and Markdown example checks when docs change;
10. package build plus CLI help, version, and non-network doctor smoke tests.

Coverage percentage alone is not a release gate. High-risk policies—usage rights, point-in-time cutoffs, atomic writes, subprocess cancellation, and scoring—require direct behavioral tests.

## Pull Request Strategy

Prefer small dependency-ordered changes. A work package is a planning boundary, not one pull request.

Recommended sequence for a new adapter:

1. source descriptor and fixtures;
2. normalization and unit tests;
3. typed adapter and shared contract tests;
4. registry wiring and configuration;
5. workflow requirement and report behavior;
6. opt-in live smoke test and operational documentation.

Do not combine a new adapter, new workflow, Markdown schema migration, and agent prompt redesign in the same change.

## Risk Register

| Risk | Early control | Release response |
| --- | --- | --- |
| Architecture becomes ceremony before value | Implement only models needed by the active slice | Delete unused abstractions; keep fitness tests |
| Configuration or composition leaks into commands | Strict config models, one bootstrap root, and factory tests | Reject startup and fix the boundary before adding commands |
| Agent CLI output changes | Capability detection, fake-process fixtures, bounded parsers | Mark backend unhealthy without corrupting runs |
| Public source schema or quota changes | Fixture contracts, source manifests, request budgets | Use compatible fallback or return incomplete research |
| Free-source terms conflict with future use | Workspace usage profile and fail-closed routing | Add a licensed adapter; do not weaken policy silently |
| Historical backtest leaks future data | Separate availability and revision times | Block scoring when point-in-time evidence is unavailable |
| Markdown becomes slow or conflict-prone | Partitioned paths, append-mostly artifacts, in-process index | Optimize scans and add disposable indexes that rebuild from Markdown |
| Diagnostics expose credentials or private payloads | Central redaction, sanitized fixtures, and secret-safety checks | Block the release and rotate any exposed credential |
| Too many sources delay product validation | Add a source only for a declared evidence requirement | Defer enrichment until after the crisis slice proves need |
| Crisis ranking looks precise but rests on weak exposure data | Coverage/confidence fields and counter-scenario | Report low confidence or `CapabilityUnavailable` |

## First Implementation Backlog

These are the first dependency-ordered tasks after planning approval:

1. select and document the compatible WP0 toolchain, then create `pyproject.toml` and test roots;
2. add a hermetic CLI version test and observe it fail because the package command is absent;
3. implement the package entry point, version, minimal bootstrap, `fra --version`, and `fra --help`;
4. add strict configuration models, `fra.example.toml`, typed exit results, redaction, and runtime/configuration `fra doctor` tests;
5. implement IDs, clock, timestamps, typed errors, and core source/evidence/signal models;
6. define initial ports, in-memory adapters, factories, and a bootstrap-built test object graph;
7. implement and test the research state machine;
8. build deterministic Markdown front-matter round trips;
9. implement atomic Markdown research and signal storage plus workspace doctor probes;
10. add `fra init`, `fra dashboard`, `fra signals`, `fra runs`, and `fra show`;
11. implement `SourceDescriptor`, registry, router, source-status, and policy tests;
12. add manual document ingestion through a fixture-backed adapter.

Task 12 is the first evidence-ingestion demonstration. Do not start CoinGecko or an agent CLI before the earlier tasks and their applicable WP exit gates pass.

## MVP Definition of Done

The three-question MVP is complete when:

- a clean local installation can initialize and diagnose a workspace;
- configuration rejects unknown options and inline secrets without exposing values;
- `fra dashboard` observes signals, forecasts, risks, source state, and recent research from Markdown;
- Codex and Claude Code satisfy the same agent contract;
- crypto timing, suitability-aware allocation, and crisis-impact research complete through the shared orchestrator;
- every material claim links to persisted, policy-compatible evidence;
- deterministic numbers never come only from agent prose;
- source routing, attribution, freshness, conflicts, and limitations are visible;
- forecasts preserve a knowledge cutoff and can be monitored, resolved, and scored;
- runs recover from a terminated process without chat history;
- hermetic end-to-end tests pass with no network or credentials;
- Markdown artifacts are sufficient to reproduce reports and forecast scores;
- supported Markdown schema migrations and interrupted-write recovery are tested;
- every dashboard detail points to a durable Markdown result;
- expected CLI failures return stable typed results and secret-free diagnostics;
- no workflow imports a concrete agent, source, or storage adapter;
- no application port exists beyond observation, research, signaling, and local result persistence.

## Post-MVP Candidates

Consider only after the corresponding release proves demand:

- general multi-agent swarms;
- agent API-key backends;
- live AIS and proprietary supply-chain feeds;
- general plugin marketplace or remote plugin installation;
- optimization of every source before one complete forecast is scored.

Implementation must retain the permanent [CLI dashboard and Markdown output contract](09-cli-dashboard-and-output-contract.md). New capabilities may extend research inputs and signal types, but not introduce another user-facing surface or authoritative result format.

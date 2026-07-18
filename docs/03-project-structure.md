# Project Structure

## Proposed Repository Layout

```text
fra/
├── pyproject.toml
├── README.md
├── LICENSE
├── fra.example.toml
│
├── docs/
│   ├── README.md
│   ├── 01-mvp-scope.md
│   ├── 02-architecture.md
│   ├── 03-project-structure.md
│   ├── 04-components.md
│   ├── 05-runtime-flows.md
│   ├── 06-markdown-storage.md
│   ├── 07-extensibility.md
│   ├── 08-data-source-strategy.md
│   ├── 09-cli-dashboard-and-output-contract.md
│   └── 10-implementation-plan.md
│
├── src/
│   └── fra/
│       ├── __init__.py
│       ├── __main__.py
│       ├── bootstrap.py
│       │
│       ├── cli/
│       │   ├── app.py
│       │   ├── commands/
│       │   │   ├── doctor.py
│       │   │   ├── dashboard.py
│       │   │   ├── research.py
│       │   │   ├── resume.py
│       │   │   ├── signals.py
│       │   │   ├── forecasts.py
│       │   │   ├── monitor.py
│       │   │   ├── runs.py
│       │   │   ├── profile.py
│       │   │   └── portfolio.py
│       │   └── presenters/
│       │       ├── console.py
│       │       ├── dashboard.py
│       │       └── progress.py
│       │
│       ├── config/
│       │   ├── models.py
│       │   ├── loader.py
│       │   └── validation.py
│       │
│       ├── domain/
│       │   ├── enums.py
│       │   ├── errors.py
│       │   ├── research.py
│       │   ├── evidence.py
│       │   ├── signals.py
│       │   ├── sources.py
│       │   ├── events.py
│       │   ├── instruments.py
│       │   ├── market_data.py
│       │   ├── scenarios.py
│       │   ├── forecasts.py
│       │   ├── outcomes.py
│       │   ├── exposure_graph.py
│       │   ├── profiles.py
│       │   ├── portfolios.py
│       │   └── validation.py
│       │
│       ├── application/
│       │   ├── research_orchestrator.py
│       │   ├── evidence_service.py
│       │   ├── signal_service.py
│       │   ├── dashboard_service.py
│       │   ├── source_registry.py
│       │   ├── source_router.py
│       │   ├── forecast_service.py
│       │   ├── monitoring_service.py
│       │   ├── scoring_service.py
│       │   ├── verification_service.py
│       │   ├── report_service.py
│       │   ├── doctor_service.py
│       │   └── use_cases/
│       │       ├── run_research.py
│       │       ├── show_dashboard.py
│       │       ├── list_signals.py
│       │       ├── resume_research.py
│       │       ├── evaluate_crypto.py
│       │       ├── propose_allocation.py
│       │       ├── analyze_crisis.py
│       │       ├── issue_forecast.py
│       │       ├── monitor_forecast.py
│       │       └── resolve_forecast.py
│       │
│       ├── ports/
│       │   ├── agent_backend.py
│       │   ├── market_data.py
│       │   ├── economic_series.py
│       │   ├── documents.py
│       │   ├── events.py
│       │   ├── fundamentals.py
│       │   ├── trade_flows.py
│       │   ├── physical_flows.py
│       │   ├── positioning.py
│       │   ├── on_chain.py
│       │   ├── repositories.py
│       │   ├── cache.py
│       │   ├── clock.py
│       │   └── ids.py
│       │
│       ├── adapters/
│       │   ├── agents/
│       │   │   ├── subprocess_base.py
│       │   │   ├── codex_cli.py
│       │   │   ├── claude_cli.py
│       │   │   ├── antigravity_cli.py
│       │   │   └── event_normalizers.py
│       │   ├── data_sources/
│       │   │   ├── common/
│       │   │   │   ├── http.py
│       │   │   │   ├── files.py
│       │   │   │   ├── manifests.py
│       │   │   │   └── rate_limits.py
│       │   │   ├── market/
│       │   │   │   ├── coingecko.py
│       │   │   │   ├── yfinance.py
│       │   │   │   └── symbol_mapping.py
│       │   │   ├── economic/
│       │   │   │   ├── fred.py
│       │   │   │   └── world_bank_indicators.py
│       │   │   ├── physical/
│       │   │   │   ├── eia.py
│       │   │   │   ├── world_bank_pink_sheet.py
│       │   │   │   ├── jodi.py
│       │   │   │   └── portwatch.py
│       │   │   ├── documents/
│       │   │   │   ├── manual_url.py
│       │   │   │   ├── rss_atom.py
│       │   │   │   ├── sec_edgar.py
│       │   │   │   ├── open_dart.py
│       │   │   │   └── gdelt.py
│       │   │   ├── trade/
│       │   │   │   ├── un_comtrade.py
│       │   │   │   └── faostat.py
│       │   │   ├── positioning/
│       │   │   │   └── cftc.py
│       │   │   └── crypto/
│       │   │       └── coin_metrics.py
│       │   ├── storage/
│       │   │   ├── markdown_research.py
│       │   │   ├── markdown_signals.py
│       │   │   ├── markdown_source_status.py
│       │   │   ├── markdown_forecasts.py
│       │   │   ├── markdown_outcomes.py
│       │   │   ├── markdown_exposure_graph.py
│       │   │   ├── markdown_profiles.py
│       │   │   ├── markdown_portfolios.py
│       │   │   ├── markdown_codec.py
│       │   │   └── atomic_files.py
│       │   └── system/
│       │       ├── system_clock.py
│       │       └── uuid_generator.py
│       │
│       ├── factories/
│       │   ├── agent_factory.py
│       │   ├── source_adapter_factory.py
│       │   ├── source_plugin_registry.py
│       │   └── repository_factory.py
│       │
│       ├── research/
│       │   ├── registry.py
│       │   ├── crypto/
│       │   │   ├── workflow.py
│       │   │   ├── requirements.py
│       │   │   └── policies.py
│       │   ├── equities/
│       │   │   ├── workflow.py
│       │   │   ├── requirements.py
│       │   │   └── policies.py
│       │   └── commodities/
│       │       ├── workflow.py
│       │       ├── requirements.py
│       │       └── policies.py
│       │
│       ├── markets/
│       │   ├── registry.py
│       │   ├── us.py
│       │   ├── vn.py
│       │   └── kr.py
│       │
│       ├── analytics/
│       │   ├── returns.py
│       │   ├── volatility.py
│       │   ├── drawdown.py
│       │   ├── allocation.py
│       │   ├── exposure.py
│       │   └── stress.py
│       │
│       ├── schemas/
│       │   ├── research_plan.schema.json
│       │   ├── analysis.schema.json
│       │   ├── signal.schema.json
│       │   ├── forecast.schema.json
│       │   ├── outcome.schema.json
│       │   ├── verification.schema.json
│       │   └── report.schema.json
│       │
│       └── templates/
│           ├── prompts/
│           │   ├── plan.md
│           │   ├── analyze.md
│           │   ├── forecast.md
│           │   ├── challenge.md
│           │   ├── verify.md
│           │   └── synthesize.md
│           └── storage/
│               ├── run.md
│               ├── evidence.md
│               ├── claim.md
│               ├── signal.md
│               ├── forecast.md
│               ├── outcome.md
│               └── report.md
│
└── tests/
    ├── unit/
    │   ├── domain/
    │   ├── application/
    │   ├── analytics/
    │   └── factories/
    ├── contract/
    │   ├── agent_backends/
    │   ├── data_sources/
    │   └── repositories/
    ├── integration/
    │   ├── cli/
    │   ├── markdown_storage/
    │   └── provider_fixtures/
    └── fixtures/
        ├── agent_events/
        ├── data_sources/
        └── workspaces/
```

## Source Layout Rules

### `cli/`

Contains presentation code only. Commands call application use cases and convert results into terminal output. The dashboard presenter renders application snapshots and never performs research or external calls. Provider-specific flags must not appear here.

### `config/`

Owns FRA configuration models and merging rules. It validates provider names and options but does not instantiate providers.

### `domain/`

Contains pure finance-research models and policies. It must be importable without installing an agent CLI or any data-source client dependency.

### `application/`

Coordinates workflows and transactions over repository ports. It contains no vendor imports and no filesystem path construction.

### `ports/`

Defines the interfaces implemented by adapters. Ports belong to FRA, not to a vendor.

### `adapters/`

Contains all external integration logic. Each adapter translates vendor concepts into FRA port contracts and typed errors. Data-source adapters are grouped by evidence plane, share transport utilities, and publish a source manifest; shared HTTP code must not become a generic untyped provider API.

### `factories/`

Maps configuration to adapters. Factories are small and deterministic. The source factory loads built-ins and future `fra.data_sources` entry-point plugins into the registry; it does not choose evidence for a workflow.

### `research/`

Contains asset-class research policies and data requirements. These modules answer questions such as “which evidence is normally required for a crypto regime assessment?” They do not perform HTTP calls.

### `markets/`

Contains country or venue rules shared across asset workflows:

- identifiers and ticker suffixes;
- currencies and timezones;
- market calendars and session conventions;
- disclosure or source conventions;
- benchmark mappings.

US, Vietnam, and South Korea remain independent from the equity workflow so the same market metadata can later support ETFs, FX, or local commodities.

### `analytics/`

Contains deterministic numerical functions. An agent may request a calculation, but the calculation implementation lives here.

### `schemas/`

Contains JSON Schemas used for transient agent output. Valid JSON is converted into domain models and then persisted as Markdown.

### `templates/`

Contains versioned prompt and Markdown templates. Prompt versions are recorded in every research run.

## User Workspace Layout

Application source and user research data are separate. The default user workspace is `./fra-workspace`, configurable in `fra.toml`.

```text
fra-workspace/
├── workspace.md
├── profiles/
├── portfolios/
├── runs/
├── signals/
├── source-status/
├── forecasts/
├── exposure-graphs/
├── outcomes/
├── cache/
└── logs/
```

The detailed layout and file contracts are defined in [Markdown storage](06-markdown-storage.md).

## Naming Rules

- Use `equities`, not `stock`, for the domain package.
- Use plural package names for collections: `agents`, `adapters`, `portfolios`.
- Adapter class names include their concrete technology: `CodexCliAgentAdapter`.
- Port names describe capabilities: `AgentBackend`, not `CodexService`.
- Factory names match the port they create.
- Domain IDs are provider-independent; provider identifiers are stored as aliases.

## Import Rules

Allowed dependency direction:

```text
cli -> application -> domain
                \-> ports -> domain
adapters -> ports + domain
factories -> adapters + ports + config
bootstrap -> cli + application + factories
```

Forbidden examples:

- `domain` importing `yfinance`;
- `application` running `codex exec`;
- `cli` opening Markdown files directly;
- `MarkdownResearchRepository` importing a use case;
- `CoinGeckoMarketDataAdapter` returning raw provider JSON;
- a workflow selecting `eia` or `gdelt` by vendor name instead of declaring an evidence requirement;
- a data-source plugin bypassing usage-policy or point-in-time validation;
- a domain workflow reading environment variables.

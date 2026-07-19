# Project Structure

## Canonical Repository Layout

This document describes the implemented source layout. It is a boundary map, not a backlog of
files to create. New packages and files are added only when an implemented behavior needs them;
empty scaffolding from earlier design sketches is not part of the architecture.

```text
fra/
├── pyproject.toml
├── README.md
├── fra.example.toml
├── docs/
│   ├── README.md
│   ├── 01-mvp-scope.md ... 10-implementation-plan.md
│   └── 11-operations-and-recovery.md
├── src/fra/
│   ├── __init__.py
│   ├── __main__.py
│   ├── bootstrap.py
│   ├── cli/
│   │   ├── app.py
│   │   └── exit_codes.py
│   ├── config/
│   │   ├── loader.py
│   │   └── models.py
│   ├── domain/
│   │   ├── research.py
│   │   ├── sources.py
│   │   ├── signals.py
│   │   ├── forecasts.py
│   │   ├── portfolio.py
│   │   ├── analytics.py
│   │   ├── crisis.py
│   │   ├── documents.py
│   │   ├── economic.py
│   │   ├── market_data.py
│   │   └── supporting values, IDs, errors, time, regions, and regulatory models
│   ├── application/
│   │   ├── research_orchestrator.py
│   │   ├── research_workflows.py
│   │   ├── verification_service.py
│   │   ├── source_platform.py
│   │   ├── source_service.py
│   │   ├── source_cache.py
│   │   ├── forecast_service.py
│   │   ├── dashboard_service.py
│   │   ├── workspace_service.py
│   │   ├── crypto_market_timing.py
│   │   ├── crisis_research.py
│   │   ├── allocation_research.py
│   │   ├── agent_schemas.py
│   │   ├── prompt_templates.py
│   │   └── container.py
│   ├── ports/
│   │   ├── agent_backend.py
│   │   ├── market_data.py
│   │   ├── economic_series.py
│   │   ├── documents.py
│   │   ├── repositories.py
│   │   ├── workspace.py
│   │   ├── workspace_maintenance.py
│   │   ├── clock.py
│   │   └── ids.py
│   ├── adapters/
│   │   ├── agents/
│   │   ├── data_sources/{common,documents,economic,market}/
│   │   ├── storage/
│   │   ├── system/
│   │   ├── in_memory/
│   │   └── fakes/
│   ├── factories/
│   │   ├── agents.py
│   │   ├── sources.py
│   │   ├── source_plugins.py
│   │   └── in_memory.py
│   ├── security/
│   └── templates/prompts/{v1,v2}/
└── tests/
    ├── unit/
    ├── contract/
    ├── integration/
    └── fixtures/
```

The tree intentionally keeps cohesive domain and application slices in single modules while they
remain reviewable. For example, forecast lifecycle use cases live together in
`application/forecast_service.py`, and deterministic calculations live in `domain/analytics.py`.
They may be split when size or independent change cadence makes that useful, not merely to mirror a
hypothetical future tree.

## Source Layout Rules

### `cli/`

Contains presentation code only. Commands parse input, call application services, render output,
and map typed failures to process exit codes. Commands do not construct adapters, open Markdown
artifacts directly, or call providers.

### `config/`

Owns typed configuration and loading. It validates provider names and options but does not construct
providers.

### `domain/`

Contains pure finance-research values, aggregates, and deterministic policies. It has no subprocess,
HTTP, filesystem, YAML, Markdown, CLI, or third-party validation dependency.

### `application/`

Coordinates use cases over domain objects and ports. `SourceRegistry` and `SourceRouter` live here:
the registry indexes constructed adapters, while the router selects and executes only
policy-compatible sources. Workflow modules declare provider-neutral evidence requirements and do
not select adapters by vendor ID.

`agent_schemas.py` is the authoritative Pydantic boundary for transient agent JSON. Schemas are
generated from those models and versioned in run metadata; duplicate checked-in schema files are not
maintained.

### `ports/`

Defines FRA-owned protocols for agents, typed evidence sources, repositories, workspaces, clocks,
and IDs. Ports depend only on the domain and the standard library.

### `adapters/`

Contains external integration and persistence logic. Adapters translate vendor or filesystem
concepts into port contracts and typed errors. Data-source adapters are grouped by evidence plane and
share bounded transport and manifest utilities.

### `factories/`

Maps configuration to constructed adapters. Factories may depend on adapters, ports, domain values,
and configuration, but not on application or CLI modules. The source factory accepts a registrar
protocol supplied by the composition root, so plugin discovery and adapter construction do not
reverse the dependency direction.

### `templates/`

Contains immutable versioned prompt resources. New runs use the latest version while research-run
metadata records the version used for each stage; `v1` remains available after the `v2` crypto
contract clarification.
Markdown rendering belongs to storage adapters because the rendered format is a repository concern.

## Dependency Direction

Allowed project dependencies are:

```text
cli --------> application --------> ports --------> domain
 |                 |                  |
 +---------------> domain <-----------+

adapters ---------------------------> ports + domain
factories --------------------------> adapters + ports + domain + config
bootstrap --------------------------> cli + application + factories + adapters
```

`bootstrap.py` is the only composition root. It may know concrete implementations; inner layers may
not import it. The contract suite enforces these rules across every source file.

Forbidden examples include:

- domain importing Pydantic, Typer, HTTPX, a provider, or a repository adapter;
- application importing CLI, factory, or adapter modules;
- adapters importing application workflows;
- factories importing `SourceRegistry` or another application service;
- CLI importing a concrete adapter or factory;
- a workflow selecting `eia`, `coingecko`, or another vendor by name;
- a plugin bypassing routing, usage-policy, or point-in-time checks.

## User Workspace Layout

Application source and user research data remain separate. The configured workspace uses this stable
top-level layout:

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
├── logs/
└── .locks/
```

The detailed durable artifact contract is defined in [Markdown storage](06-markdown-storage.md).

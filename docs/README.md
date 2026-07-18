# FRA Architecture Documentation

FRA stands for **Finance Research Agents**. It is a local-first signaling, research, and forecasting system that uses an installed agentic CLI for reasoning, replaceable data-source adapters for evidence, a terminal dashboard for observation, and Markdown files for every durable result.

This documentation describes the MVP and the extension boundaries that allow FRA to add many public or licensed data sources and API-key-backed agents without rewriting its application core. The product surface remains the local CLI and Markdown.

## Document Map

1. [MVP scope and decisions](01-mvp-scope.md)
2. [Architecture](02-architecture.md)
3. [Project structure](03-project-structure.md)
4. [Components and contracts](04-components.md)
5. [Runtime flows](05-runtime-flows.md)
6. [Markdown storage](06-markdown-storage.md)
7. [Factories, adapters, and evolution](07-extensibility.md)
8. [Data-source strategy and feasibility](08-data-source-strategy.md)
9. [CLI dashboard and Markdown output contract](09-cli-dashboard-and-output-contract.md)
10. [Implementation plan](10-implementation-plan.md)

## Architecture in One Sentence

FRA's application core coordinates signaling and research through stable ports; a source registry routes typed evidence requirements to permitted adapters, Markdown repositories preserve every result, and the CLI dashboard projects those results for observation.

## Product Positioning

- **Data sources are the fuel.** Public sources are necessary, but source count alone is not a moat.
- **The research workflow is the engine.** FRA plans, challenges, verifies, monitors, and resolves forecasts consistently across agent backends.
- **The forecast ledger and exposure graph are the moat.** Time-stamped predictions, causal links, observed outcomes, and calibration compound with use.
- **Local Markdown is the trust advantage.** The user can inspect, version, move, and recover the complete research record.

## MVP Technology Commitments

| Concern | MVP choice | Future choices |
| --- | --- | --- |
| User interface | Local `fra` CLI and observational dashboard | Additional terminal views only |
| Agent execution | Installed Codex or Claude Code CLI | Antigravity CLI, provider API, local model |
| Evidence sources | Official document ingestion, World Bank Indicators, conditional CoinGecko; then EIA, FRED/ALFRED, Pink Sheet, and SEC EDGAR for the crisis slice | JODI, UN Comtrade, OpenDART, KRX, licensed feeds, and source plugins |
| Durable results | Versioned Markdown files | Same Markdown contracts; optional disposable indexes only |
| Agent transport | Subprocess plus JSON/JSONL | SDK, MCP, or provider API behind `AgentBackend` |
| Research actions | Observe, signal, forecast, and explain | Additional research and signal packs |

## Design Rules

1. The domain and application layers never import a concrete CLI, HTTP client, or storage implementation.
2. Every external boundary is represented by a port and implemented by an adapter.
3. Factories create adapters from configuration only at the composition root.
4. Agent output is untrusted until it passes structural and evidence validation.
5. Evidence carries observation, publication, first-available, revision, and retrieval times when applicable; one ambiguous `as_of` field is not sufficient for forecasting.
6. Chat history is not the system of record. Research artifacts are.
7. Persistent MVP records are Markdown. Structured JSON may be used only as an in-process or subprocess transport format.
8. FRA emits research signals only and contains no financial-account action boundary.
9. A source is enabled only when its manifest proves that the active workspace usage, attribution, and retention policy are permitted.
10. Discovery sources may locate evidence, but material claims require suitable primary or corroborating support.
11. User-facing output is limited to the CLI dashboard and Markdown artifacts.

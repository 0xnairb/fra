# MVP Scope and Architecture Decisions

## Product Goal

The MVP proves that FRA can turn an open-ended finance question into reproducible signals, evidence-backed Markdown research, and point-in-time forecasts while using an agentic CLI already authenticated on the user's machine.

The three initial research mandates are:

1. **Market timing:** “Is it a good time to invest in crypto?”
2. **Asset allocation:** “Which assets should I buy, and how much?”
3. **Crisis analysis:** “Could events A, B, C, and D lead to a crisis, and which businesses would be affected most?”

FRA provides observation, signals, scenarios, and research evidence. Its only presentation surfaces are the local CLI dashboard and Markdown results.

## In Scope

- A Python package with a local `fra` command
- A read-only `fra dashboard` view for signals, forecasts, risks, source status, and recent research
- Codex CLI and Claude Code adapters
- A provider capability check through `fra doctor`
- Structured `plan -> collect -> analyze -> verify -> synthesize` workflows
- A continuing `forecast -> monitor -> resolve -> score` lifecycle for forward-looking mandates
- Crypto, equities, and commodities as research domains
- Market-pack abstractions and identifier conventions for US, Vietnam, and South Korea; production-ready regional source coverage is staged after the three-question MVP
- A source registry and router that select providers by capability, authority, freshness, point-in-time coverage, and allowed use
- Configured RSS/Atom feeds and manual URLs for official document ingestion
- CoinGecko Demo for attributed local-evaluation crypto market data
- yfinance only as a best-effort, personal-research fallback for equities, ETFs, indices, currencies, and futures proxies
- World Bank Indicators for structural country and debt evidence
- EIA, FRED/ALFRED, World Bank Pink Sheet, and SEC EDGAR in the oil-and-fertilizer forecasting vertical slice
- Normalization of provider data into FRA-owned models
- Source, observation, publication, first-available, revision, retrieval, staleness, authority, and usage-policy metadata
- Markdown signals, research runs, evidence, claims, scenarios, forecasts, outcomes, calculations, exposure graphs, reports, profiles, and portfolios
- Deterministic calculations for returns, allocation weights, concentration, drawdown, and scenario impacts
- Timeouts, retries, caching, rate-limit handling, validation, and clear partial-failure reporting

## Out of Scope

- Any financial-account, custody, execution, or account-action boundary
- Any graphical, hosted, multi-user, or non-CLI product surface
- Any authoritative result store other than Markdown
- Guaranteed real-time or exchange-authoritative data
- Low-latency or tick-level signaling
- Autonomous personalized financial advice without a separately designed compliance boundary
- Training or fine-tuning models
- A home-grown LLM inference loop
- A generalized swarm that creates agents without explicit workflow need
- An Antigravity adapter until its non-interactive and structured-output integration is stable enough for the shared agent contract
- Commercial redistribution of data whose license only permits personal, research, or non-commercial use
- A promise of authoritative global real-time prices from free sources
- Production-ready exchange-authoritative coverage for US, Vietnam, and South Korea in the three-question MVP
- Unlicensed full-text news archives, earnings-call transcripts, live AIS tracks, or proprietary supply-chain datasets

## Initial Provider Decisions

### Agent backends

Codex CLI and Claude Code are the preferred MVP backends because both expose non-interactive execution, resumable sessions, and machine-readable output. Codex additionally exposes JSONL events and a final-output schema; Claude Code exposes JSON or streaming JSON and JSON Schema validation.

- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)

Antigravity CLI is experimental. The locally inspected `agy` version exposes `--print`, `--conversation`, and `--sandbox`, but its public README primarily documents the terminal UI and keyring authentication. FRA must detect capabilities instead of assuming parity.

- [Antigravity CLI repository](https://github.com/google-antigravity/antigravity-cli)

FRA never copies or reads provider credential files. Each agent CLI owns its authentication.

### Evidence-source backends

CoinGecko Demo is the initial crypto price adapter. Its free plan currently requires attribution, provides 10,000 monthly call credits and 100 calls per minute, and does not advertise the commercial license attached to paid plans. FRA therefore enables it only under a local-evaluation usage policy, requests update timestamps where supported, and stores provider IDs rather than treating tickers as unique.

- [CoinGecko data delivery](https://docs.coingecko.com/docs/data-delivery-methods)
- [CoinGecko endpoint overview](https://docs.coingecko.com/reference/endpoint-overview)

yfinance remains a broad-market fallback because it can retrieve historical data for many ticker types without a paid subscription. It is unofficial, its own documentation describes the Yahoo data as intended for personal use, and its coverage and behavior can change. FRA must label it best-effort, forbid it when the active usage policy is incompatible, and never present it as exchange-authoritative.

- [yfinance documentation](https://ranaroussi.github.io/yfinance/)
- [yfinance legal and usage notice](https://github.com/ranaroussi/yfinance#legal-stuff)

Forward-looking research also requires evidence that can lead prices. The first crisis vertical slice therefore adds:

- configured official RSS/Atom feeds and manual URLs for releases;
- EIA for physical energy supply, inventory, and prices;
- FRED/ALFRED for macro series and point-in-time vintages;
- World Bank Indicators for structural country vulnerability;
- World Bank Pink Sheet for monthly commodity benchmarks;
- SEC EDGAR for US filings and XBRL facts;
- GDELT only as an experimental discovery source that requires corroboration.

Later free-source candidates include Coin Metrics Community, JODI Oil and Gas, UN Comtrade, FAOSTAT fertilizer data, CFTC Commitments of Traders, the Geopolitical Risk index, UCDP, OpenDART, KRX Open API, and IMF PortWatch. Their feasibility and constraints are documented in [Data source strategy and feasibility](08-data-source-strategy.md).

Provider selection is an application routing concern implemented over FRA-owned capabilities. Vendor names do not appear in workflows or domain policies.

## Local-First Assumptions

- The user owns the machine and chooses the installed agent CLI.
- The user has already completed the provider's supported sign-in flow.
- FRA runs inside a trusted research workspace.
- Agent processes receive the minimum filesystem access needed for one research run.
- The user's provider quota, subscription, rate limits, and terms still apply.
- Research data remains on the local machine unless an external provider is explicitly invoked.

## Success Criteria

The MVP is successful when:

1. the same research command can run through either Codex CLI or Claude Code without changing application code;
2. the same use case can read CoinGecko or yfinance data only through FRA's typed market-data port;
3. one research run can be reconstructed from Markdown files without chat history;
4. every material claim links to at least one stored evidence item;
5. every market fact shows its provider and freshness;
6. agent output that violates its schema or lacks required evidence is rejected or clearly marked incomplete;
7. application tests can use an in-memory repository without changing use cases, while product results remain Markdown;
8. a data requirement can switch among compatible source adapters without changing its workflow;
9. a source with incompatible usage rights, insufficient authority, stale data, or missing point-in-time semantics is rejected visibly;
10. a forecast records what was knowable when issued and can later be resolved and scored without future-data leakage;
11. adding a new source requires a manifest, adapter, mappings, and contract tests—not changes to research use cases;
12. `fra dashboard` reconstructs its view from Markdown and every displayed result links to its Markdown artifact;
13. every completed, incomplete, or failed research operation leaves an inspectable Markdown result.

## Decision Summary

| Decision | Choice | Reason |
| --- | --- | --- |
| Product center | Agent-centric | Research planning and synthesis create the value |
| Truth plane | Data-centric | Finance requires traceable, point-in-time facts and calculations |
| Deployment | Local first | Reuses installed agent authentication and keeps state local |
| Persistence | Markdown | Human-readable, inspectable, versionable, and sufficient for MVP scale |
| User output | CLI dashboard plus Markdown | Observation in the terminal; durable results on disk |
| Source model | Typed capability ports plus registry | Supports many heterogeneous sources without one giant provider interface |
| Extensibility | Ports, adapters, registries, factories | Allows future agent APIs, paid data, and source plugins while preserving the output contract |
| Agent topology | One orchestrated workflow first | Reduces cost and coordination failure while preserving future specialization |

# Markdown Storage

## Goal

FRA uses Markdown as its permanent durable result format. A user should be able to inspect, copy, version, and recover signals and research without a database or proprietary viewer.

Markdown is the persistence format, not the in-memory domain model. Repositories convert between domain aggregates and Markdown documents.

## Transport Versus Persistence

FRA may use JSON or JSONL transiently to communicate with agent CLIs because those interfaces support structured output. After validation, that data becomes domain objects and is persisted as Markdown.

```text
Agent JSONL -> adapter -> domain object -> Markdown repository
Source JSON/CSV/XML/XLSX/ZIP -> typed adapter -> DataEnvelope -> Markdown repository
```

Raw source responses are not durable domain state by default. The MVP stores normalized evidence sufficient to reproduce the report's claims, plus a content hash, request fingerprint, and source reference. Raw retention occurs only when the source manifest and workspace policy permit it.

## Workspace Layout

```text
fra-workspace/
├── workspace.md
├── profiles/
│   └── default.md
├── portfolios/
│   └── portfolio_main.md
├── signals/
│   └── signal_01j.../
│       ├── v001.md
│       └── v002.md
├── source-status/
│   └── <provider_id>.md
├── forecasts/
│   └── forecast_01j.../
│       ├── v001.md
│       └── v002.md
├── outcomes/
│   └── outcome_01j....md
├── exposure-graphs/
│   └── oil_strait_disruption.md
├── runs/
│   └── 2026/
│       └── 07/
│           └── run_01j...
│               ├── run.md
│               ├── mandate.md
│               ├── plan.md
│               ├── evidence/
│               │   ├── ev_01j....md
│               │   └── ev_01k....md
│               ├── claims/
│               │   └── claim_01j....md
│               ├── calculations/
│               │   └── calc_01j....md
│               ├── scenarios/
│               │   └── scenario_01j....md
│               ├── verification.md
│               └── report.md
├── cache/
│   └── <provider_id>/
└── logs/
    └── 2026-07-18.md
```

Year and month partitioning avoids one unbounded directory while remaining human-navigable.

## Common Document Contract

Every stored document has YAML front matter followed by a stable Markdown body.

```markdown
---
schema: fra.evidence
schema_version: 1
id: ev_01jabc123
created_at: 2026-07-18T08:30:00Z
updated_at: 2026-07-18T08:30:00Z
---

# Evidence ev_01jabc123
```

Required common fields:

| Field | Meaning |
| --- | --- |
| `schema` | FRA document type |
| `schema_version` | Parser and migration version |
| `id` | Stable provider-independent domain ID |
| `created_at` | UTC creation time |
| `updated_at` | UTC last modification time |

Timestamps are ISO 8601. Financial timestamps additionally record their market timezone when relevant.

## Research Run

File: `run.md`

```markdown
---
schema: fra.research_run
schema_version: 1
id: run_01jabc123
workflow: crypto_market_timing
status: verifying
created_at: 2026-07-18T08:20:00Z
updated_at: 2026-07-18T08:42:00Z
agent_adapter: codex_cli
agent_cli_version: 0.144.5
agent_session_id: 0198...
prompt_versions:
  plan: 1
  analyze: 1
  verify: 1
attempts:
  plan: 1
  analyze: 1
  verify: 1
warnings: []
---

# Research Run: run_01jabc123

## Question

Is it a good time to invest in crypto?

## Progress

- [x] Plan
- [x] Collect evidence
- [x] Analyze
- [ ] Verify
- [ ] Synthesize

## Artifact Links

- [Mandate](mandate.md)
- [Plan](plan.md)
- [Verification](verification.md)
- [Final report](report.md)
```

`run.md` is the aggregate root and workflow checkpoint. A state transition is complete only after this file is atomically updated.

## Mandate

File: `mandate.md`

Stores the original question, clarified scope, user-provided constraints, workflow selection, asset universe, time horizon, and declared assumptions.

It must distinguish:

- facts supplied by the user;
- assumptions introduced by FRA;
- unresolved questions;
- exclusions.

## Plan

File: `plan.md`

```markdown
---
schema: fra.research_plan
schema_version: 1
id: plan_01jabc123
run_id: run_01jabc123
created_at: 2026-07-18T08:21:00Z
updated_at: 2026-07-18T08:21:00Z
---

# Research Plan

## Objective

Assess the current crypto market regime for a medium-risk, twelve-month horizon.

## Tasks

| ID | Task | Depends on | Status |
| --- | --- | --- | --- |
| task_1 | Collect BTC and ETH price history | — | complete |
| task_2 | Calculate volatility and drawdown | task_1 | complete |
| task_3 | Build three scenarios | task_1, task_2 | pending |

## Data Requirements

| ID | Asset | Metric | Window | Freshness |
| --- | --- | --- | --- | --- |
| data_1 | bitcoin | price, volume, market cap | 365 days | 1 hour |
| data_2 | ethereum | price, volume, market cap | 365 days | 1 hour |
```

## Evidence

One file per evidence item prevents one large document from becoming a write-conflict hotspot.

```markdown
---
schema: fra.evidence
schema_version: 1
id: ev_01jabc123
run_id: run_01jabc123
kind: market_series
provider: coingecko
adapter_version: 0.1.0
provider_instrument_id: bitcoin
instrument_id: crypto:bitcoin
source_url: https://api.coingecko.com/api/v3/coins/bitcoin/market_chart
authority_class: aggregator
independence_group: coingecko
observed_at: 2026-07-18T08:29:42Z
published_at: 2026-07-18T08:29:50Z
available_at: 2026-07-18T08:29:50Z
retrieved_at: 2026-07-18T08:30:00Z
expires_at: 2026-07-18T09:30:00Z
currency: USD
timezone: UTC
is_stale: false
is_delayed: false
content_hash: sha256:...
request_fingerprint: sha256:...
usage_policy_id: coingecko_demo_local_evaluation_v1
allowed_usage_profile: local_personal_research
raw_retention: prohibited
required_attribution: Data provided by CoinGecko
created_at: 2026-07-18T08:30:00Z
updated_at: 2026-07-18T08:30:00Z
---

# Bitcoin Market Evidence

## Summary

Normalized daily observations used by this research run.

## Observations

| Time | Price | Market cap | Volume |
| --- | ---: | ---: | ---: |
| 2026-07-17T00:00:00Z | 00000.00 | 0000000000 | 00000000 |
| 2026-07-18T00:00:00Z | 00000.00 | 0000000000 | 00000000 |

## Provider Warnings

- Demo data is best-effort and subject to provider limits.
```

Example values are placeholders; production files contain actual normalized observations.

Large time series must be bounded to the observations required by the workflow. FRA does not persist unlimited raw provider payloads in Markdown.

### Evidence time semantics

`observed_at`, `published_at`, `available_at`, `effective_at`, and `retrieved_at` are not aliases:

- `observed_at` or a period range describes when the measured fact occurred;
- `published_at` describes when the publisher released it;
- `available_at` is the earliest time FRA could legitimately have known it;
- `effective_at` describes when a rule or decision takes effect;
- `retrieved_at` describes when FRA fetched it;
- `revised_at` and `vintage` identify later corrections.

Forecast backtests select on `available_at`, not observation period. Missing point-in-time metadata makes an item ineligible for historical prediction scoring unless the limitation is explicit.

## Claim

```markdown
---
schema: fra.claim
schema_version: 1
id: claim_01jabc123
run_id: run_01jabc123
materiality: high
status: verified
confidence: medium
evidence_ids:
  - ev_01jabc123
  - calc_01jdef456
created_at: 2026-07-18T08:38:00Z
updated_at: 2026-07-18T08:43:00Z
---

# Claim

Bitcoin remains in a high-volatility regime relative to the selected twelve-month baseline.

## Support

- [Bitcoin market evidence](../evidence/ev_01jabc123.md)
- [Volatility calculation](../calculations/calc_01jdef456.md)

## Limitations

- The conclusion depends on the selected lookback and sampling interval.
```

A citation is an evidence ID plus a relative Markdown link. A URL alone is not an FRA citation because it does not identify the normalized evidence actually used.

## Calculation

Calculation files record inputs, formula version, parameters, output, units, and implementation version.

```markdown
---
schema: fra.calculation
schema_version: 1
id: calc_01jdef456
run_id: run_01jabc123
calculation: annualized_volatility
calculation_version: 1
input_evidence_ids:
  - ev_01jabc123
created_at: 2026-07-18T08:35:00Z
updated_at: 2026-07-18T08:35:00Z
---

# Annualized Volatility

## Parameters

| Parameter | Value |
| --- | ---: |
| Return interval | daily |
| Annualization factor | 365 |
| Lookback | 365 days |

## Result

| Metric | Value | Unit |
| --- | ---: | --- |
| Annualized volatility | 0.00 | decimal |
```

## Scenario

Scenario documents separate observations from assumptions.

Required sections:

- scenario statement;
- probability band rather than false precision;
- assumptions;
- causal transmission channels;
- affected instruments, sectors, or businesses;
- supporting evidence;
- invalidation signals;
- expected impact range;
- limitations.

## Signal

Directory: `signals/<signal_id>/`; one immutable file per version.

Required front matter includes signal ID and version, subject IDs, stance, strength, confidence, horizon, `issued_at`, `knowledge_cutoff_at`, evidence and calculation IDs, freshness, next review time, lifecycle status, and supersession.

Required body sections are:

1. signal summary;
2. evidence and calculations;
3. rationale or transmission path;
4. counter-evidence;
5. invalidation conditions;
6. limitations and warnings;
7. links to the research run and report.

Signals are observation results. Nothing in the document is an executable account instruction.

## Source Status

File: `source-status/<provider_id>.md`

Stores the last explicit `fra sources check` result: provider ID, checked time, normalized health, capability warnings, quota or limit warning, and typed error when present. It is historical observation state for the dashboard, not permission for the dashboard to make a live request.

## Forecast

Directory: `forecasts/<forecast_id>/`; one immutable file per version.

```markdown
---
schema: fra.forecast
schema_version: 1
id: forecast_01jabc123
version: 1
status: issued
question: Will benchmark oil exceed the declared threshold before the horizon?
issued_at: 2026-07-18T09:00:00Z
knowledge_cutoff_at: 2026-07-18T08:55:00Z
horizon_end: 2026-10-18T00:00:00Z
probability: 0.35
resolution_rule_version: 1
evidence_ids: [ev_01jabc123]
supersedes: null
created_at: 2026-07-18T09:00:00Z
updated_at: 2026-07-18T09:00:00Z
---

# Forecast

## Hypothesis

The declared event will occur before the horizon.

## Transmission path

Event -> physical constraint -> inventory response -> price threshold.

## Alternatives and invalidation conditions

- Alternative: supply is rerouted before inventories tighten.
- Invalidate the transmission hypothesis if the declared passage and inventory indicators normalize.
```

A probability update creates `v002.md` with its new cutoff, evidence, and reason. The original probability remains scoreable.

## Outcome

File: `outcomes/<outcome_id>.md`

An outcome records the linked forecast, resolution date, authoritative evidence, resolved value (`true`, `false`, numeric, categorical, or `ambiguous`), rule version, and deterministic scores. Ambiguous cases remain visible and are never silently removed from performance reports.

## Exposure Graph

File: `exposure-graphs/<graph_id>.md`

The body contains human-readable node and edge tables. Example edge columns are `from`, `to`, `relationship`, `direction`, `expected_lag`, `confidence`, `jurisdiction`, and `evidence_ids`. This supports causal paths such as:

```text
strait restriction -> seaborne oil capacity -> oil price -> fertilizer feedstock cost -> company margin
```

Graphs are versioned hypotheses, not asserted truth. Each material edge requires evidence, a confidence, and an invalidation condition.

## Verification

File: `verification.md`

Contains deterministic and agent-assisted verification results:

```text
claim coverage
citation validity
freshness
numeric consistency
currency and unit consistency
contradictions
unsupported claims
required follow-up
```

The report cannot be marked complete while a high-materiality verification issue remains unresolved unless the report visibly carries an incomplete status.

## Final Report

File: `report.md`

Recommended stable sections:

1. Research question
2. Executive conclusion
3. User constraints and assumptions
4. Current evidence
5. Scenarios
6. Risks and counter-thesis
7. Suggested decision framework
8. Invalidation and monitoring signals
9. Limitations
10. Sources and evidence links

The report is the main human-readable run result. Signals, evidence, claims, calculations, and scenarios remain separately addressable Markdown results.

## Profiles and Portfolios

### Investor profile

File: `profiles/<profile_id>.md`

Stores a confirmed investment objective, time horizon, risk tolerance and capacity, liquidity needs,
loss tolerance, restrictions, tax jurisdiction, and user-confirmed assumptions. Sensitive free-form
personal information should be minimized.

### Portfolio

File: `portfolios/<portfolio_id>.md`

Stores user-supplied positions or a proposed research allocation. It is not a transaction ledger.

```markdown
| Instrument ID | Symbol | Weight | Currency | As of |
| --- | --- | ---: | --- | --- |
| equity:us:AAPL | AAPL | 0.10 | USD | 2026-07-18 |
```

Weights are stored as decimals. Display percentages are rendered from decimals.

## Indexing and Queries

Markdown files are the source of truth. The repository lists runs by scanning front matter and may maintain an in-memory index during one process.

An optional generated `index.md` may improve navigation, but it is disposable and must never be required for recovery.

## Caching

Source cache entries are also Markdown with front matter containing request fingerprint, provider, retrieval time, availability time, expiry, usage policy, raw-retention rule, and normalized content hash.

Cache rules:

- cache is never treated as fresh after `expires_at`;
- workflows may explicitly allow stale cache with a warning;
- a cached observation retains its original observed, published, available, revised, and retrieval times;
- a cache entry is reusable only under a compatible usage profile and retention policy;
- cache files may be deleted without corrupting research runs;
- evidence copied into a run remains immutable even after cache eviction.

## Atomicity and Concurrency

The Markdown adapter uses:

1. a per-aggregate lock;
2. rendering to a temporary sibling file;
3. file flush and optional filesystem sync;
4. atomic replace;
5. lock release.

Research artifacts are append-mostly. Existing evidence and calculation files are immutable; corrections create a new version and record supersession metadata.

## Schema Evolution

Every document declares `schema` and `schema_version`.

Migration rules:

- parsers reject newer unsupported major schemas;
- migrations operate through domain models, not text replacement;
- migrations write into a new workspace or create a complete backup first;
- IDs and citation links remain stable;
- a migration report records converted, skipped, and failed files.

These rules also allow disposable search indexes to be rebuilt from the same versioned documents. An index never becomes the authoritative result store.

## Privacy and Security

- No agent or data-source secret is persisted.
- Workspace files use owner-only permissions where supported.
- Agent prompts receive only the profile fields required for the active mandate.
- Logs redact configured secret values and avoid full source payloads.
- Export is an explicit user action.

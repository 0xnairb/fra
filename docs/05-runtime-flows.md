# Runtime Flows

## Common Research Flow

All three initial research mandates use the same controlled workflow.

### Step 1: Bootstrap

1. `fra` finds the workspace and loads `fra.toml`.
2. The composition root validates configuration.
3. Factories create the selected agent and storage adapters plus every enabled data-source adapter.
4. `SourceRegistry` validates source manifests and indexes their typed capabilities.
5. `DoctorService` verifies required binaries, source policy, and provider configuration.

### Step 2: Create the mandate

1. The CLI captures the question and optional flags.
2. The application creates a `ResearchMandate` with an ID and timestamp.
3. The repository saves the initial run as Markdown.
4. Missing material inputs cause `NEEDS_USER_INPUT` rather than silent assumptions.

### Step 3: Plan

1. `ResearchOrchestrator` sends a planning request through `AgentBackend`.
2. The adapter invokes the chosen agentic CLI with a plan output schema.
3. Vendor events are normalized into FRA agent events.
4. The returned `ResearchPlan` is structurally and semantically validated.
5. The plan is saved before execution.

### Step 4: Collect evidence

1. The selected research workflow validates and converts its typed plan requirements into FRA-owned provider requests.
2. `SourceRouter` filters registered adapters by capability, usage rights, authority, scope, point-in-time support, freshness, quota, and health.
3. The routing decision records selected, rejected, fallback, cross-check, and discovery sources.
4. The router executes only selected adapters. A fallback runs only when no selected primary succeeds.
5. Adapters return normalized envelopes containing provenance, distinct time semantics, policy, and freshness metadata; the workflow converts them into bounded evidence and deterministic calculations.
6. The orchestrator saves evidence and calculations before analysis. The collect checkpoint preserves the routing decision used by the workflow.

The agent does not invent provider calls or directly persist provider payloads.

### Step 5: Analyze

1. The application renders a bounded evidence bundle.
2. The agent backend analyzes only the mandate, assumptions, and supplied evidence.
3. The result is validated into typed claims, evidence-backed scenarios, and open questions.
4. Claims and scenarios are persisted as independently addressable Markdown before verification.
5. Claims may cite the deterministic calculations persisted during collection.

### Step 6: Verify

1. `VerificationService` checks claim citations, freshness, numerical consistency, and contradictory evidence.
2. An agent verification stage challenges causal reasoning and missing risks.
3. Deterministic failures, an explicit agent rejection, and high-severity agent issues block the run.
   Low- and medium-severity advisories remain in the verification artifact without overriding an
   otherwise passing result.
4. Failed verification returns a structured research gap.
5. The orchestrator either collects more evidence, asks the user, or marks the report incomplete.

### Step 7: Synthesize

1. The backend receives verified claims, calculations, scenarios, and limitations.
2. It returns a structured final artifact.
3. FRA validates and persists any signal version produced by the workflow.
4. `ReportRenderer` produces `report.md`.
5. The run transitions to `COMPLETED` only after the signal and final Markdown artifact validate and persist.

Terminal summaries are convenience views. The Markdown signal and report are the durable results.

## Agent Subprocess Flow

```text
ResearchOrchestrator
        |
        | AgentStageRequest
        v
AgentBackend port
        |
        v
Codex/Claude/Antigravity adapter
        |
        | argument array + stdin
        v
Local agent process
        |
        | stdout events / stderr progress / exit code
        v
Vendor event parser
        |
        | AgentEvent + AgentStageResult
        v
Schema and policy validation
```

The subprocess adapter must:

- avoid shell-string interpolation;
- set an explicit working directory;
- use a new process group so cancellation terminates child processes;
- capture stdout and stderr separately;
- enforce a timeout;
- stream progress without treating it as durable evidence;
- record binary name and version;
- extract the provider session ID;
- redact known secret values from diagnostics;
- return typed failures for missing binary, missing authentication, timeout, cancellation, invalid output, and non-zero exit.

## Crypto Market-Timing Flow

Question:

> Is it a good time to invest in crypto?

1. Collect the forward interpretation horizon, categorical risk tolerance, bounded historical lookback, currency, and BTC/ETH asset scope. The lookback does not need to equal the horizon.
2. The plan requests only price, volume, market capitalization, and deterministic return, volatility, and drawdown evidence required by the first release.
3. The router selects permitted CoinGecko evidence and records its local-evaluation policy, attribution, and routing decision.
4. For current research, the workflow freezes the knowledge cutoff after retrieval so every selected envelope was actually available by that cutoff. A user-supplied historical cutoff remains immutable and rejects later evidence.
5. The collect checkpoint preserves the declared-input semantics, requested and observed windows, first/latest source values, currency, retrieval times, and formula conventions alongside evidence and calculation IDs.
6. Deterministic analytics calculate point-to-point return, sample volatility annualized at 365 periods, current drawdown, and maximum drawdown.
7. The agent builds bullish, base, and bearish scenarios from that durable contract. It may retain non-blocking advisories but cannot waive a high-severity evidence gap.
8. Verification checks timestamps, numerical statements, missing risks, and claims of certainty.
9. The report gives conditions, scenarios, and risk limits—not an unconditional “buy now.”

## Asset-Allocation Flow

Question:

> Which assets should I buy, and how much?

1. Load or create an `InvestorProfile`.
2. Reject the workflow if critical suitability fields are absent.
3. Resolve the asset universe and fetch normalized historical, macro, filing, and exposure evidence as required.
4. Deterministic services calculate correlations, volatility, drawdowns, concentration, and candidate weights.
5. The agent explains tradeoffs and proposes alternatives; it does not calculate weights freehand.
6. Stress scenarios test the proposed allocation.
7. The final Markdown report records assumptions, constraints, weights, risks, and rebalancing conditions.

The proposed allocation remains a Markdown research signal and is never sent outside FRA.

## Crisis-Analysis Flow

Question:

> Could events A, B, C, and D lead to a crisis, and which businesses would be affected most?

1. Normalize each event with time, geography, affected entities, and evidence status.
2. The planner creates candidate transmission channels such as funding, demand, supply, currency, rates, regulation, or confidence.
3. Data collection gathers relevant official releases, macro proxies, physical supply/demand, trade and passage flows, filings, positioning, asset prices, and company exposures.
4. Independent research tasks may run concurrently when they use disjoint evidence scopes.
5. A skeptic stage builds counter-scenarios and invalidation conditions.
6. Deterministic scoring ranks exposure, sensitivity, balance-sheet resilience, and data confidence.
7. The final report separates observed facts, causal hypotheses, probability bands, leading indicators, and affected businesses.

Discovery sources such as GDELT may identify candidate events or documents, but material claims require the underlying official document or independent corroboration. Historical forecasts request `point_in_time_at`; the router rejects observations that were published or available after that cutoff.

## Forecast Lifecycle Flow

Research and forecasting share evidence collection, but a forecast is a separate durable object.

### Issue

1. Create a hypothesis with target, horizon, probability, transmission path, alternatives, and invalidation conditions.
2. Freeze `knowledge_cutoff_at` and ensure every supporting item has `available_at <= knowledge_cutoff_at`.
3. Save an immutable forecast version and its evidence snapshot before observing the outcome.

### Monitor

1. A scheduled or manual run evaluates declared leading indicators.
2. New evidence is appended with its retrieval and availability times.
3. Probability changes create a new forecast version with a reason; they never overwrite the original.

### Resolve and score

1. Apply the forecast's predeclared resolution rule after the horizon or terminal event.
2. Save the outcome separately, including the authoritative observation and ambiguity notes.
3. Compute deterministic calibration and usefulness scores, such as Brier score for probabilistic binary outcomes.
4. Aggregate performance by workflow, horizon, source mix, and event class without hiding unresolved or ambiguous cases.

This ledger is the basis for learning which signals and workflows predict well. A persuasive report without a frozen, resolved forecast does not count as predictive evidence.

## CLI Dashboard Flow

`fra dashboard` is the primary observation surface.

1. The CLI calls `ShowDashboard`.
2. `DashboardService` queries Markdown-backed signal, forecast, outcome, research, and source-status repositories.
3. It calculates freshness and warning priority and returns `DashboardSnapshot`.
4. The CLI presenter renders terminal panels and Markdown artifact paths.
5. With `--watch`, the presenter reloads local repository state when files change.

The dashboard performs no implicit agent or network call. `fra monitor` explicitly collects new evidence, updates signal or forecast versions, and persists Markdown before the dashboard can display the change.

## Resume Flow

`fra resume RUN_ID` loads the Markdown run aggregate and selects the next safe action.

- If the agent session is resumable and the configured backend matches, FRA supplies its stored provider session ID.
- If the backend changed or the session expired, FRA starts a new backend session from durable artifacts.
- Correctness must never depend on the provider's hidden conversation state.

## Failure and Recovery

| Failure | FRA behavior |
| --- | --- |
| Agent CLI missing | Stop with installation guidance from the adapter |
| Agent not authenticated | Stop with provider-specific login guidance |
| Required source capability unavailable | Try a policy-compatible fallback; otherwise stop or explicitly mark the research incomplete |
| Source usage policy incompatible | Reject the source; never silently weaken the workspace usage profile |
| Point-in-time evidence unavailable | Stop historical scoring or label the related claim non-backtestable |
| Rate limited | Respect retry metadata and use a fresh-enough, retention-permitted cached evidence item when policy allows |
| Agent timeout | Persist state and allow resume or retry |
| Invalid structured output | One bounded repair attempt, then fail the stage |
| Unsupported claim | Return to evidence collection or label the report incomplete |
| Markdown write failure | Do not advance workflow state |
| Cancellation | Terminate subprocess group and persist `CANCELLED` |

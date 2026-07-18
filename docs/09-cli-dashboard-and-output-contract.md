# CLI Dashboard and Markdown Output Contract

## Permanent Product Boundary

FRA is a local signaling and finance-research system. It observes evidence, produces signals and forecasts, and explains them. It does not act on financial accounts and it is not a hosted application.

FRA has exactly two user-facing output surfaces:

1. a terminal dashboard for observing current signals, forecasts, risks, source health, and research status;
2. Markdown files containing every durable signal, forecast, evidence item, calculation, verification result, and report.

This is a permanent product constraint, not merely an MVP limitation.

## Output Flow

```text
Sources + agentic CLI + deterministic analytics
                       |
                       v
             FRA application services
                       |
                       v
             Versioned Markdown files
                       |
                       v
          Read-only terminal dashboard
```

Markdown is the system of record. The dashboard is a disposable projection of Markdown state. If the dashboard and a file disagree, the file wins and the dashboard must be rebuilt.

## Signal Contract

A signal is an observation-oriented research conclusion, not an action instruction.

Each signal records:

```text
signal ID and version
subject and provider-independent instrument IDs
stance or direction
strength and confidence
time horizon
issued_at and knowledge_cutoff_at
supporting evidence and calculation IDs
causal or research rationale
invalidation conditions
freshness and next-review time
status: active, weakened, invalidated, expired, or resolved
limitations and warnings
```

A signal update creates a new version. FRA never rewrites the originally observed signal, confidence, or knowledge cutoff.

## CLI Dashboard

Primary command:

```text
fra dashboard
fra dashboard --watch
```

The dashboard should contain five compact panels:

```text
FRA Dashboard | workspace | UTC time | last Markdown refresh

Signals
Subject     Stance       Strength  Confidence  Horizon   Freshness  Status

Forecasts
Question    Probability  Horizon   Updated     State     Score

Risk Watch
Event       Transmission path      Exposed subjects     Severity   Next check

Sources
Provider    Role          Freshness  Health     Quota/limit warning

Recent Research
Run         Mandate       State      Updated    Verification      Result path
```

Dashboard behavior:

- it reads normalized repository objects backed by Markdown;
- it does not invoke an agent or network source by default;
- `--watch` reloads local Markdown when files change;
- monitoring and evidence refresh occur through explicit `fra monitor` or research commands, which persist results before the dashboard displays them;
- every detailed row exposes or prints the corresponding Markdown path;
- stale, incomplete, conflicting, and invalidated states remain visible;
- terminal color is supplementary; text labels carry the meaning;
- a non-interactive plain-text mode remains available for logs and terminal automation.

The dashboard may maintain an in-memory index during one process. It must be fully reconstructable after restart by scanning Markdown front matter.

## Markdown Results

Every completed or incomplete research operation produces Markdown. Important result locations are:

```text
fra-workspace/
├── signals/<signal_id>/vNNN.md
├── source-status/<provider_id>.md
├── forecasts/<forecast_id>/vNNN.md
├── outcomes/<outcome_id>.md
├── exposure-graphs/<graph_id>.md
└── runs/<year>/<month>/<run_id>/
    ├── run.md
    ├── mandate.md
    ├── plan.md
    ├── evidence/*.md
    ├── claims/*.md
    ├── calculations/*.md
    ├── scenarios/*.md
    ├── verification.md
    └── report.md
```

Rules:

- `report.md` is the main human-readable result for a research run;
- signal and forecast files are independently addressable results, not dashboard-only state;
- incomplete and failed runs retain their evidence and a visible status;
- transient JSON or JSONL is allowed only between a CLI adapter and FRA validation;
- generated caches and indexes are disposable and never replace Markdown;
- future internal optimizations must continue emitting the same Markdown contracts.

## Eliminated Product Surfaces

FRA will not add:

- financial-account connectivity, custody, execution, or account-action endpoints;
- a browser-based or desktop graphical interface;
- a hosted, multi-user application or user-account system;
- an HTTP product API that replaces the local CLI;
- a database as the authoritative result store.

Agent provider APIs and data-source HTTP APIs remain valid adapters because they are implementation inputs, not FRA user-facing product surfaces.

## Implementation Responsibilities

### `SignalService`

- validates signal structure and supporting evidence;
- freezes the knowledge cutoff;
- persists immutable versions through `SignalRepository`;
- transitions signal lifecycle state;
- never sends a signal to an external account or action system.

### `DashboardService`

- queries signal, forecast, outcome, research, and source-status repositories;
- produces a provider-independent `DashboardSnapshot`;
- calculates display freshness and warning priority deterministically;
- performs no rendering and makes no direct filesystem, network, or subprocess call outside its ports.

### CLI presenter

- converts `DashboardSnapshot` to terminal tables;
- supports interactive refresh and plain-text output;
- does not read files or call sources directly;
- contains no research or signal-ranking logic.

## Acceptance Criteria

The output boundary is correctly implemented when:

1. `fra dashboard` can rebuild its complete view from Markdown after process restart;
2. deleting a disposable cache or index does not remove a signal or result;
3. every displayed signal and forecast points to a Markdown artifact;
4. dashboard watch mode performs no implicit external call;
5. every research command leaves a Markdown result, including incomplete work;
6. no application port represents an external account action;
7. no roadmap or factory contains an alternative graphical or hosted product surface;
8. a future storage optimization cannot disable Markdown emission.

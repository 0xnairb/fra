# Finance Research Agents

Finance Research Agents (FRA) is a local-first system for evidence-backed financial research,
signals, and forecasting. It uses replaceable agent and data-source adapters while keeping durable
results in human-readable Markdown.

FRA is research software. It has no brokerage, custody, trading, or financial-account integration.

## Status

FRA is under active implementation. WP0 and WP1 provide the packaged CLI, configuration boundary,
domain kernel, ports, deterministic fakes, and initial quality gates. Later work-package components
exist, but WP2 through WP9 remain in convergence until their documented end-to-end contracts and
exit gates are satisfied. In particular, do not treat fixture-backed adapters or stage checkpoints
alone as proof that the corresponding user workflow is complete.

The authoritative remaining delivery gates are in the
[implementation plan](docs/10-implementation-plan.md). This status section is intentionally
conservative: a work package is complete only when its observable command, durable Markdown
artifacts, replacement boundaries, and hermetic release tests all agree with the design documents.

The CLI exposes `init`, `research run`, `research crypto`, `research crisis`,
`research allocation`, `resume`, `dashboard`, `signals`, `forecasts`, `forecast show`, `monitor`,
`resolve`, `runs`, `show`, staged `doctor`, and the `sources list`, `sources describe`, and
`sources check` commands in addition to `--version` and `--help`. The full delivery sequence is defined in the
[implementation plan](docs/10-implementation-plan.md).

Regional readiness is visible through `fra regions list` and `fra regions describe CODE`.
Operational commands are `fra workspace export`, `fra workspace migrate`, and
`fra workspace rebuild-index`; see the [operations and recovery guide](docs/11-operations-and-recovery.md).

## Quick start

FRA requires Python 3.12 or newer and uses
[uv](https://docs.astral.sh/uv/) with a committed lock file.

```console
git clone git@github.com:0xnairb/fra.git
cd fra
uv sync --locked --all-groups
cp fra.example.toml fra.toml
uv run fra --version
uv run fra --help
uv run fra init
uv run fra doctor
uv run fra research allocation --horizon-years 10 --risk-tolerance medium \
  --risk-capacity medium --investment-objective "Long-term capital growth" \
  --maximum-loss 0.35 --liquidity-need 0.10 --tax-jurisdiction US
uv run fra dashboard --plain-text
```

The shipped example leaves the optional Codex profile unset and enables yfinance as a no-key,
personal-research-only source, so the allocation command above has a runnable source route after the
selected agent CLI is authenticated. To select a named Codex profile, first create
`$CODEX_HOME/<name>.config.toml` (normally `~/.codex/<name>.config.toml`), then set
`agent.options.profile = "<name>"`; `fra doctor` reports a missing profile before research starts.
Unknown options are rejected. Secrets must be referenced through environment-variable names in
`*_env` options; inline secret values are rejected and redacted from diagnostics.

`fra init` is idempotent and preserves existing content. `fra doctor` is deliberately staged. It
validates source manifests, typed source capabilities, dated terms reviews, the configured agent
binary and capabilities, and safe CLI-managed authentication status. These checks use no
network source call or model quota. Only `fra sources check` performs a source health call;
`fra research` is the explicit quota-consuming agent operation.

`fra research run` exposes the shared orchestration skeleton for registered research packs. FRA
fails it as incomplete when no evidence workflow is registered for the selected mandate; it does
not manufacture an evidence-free general answer.

FRA uses the installed Codex CLI in a read-only sandbox by default. Set `agent.provider` and
`agent.options.binary` to `claude_cli` and `claude` to use Claude Code instead. Authenticate the
selected CLI before research. Every completed stage is recorded in `run.md`; `fra resume RUN_ID`
starts at the next uncheckpointed stage and starts a fresh provider session if the backend changed.

Crypto research requires the CoinGecko source to be enabled and `COINGECKO_DEMO_API_KEY` to name
the Demo credential environment variable. Reports retain the required CoinGecko attribution and
the local-evaluation usage policy. Missing horizon or risk tolerance creates a durable
`needs_user_input` run instead of assuming suitability inputs.

Crisis research requires the EIA, World Bank Pink Sheet, FRED/ALFRED, and SEC EDGAR sources shown in
the example to be enabled, with the documented provider credentials and a real SEC contact
`User-Agent`. They remain disabled in the first-run configuration because that workflow has several
operator prerequisites.

Allocation research additionally requires the yfinance fallback and complete suitability inputs.
It persists the confirmed profile, deterministic proposed weights, stress metrics, and an immutable
signal. yfinance is unofficial, best effort, and limited to local personal research; FRA does not
expose any order, account, brokerage, or custody action.

## Architecture

FRA follows ports and adapters:

- the domain owns research, evidence, signal, instrument, and state invariants;
- application services coordinate use cases through FRA-owned protocols;
- adapters normalize agent, provider, clock, ID, and repository behavior;
- factories construct adapters only at the composition root;
- external payloads and provider identifiers do not become domain contracts.

The application core remains testable with deterministic clocks and IDs, fake agents and sources,
and in-memory repositories. See the [architecture guide](docs/02-architecture.md) and
[component contracts](docs/04-components.md).

## Development

Run the same hermetic gates as CI:

```console
uv run --locked pytest
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv build
```

The default verification path requires no provider credentials, live service, or installed agent
CLI. Set `FRA_RUN_LIVE_CODEX=1` or `FRA_RUN_LIVE_CLAUDE=1` to opt into each installed CLI's
structured-output smoke test. Set `FRA_RUN_LIVE_WP8=1` to run the same fixture-source allocation
workflow through both installed CLIs. Set `FRA_RUN_LIVE_CRYPTO=1` with
`COINGECKO_DEMO_API_KEY` to opt into the complete CoinGecko plus Codex crypto workflow smoke test.

Expected CLI outcomes use stable process codes:

| Code | Meaning |
| ---: | --- |
| `0` | Success |
| `1` | Incomplete result |
| `2` | User input required |
| `3` | Configuration failure |
| `4` | External dependency failure |
| `5` | Corrupt or unsupported data |
| `70` | Unexpected internal failure |

## Documentation

Start with the [documentation map](docs/README.md). The primary references are:

- [MVP scope and decisions](docs/01-mvp-scope.md)
- [Architecture](docs/02-architecture.md)
- [Project structure](docs/03-project-structure.md)
- [Components and contracts](docs/04-components.md)
- [Runtime flows](docs/05-runtime-flows.md)
- [Markdown storage](docs/06-markdown-storage.md)
- [Extensibility](docs/07-extensibility.md)
- [Data-source strategy](docs/08-data-source-strategy.md)
- [CLI and Markdown output contract](docs/09-cli-dashboard-and-output-contract.md)
- [Implementation plan](docs/10-implementation-plan.md)
- [Operations and recovery](docs/11-operations-and-recovery.md)
- [WP2-WP9 release traceability](docs/12-release-traceability.md)

## License

Licensed under the [Apache License 2.0](LICENSE).

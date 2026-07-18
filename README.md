# Finance Research Agents

Finance Research Agents (FRA) is a local-first system for evidence-backed financial research,
signals, and forecasting. It uses replaceable agent and data-source adapters while keeping durable
results in human-readable Markdown.

FRA is research software. It has no brokerage, custody, trading, or financial-account integration.

## Status

The repository currently implements the first two work packages:

- **WP0 — foundation:** packaged `fra` CLI, strict TOML configuration, stable exit codes,
  diagnostics, secret redaction, CI, and quality gates.
- **WP1 — domain kernel:** provider-independent domain models, evidence provenance and point-in-time
  safeguards, research-run transitions, typed ports and failures, deterministic fakes, in-memory
  repositories, and composition-root wiring.

The CLI currently exposes `--version`, `--help`, and the runtime/configuration stage of `doctor`.
Markdown persistence and the observational dashboard arrive in WP2. The full delivery sequence is
defined in the [implementation plan](docs/10-implementation-plan.md).

## Quick start

FRA requires Python 3.12 or newer and uses
[uv](https://docs.astral.sh/uv/) with a committed lock file.

```console
git clone git@github.com:0xnairb/fra.git
cd fra
uv sync --locked --all-groups
uv run fra --version
uv run fra --help
uv run fra doctor
```

Copy `fra.example.toml` to `fra.toml` when local configuration is needed. Unknown options are
rejected. Secrets must be referenced through environment-variable names in `*_env` options; inline
secret values are rejected and redacted from diagnostics.

`fra doctor` is deliberately staged. At the current milestone it checks only Python and
configuration, without network requests, source calls, agent processes, credentials, or quota use.

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
CLI. Live adapter tests are opt-in when their owning work package introduces them.

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

## License

Licensed under the [Apache License 2.0](LICENSE).

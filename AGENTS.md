# Development Guide

## Purpose

This file defines how development work should be approached in this repository. Project scope, architecture, component contracts, data-source decisions, persistence formats, and implementation milestones belong in `docs/` and should not be duplicated here.

Treat documentation as the design reference and the repository as the current implementation state. Never assume a documented component already exists without inspecting the code.

## Starting Work

At the beginning of a fresh task:

1. read the user request and identify the intended observable outcome;
2. inspect the repository tree, relevant code, tests, configuration, and local changes;
3. use `docs/README.md` to locate the relevant design references;
4. identify the smallest behavior that can satisfy the request;
5. define how that behavior will be verified before editing code;
6. note any ambiguity, external dependency, migration, or compatibility risk.

Do not begin by creating abstractions or files from the proposed structure. Begin from the behavior and the current repository state.

## Documentation Routing

Start with `docs/README.md`, then read only the references needed for the task:

| When working on | Read |
| --- | --- |
| Product scope, non-goals, or MVP acceptance | `docs/01-mvp-scope.md` |
| Dependency direction, layers, states, or system boundaries | `docs/02-architecture.md` |
| Package placement, naming, or import rules | `docs/03-project-structure.md` |
| Ports, domain contracts, services, factories, or errors | `docs/04-components.md` |
| Orchestration, command behavior, resume, monitoring, or failures | `docs/05-runtime-flows.md` |
| Markdown layout, schemas, atomicity, or migrations | `docs/06-markdown-storage.md` |
| Adapter extension, portability, contract tests, or versioning | `docs/07-extensibility.md` |
| Source feasibility, authority, licensing, or routing policy | `docs/08-data-source-strategy.md` |
| CLI dashboard, signals, or durable output behavior | `docs/09-cli-dashboard-and-output-contract.md` |
| Delivery sequence, release gates, testing strategy, or backlog | `docs/10-implementation-plan.md` |

Read multiple documents when a change crosses boundaries. For example, a new persisted adapter result commonly requires the component contract, runtime flow, Markdown schema, source policy, and implementation plan.

If code and documentation disagree:

- do not silently choose one;
- determine whether the code is incomplete or the design has changed;
- preserve the approved design unless the user authorizes a change;
- update affected documentation in the same change when behavior or architecture intentionally changes.

## Development Philosophy

### Work in small complete increments

- Prefer a thin, executable vertical slice over broad unfinished scaffolding.
- Make one primary behavioral change at a time.
- Implement only what the current acceptance criteria require.
- Avoid speculative interfaces, adapter skeletons, configuration, and migrations.
- Keep changes reviewable and independently verifiable.
- Separate mechanical cleanup from behavioral changes unless the cleanup is necessary for the behavior.

### Favor clarity and determinism

- Prefer explicit types, states, inputs, outputs, and errors.
- Keep business decisions in deterministic code when possible.
- Make time, IDs, external responses, and environment behavior controllable in tests.
- Preserve uncertainty and partial failure rather than inventing a successful value.
- Choose readable code over cleverness or premature generalization.
- Add comments for non-obvious constraints and decisions, not for syntax.

### Respect boundaries

- Follow the dependency and placement rules in the architecture documents.
- Validate untrusted input at system boundaries.
- Translate external concepts into project-owned contracts once, near the boundary.
- Do not leak provider, transport, filesystem, or presentation details into core behavior.
- Use factories for construction and adapters for external integration; do not turn either into business-logic containers.

### Preserve user work

- Inspect existing changes before editing overlapping files.
- Treat unrelated modifications as user-owned.
- Avoid destructive Git or filesystem operations.
- Do not rewrite or reformat unrelated files.
- When a conflict cannot be resolved safely, stop and explain the exact overlap.

## Test-Driven Development

Use red-green-refactor for behavioral work.

### Red

1. express the requested behavior as the smallest useful test;
2. run the test and confirm it fails for the expected reason;
3. if it passes unexpectedly, inspect the existing behavior before changing implementation.

### Green

1. implement the smallest change that satisfies the failing test;
2. run the focused test until it passes;
3. run nearby tests that cover the affected boundary.

### Refactor

1. improve naming, duplication, and structure without changing behavior;
2. keep the focused tests green throughout;
3. run the broader relevant suite after refactoring.

TDD expectations:

- Bug fixes begin with a regression test.
- Domain rules and state transitions use unit tests.
- Adapter behavior uses shared contract tests and sanitized fixtures.
- Markdown changes include round-trip and compatibility tests.
- CLI behavior uses isolated command tests.
- End-to-end behavior defaults to fake agents, fixture sources, deterministic clocks/IDs, and temporary workspaces.
- Live provider or agent tests are opt-in and are never the default correctness gate.

Documentation-only changes do not require artificial unit tests, but links, examples, formatting, and internal consistency should be checked.

Do not optimize for coverage percentage alone. Test important behavior, failure modes, invariants, and boundaries directly.

## Planning and Execution

Create a short working plan when a task:

- spans multiple layers or documents;
- changes a persisted contract;
- adds or replaces an external integration;
- changes a state machine or lifecycle;
- requires a migration or compatibility strategy;
- has several independently verifiable steps.

A useful plan names outcomes and verification gates, not vague activities. Keep at most one dependent step in progress and update the plan when evidence changes the approach.

During implementation:

- search with `rg` and list files with `rg --files`;
- inspect before editing;
- use `apply_patch` for source and documentation changes;
- prefer non-interactive, narrowly scoped commands;
- do not use live services when a fixture or local contract test can answer the question;
- report material assumptions and unexpected repository state promptly.

## Context7 and External Documentation

Use Context7 MCP whenever a task depends on current documentation for a library, framework, SDK, API, CLI tool, or cloud service. Use it even for familiar tools because syntax and recommended patterns change.

Do not use Context7 for pure business logic, general programming concepts, refactoring, code review, or scripts with no external-library dependency.

Context7 workflow:

1. call `resolve-library-id` with the exact library name and the full task question unless the user supplied an exact `/org/project` ID;
2. choose the best exact match using description relevance, snippet coverage, source reputation, benchmark score, and requested version;
3. call `query-docs` with the selected library ID and one focused concept per query;
4. implement and explain the result using the fetched documentation;
5. consult additional concepts separately instead of using one broad query.

For finance data providers, read `docs/08-data-source-strategy.md` first and verify unstable access, quota, schema, and terms details against official primary sources when the task requires integration or a decision.

Prefer purpose-built repository, connector, or MCP tools over browser automation. Use web search only when current external information is required and no better primary integration is available.

## Verification Lifecycle

Verification should be proportional to the change, but never omitted without explanation.

Use this progression:

1. focused test for the changed behavior;
2. nearby unit or contract suite;
3. type checking and lint for affected code;
4. broader hermetic test suite;
5. package build and CLI smoke tests when packaging or command behavior changed;
6. documentation link and example checks when docs changed;
7. opt-in live smoke test only when an external adapter itself changed and credentials/terms permit it.

Default verification must not require network access, credentials, a running service, or an installed agent CLI.

When a check cannot run, state:

- the exact command or check omitted;
- why it could not run;
- what narrower evidence was obtained;
- the remaining risk.

## Change Completion

A change is ready to hand off when:

- the requested observable behavior is implemented;
- the new or changed behavior is tested;
- relevant existing tests remain green;
- formatting, lint, and types pass for the affected scope;
- architecture and persistence boundaries remain intact;
- documentation and examples match intentional behavior;
- no unrelated user work was overwritten;
- limitations, deferred work, and external verification gaps are explicit.

The final handoff should lead with the outcome and briefly include:

- important files changed;
- verification performed;
- any known limitation or next dependency.

Do not describe a task as complete when only scaffolding exists, a test was not observed failing for the intended reason, or a required acceptance gate remains unsatisfied.

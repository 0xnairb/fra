# WP2-WP9 Release Traceability

This matrix maps the completion boundaries in the implementation plan to executable or reviewable
evidence. A file's presence is never completion evidence by itself. Hermetic gates run in CI on
Linux, macOS, and Windows; installed-agent and live-source gates are explicit operator checks.

## Current execution record

| Gate | Evidence on 2026-07-19 |
| --- | --- |
| Default hermetic suite | 169 passed, 5 operator tests skipped |
| Format, lint, and types | `ruff format --check`, `ruff check`, and strict `mypy` passed |
| Package and CLI | sdist/wheel build, version/help, and example-config doctor passed |
| Installed structured output | Codex and Claude smokes both passed |
| Same installed-agent WP8 workflow | Codex and Claude fixture-source allocation runs both passed |
| Live WP5 workflow | Unexecuted: `COINGECKO_DEMO_API_KEY` was not available in the environment |
| Hosted cross-platform matrix | Configured for Linux, macOS, and Windows; the forced-color regression suite passes locally, but the current matrix is unexecuted until the release candidate is pushed |
| Clean committed checkout | Passed from a fresh local clone of the committed release candidate |

The README status remains conservative while any required operator or hosted gate is unexecuted.

## Release commands

Hermetic release gate:

```console
uv sync --locked --all-groups
uv run --locked pytest
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv build
uv run --locked fra --version
uv run --locked fra --help
uv run --locked fra doctor
```

Operator gates:

```console
FRA_RUN_LIVE_CODEX=1 FRA_RUN_LIVE_CLAUDE=1 \
  uv run --locked pytest tests/integration/agent_backends/test_codex_local_smoke.py \
  tests/integration/agent_backends/test_claude_local_smoke.py

FRA_RUN_LIVE_WP8=1 \
  uv run --locked pytest \
  tests/integration/test_wp8_allocation_vertical_slice.py::test_wp8_fixture_allocation_completes_through_each_installed_cli

FRA_RUN_LIVE_CRYPTO=1 COINGECKO_DEMO_API_KEY=... \
  uv run --locked pytest tests/integration/test_wp5_live_crypto_smoke.py
```

## WP2: Markdown persistence vertical slice

| Exit requirement | Authoritative proof |
| --- | --- |
| Repository contracts pass for memory and Markdown | `tests/contract/test_markdown_repositories.py` shared parametrized contracts |
| `fra init` is idempotent and preserves content | `tests/unit/test_workspace.py::test_workspace_initialization_is_idempotent_and_preserves_user_content` |
| Interrupted write preserves the previous aggregate | `tests/unit/test_markdown_codec_and_atomic_files.py::test_atomic_writer_preserves_previous_file_when_replace_is_interrupted` |
| Issued signals are immutable and corrections supersede | `tests/contract/test_markdown_repositories.py::test_markdown_signal_versions_are_immutable_contiguous_and_explicitly_superseded` |
| A run reconstructs from workspace files alone | `tests/contract/test_markdown_repositories.py::test_markdown_research_repository_reconstructs_complete_run_from_files` |
| Dashboard reconstructs from Markdown without external calls | `tests/integration/test_wp2_markdown_vertical_slice.py::test_r0_init_restart_dashboard_and_read_commands_are_fully_markdown_backed` |
| Plain-text output is deterministic and details link to Markdown | WP2 vertical slice above plus `tests/unit/test_dashboard_service.py::test_dashboard_snapshot_is_provider_independent_and_has_artifact_references` |
| Unsupported schema versions fail visibly | `tests/contract/test_markdown_repositories.py::test_unsupported_schema_version_fails_visibly` and the codec fixture tests |

## WP3: Source platform and deterministic ingestion

| Exit requirement | Authoritative proof |
| --- | --- |
| Router records every selection and exclusion reason | `tests/unit/test_source_platform.py::test_router_records_selection_and_every_policy_exclusion` |
| Usage, authority, freshness, and point-in-time incompatibilities reject | Source-platform router tests and `tests/unit/test_source_router_execution.py` |
| Unknown rights fail closed without credential leakage | `test_manifest_validation_is_strict_and_fails_closed`, `test_source_factory_registers_coingecko_from_environment_without_exposing_key`, and redaction tests |
| Explicit source checks persist Markdown; dashboard reads do not check | `tests/integration/cli/test_wp3_source_commands.py::test_source_list_describe_check_and_dashboard_use_persisted_status` |
| Default CI uses fixtures; live HTTP is opt-in | `.github/workflows/ci.yml`, provider-fixture integrations, and the full default suite |
| A fixture source requires no workflow change | Shared source contract plus manual/RSS/World Bank provider-fixture integrations |

## WP4: Agent backend and orchestration

| Exit requirement | Authoritative proof |
| --- | --- |
| Orchestrator primarily uses a fake backend | `tests/unit/test_agent_schemas_and_orchestrator.py` |
| Codex contract passes against a fake executable in CI | `tests/contract/agent_backends/test_codex_cli_contract.py` |
| Installed Codex structured-output smoke passes | Operator gate `FRA_RUN_LIVE_CODEX=1`; `test_installed_codex_structured_output_smoke` |
| Timeout and cancellation terminate the process group and preserve resume | Codex/Claude contract timeout tests and `test_process_cancellation_persists_markdown_and_restart_resumes` |
| Structured-output repair is bounded and failure remains visible | `test_invalid_structured_output_gets_exactly_one_repair_attempt_and_stays_visible` |
| Restart resumes from Markdown without hidden conversation state | Parametrized `test_restart_after_every_agent_stage_uses_only_markdown` |

## WP5: Crypto market timing release

| Exit requirement | Authoritative proof |
| --- | --- |
| Complete fixture workflow succeeds with fake agent | `tests/integration/test_wp5_crypto_vertical_slice.py::test_wp5_crypto_workflow_is_reconstructable_from_markdown` |
| Local CoinGecko plus Codex workflow succeeds | Operator gate `FRA_RUN_LIVE_CRYPTO=1`; `test_live_coingecko_and_installed_codex_crypto_workflow` |
| Material conclusions cite evidence or calculations | Crypto vertical slice artifact assertions and deterministic verification service tests |
| Dashboard displays signal and Markdown path | Crypto vertical slice plus WP2 dashboard integration |
| Missing risk inputs produce `NEEDS_USER_INPUT` | Crypto vertical slice and `tests/integration/cli/test_wp5_crypto_commands.py` |
| Stale/quota/malformed failures remain explicit | Crypto quota test, source platform health rejection, and structured-output repair test |
| Every terminal outcome retains inspectable Markdown | Crypto vertical slice, quota limitation artifact, and shared Markdown repository contract |

## WP6: Forecast, outcome, and exposure graph

| Exit requirement | Authoritative proof |
| --- | --- |
| Issued probabilities cannot be edited in place | `tests/integration/cli/test_wp6_forecast_commands.py::test_wp6_forecast_commands_are_append_only_and_dashboard_backed_by_markdown` |
| Future evidence cannot enter a historical forecast | `tests/unit/domain/test_forecasts.py::test_issue_forecast_freezes_probability_and_rejects_look_ahead_evidence` |
| Scores recompute entirely from Markdown | Forecast repository contract plus WP7 frozen-case end-to-end scoring |
| Unresolved and ambiguous outcomes remain visible | `tests/unit/test_dashboard_service.py::test_dashboard_keeps_unresolved_and_ambiguous_forecasts_visible` |
| Monitoring persists explicitly; dashboard does not monitor | WP6 CLI integration and dashboard service tests |
| Exposure edges require evidence, confidence, and invalidation | `tests/unit/domain/test_forecasts.py::test_exposure_edges_require_evidence_confidence_and_invalidation` |

## WP7: Oil and fertilizer crisis slice

| Exit requirement | Authoritative proof |
| --- | --- |
| Official facts and discovery signals remain distinct | Source descriptors/manifests, routing tests, and crisis report assertions |
| Frozen case contains no post-cutoff or disguised revisions | `tests/integration/test_wp7_crisis_historical_slice.py::test_past_crisis_cutoff_rejects_current_non_vintage_source_values` and provider vintage fixtures |
| Report contains causal chain and strongest counter-scenario | `test_frozen_crisis_case_issues_monitors_resolves_and_scores_from_markdown` |
| Business rankings expose evidence coverage and confidence | Frozen crisis case report and exposure-graph assertions |
| Forecast issues, monitors, resolves, and scores end to end | Frozen crisis case end-to-end test |

## WP8: Allocation and agent portability

| Exit requirement | Authoritative proof |
| --- | --- |
| Weights are deterministic and satisfy constraints | `tests/unit/domain/test_portfolio.py::test_allocation_is_deterministic_sums_exactly_and_respects_constraints` |
| Missing suitability blocks a recommendation | `test_wp8_allocation_missing_suitability_stops_before_agent_or_provider` |
| Proposed allocation remains a versioned Markdown signal | `test_wp8_allocation_is_constraint_bound_and_durable_for_each_backend` |
| Same fixture workflow passes through both real adapter classes | Same parametrized test uses `CodexCliAgentAdapter` and `ClaudeCliAgentAdapter` with fake executables |
| Fixture plugin registers and disables through configuration | `tests/unit/test_source_plugins.py::test_enabled_fixture_plugin_registers_and_disabled_plugin_is_not_loaded` |
| Backend changes through configuration only | Agent factory/config tests plus `test_backend_change_starts_a_fresh_session_at_the_durable_checkpoint` |
| Installed-CLI operator acceptance | `FRA_RUN_LIVE_WP8=1` parametrized installed Codex/Claude workflow gate |

## WP9: Regional packs and hardening

WP9 lists deliverables rather than a separate exit-gate block, so each deliverable is traced here.

| Deliverable | Authoritative proof |
| --- | --- |
| US mappings and filing source | SEC provider fixture and `fra regions describe US` |
| OpenDART and South Korean identifiers | `tests/integration/provider_fixtures/test_wp9_opendart.py` and regional CLI integration |
| KRX remains blocked pending approval and terms | `docs/11-operations-and-recovery.md`, regional-pack state, and regional CLI integration |
| Vietnam official-document mapping and completed price decision | `docs/11-operations-and-recovery.md`, `docs/08-data-source-strategy.md`, regional-pack state, and regional CLI integration |
| Provider health/capability in dashboard and doctor | Source CLI/doctor integration and dashboard source-status tests |
| Migration, Markdown export, disposable indexes, and recovery | `test_workspace_export_migrate_and_disposable_index_recover_from_markdown` plus operations guide |
| Security, privacy, packaging, installation, cross-platform review | Redaction/config tests, package build gate, operations guide, and three-OS CI matrix |

## Completion rule

Release status may change to complete only after the hermetic gate passes from a clean committed
checkout and every operator gate required by WP4, WP5, and WP8 has current passing evidence. A
skipped live test is recorded as unexecuted, never as a pass.

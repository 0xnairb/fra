"""Top-level command tree."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Never

import typer

from fra.application.allocation_research import AllocationResearchRequest
from fra.application.container import (
    ResearchWorkflowApplication,
    SourceApplication,
    WorkspaceApplication,
)
from fra.application.crisis_research import CrisisResearchRequest
from fra.application.crypto_market_timing import (
    CryptoResearchRequest,
    CryptoRiskTolerance,
)
from fra.application.dashboard_service import DashboardSnapshot
from fra.application.doctor_service import DoctorService
from fra.cli.exit_codes import ExitCode, exit_code_for
from fra.domain.forecasts import ForecastResolutionValue, ForecastVersion
from fra.domain.ids import EvidenceId, ForecastId, ResearchRunId
from fra.domain.instruments import Currency
from fra.domain.portfolio import RiskTolerance
from fra.domain.research import ResearchMandateType, ResearchRun, ResearchRunState
from fra.domain.shared import FailureKind
from fra.errors import ConfigurationError
from fra.security.redaction import redact
from fra.version import __version__

WorkspaceApplicationFactory = Callable[[Path | None], WorkspaceApplication]
SourceApplicationFactory = Callable[[Path | None], SourceApplication]
ResearchWorkflowApplicationFactory = Callable[[Path | None], ResearchWorkflowApplication]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"fra {__version__}")
        raise typer.Exit


@dataclass(frozen=True, slots=True)
class _CliContext:
    config_path: Path | None


def create_app(
    doctor_service: DoctorService | None = None,
    workspace_application_factory: WorkspaceApplicationFactory | None = None,
    source_application_factory: SourceApplicationFactory | None = None,
    research_workflow_application_factory: ResearchWorkflowApplicationFactory | None = None,
) -> typer.Typer:
    """Create presentation handlers around injected application services."""
    cli = typer.Typer(
        name="fra",
        help="Local-first finance research agents.",
        no_args_is_help=True,
        pretty_exceptions_enable=False,
    )
    sources_cli = typer.Typer(help="Inspect and explicitly check configured evidence sources.")
    research_cli = typer.Typer(help="Run durable evidence-backed research workflows.")
    forecast_cli = typer.Typer(help="Inspect one durable forecast.")
    regions_cli = typer.Typer(help="Inspect audited regional identifier and provider mappings.")
    workspace_cli = typer.Typer(help="Export, migrate, and index a Markdown workspace.")
    cli.add_typer(sources_cli, name="sources")
    cli.add_typer(research_cli, name="research")
    cli.add_typer(forecast_cli, name="forecast")
    cli.add_typer(regions_cli, name="regions")
    cli.add_typer(workspace_cli, name="workspace")

    @cli.callback()
    def root(
        context: typer.Context,
        version: Annotated[
            bool | None,
            typer.Option(
                "--version",
                callback=_version_callback,
                is_eager=True,
                help="Show the installed FRA version and exit.",
            ),
        ] = None,
        config: Annotated[
            Path | None,
            typer.Option(
                "--config",
                dir_okay=False,
                readable=True,
                resolve_path=True,
                help="Read configuration from this TOML file.",
            ),
        ] = None,
    ) -> None:
        """Run FRA commands."""
        context.obj = _CliContext(config_path=config)

    @cli.command()
    def doctor(context: typer.Context) -> None:
        """Validate local configuration without model or network source calls."""
        try:
            if doctor_service is None:
                raise ConfigurationError("Doctor service is not configured")
            report = doctor_service.check(_context(context).config_path)
        except Exception as error:
            _fail(error)
        for check in report.checks:
            marker = "pass" if check.ok else "fail"
            typer.echo(f"[{marker}] {check.name}: {check.detail}")
        passed = sum(check.ok for check in report.checks)
        typer.echo(f"{passed}/{len(report.checks)} checks passed")
        if not report.ok:
            raise typer.Exit(int(ExitCode.EXTERNAL_DEPENDENCY))

    @cli.command("init")
    def init_workspace(context: typer.Context) -> None:
        """Initialize the Markdown workspace without overwriting user content."""
        try:
            application = _application(context, workspace_application_factory)
            result = application.workspace.initialize()
        except Exception as error:
            _fail(error)
        state = "initialized" if result.created else "already initialized"
        typer.echo(f"Workspace {state}: {result.root}")

    @workspace_cli.command("export")
    def export_workspace(context: typer.Context, destination: Path) -> None:
        """Copy only durable Markdown artifacts to a new external directory."""
        try:
            application = _application(context, workspace_application_factory)
            result = application.maintenance.export(destination)
        except Exception as error:
            _fail(error)
        typer.echo(f"Exported {result.copied} Markdown files to {result.destination}")

    @workspace_cli.command("migrate")
    def migrate_workspace(context: typer.Context, destination: Path) -> None:
        """Migrate through parsed front matter into a new workspace copy."""
        try:
            application = _application(context, workspace_application_factory)
            result = application.maintenance.migrate(destination)
        except Exception as error:
            _fail(error)
        typer.echo(
            f"Migrated {result.migrated} of {result.copied} Markdown files to {result.destination}"
        )

    @workspace_cli.command("rebuild-index")
    def rebuild_workspace_index(context: typer.Context) -> None:
        """Rebuild disposable navigation and performance indexes from Markdown."""
        try:
            application = _application(context, workspace_application_factory)
            result = application.maintenance.rebuild_index()
        except Exception as error:
            _fail(error)
        typer.echo(f"Indexed {result.copied} Markdown files at {result.destination}")

    @regions_cli.command("list")
    def list_regions(context: typer.Context) -> None:
        """List regional-pack readiness without making external calls."""
        try:
            application = _application(context, workspace_application_factory)
            items = application.regions.list()
        except Exception as error:
            _fail(error)
        typer.echo("Region | Name | State | Documents | Markets")
        for item in items:
            typer.echo(
                f"{item.code} | {item.name} | {item.state.value} | "
                f"{','.join(item.document_providers) or 'none'} | "
                f"{','.join(item.market_providers) or 'none'}"
            )

    @regions_cli.command("describe")
    def describe_region(context: typer.Context, code: str) -> None:
        """Show identifiers, approved providers, and explicit regional gaps."""
        try:
            application = _application(context, workspace_application_factory)
            item = application.regions.describe(code)
        except Exception as error:
            _fail(error)
        typer.echo(f"Region: {item.code} — {item.name}")
        typer.echo(f"State: {item.state.value}")
        for mapping in item.identifiers:
            typer.echo(f"Identifier: {mapping.name} | {mapping.format} | {mapping.authority}")
        for limitation in item.limitations:
            typer.echo(f"Limitation: {limitation}")

    @cli.command()
    def dashboard(
        context: typer.Context,
        plain_text: Annotated[
            bool, typer.Option("--plain-text", help="Render deterministic text for automation.")
        ] = False,
        watch: Annotated[
            bool, typer.Option("--watch", help="Reload persisted Markdown until interrupted.")
        ] = False,
    ) -> None:
        """Show signals and recent research reconstructed from Markdown."""
        del plain_text  # Text labels are the stable MVP renderer in both modes.
        try:
            application = _application(context, workspace_application_factory)
            while True:
                snapshot = application.dashboard.snapshot(datetime.now(UTC))
                typer.echo(_render_dashboard(snapshot, application.workspace.root))
                if not watch:
                    break
                time.sleep(5)
        except KeyboardInterrupt:
            return
        except Exception as error:
            _fail(error)

    @cli.command()
    def signals(context: typer.Context) -> None:
        """List the latest immutable signal versions."""
        try:
            application = _application(context, workspace_application_factory)
            items = application.signals.list()
        except Exception as error:
            _fail(error)
        typer.echo("Signals")
        for signal in items:
            typer.echo(
                f"{signal.id} v{signal.version:03d} | {signal.status.value} | "
                f"{signal.summary} | signals/{signal.id}/v{signal.version:03d}.md"
            )

    @cli.command()
    def forecasts(context: typer.Context) -> None:
        """List latest immutable forecast versions."""
        try:
            application = _application(context, workspace_application_factory)
            items = application.forecasts.list()
        except Exception as error:
            _fail(error)
        typer.echo("Forecasts")
        for item in items:
            typer.echo(
                f"{item.forecast.id} v{item.version:03d} | {item.probability} | "
                f"{item.status.value} | {item.forecast.question} | "
                f"forecasts/{item.forecast.id}/v{item.version:03d}.md"
            )

    @forecast_cli.command("show")
    def show_forecast(context: typer.Context, forecast_id: str) -> None:
        """Show one latest durable forecast version."""
        try:
            application = _application(context, workspace_application_factory)
            item = application.forecasts.show(ForecastId(forecast_id))
        except Exception as error:
            _fail(error)
        typer.echo(f"Forecast: {item.forecast.id}")
        typer.echo(f"Version: {item.version}")
        typer.echo(f"Question: {item.forecast.question}")
        typer.echo(f"Probability: {item.probability}")
        typer.echo(f"Status: {item.status.value}")
        typer.echo(f"Artifact: forecasts/{item.forecast.id}/v{item.version:03d}.md")

    @cli.command()
    def monitor(
        context: typer.Context,
        forecast_id: str,
        probability: Annotated[
            float,
            typer.Option("--probability", min=0, max=1, help="Updated binary probability."),
        ],
        reason: Annotated[str, typer.Option("--reason", help="Reason for the immutable update.")],
        evidence_id: Annotated[
            list[str] | None,
            typer.Option(
                "--evidence-id",
                help="Use already-persisted evidence instead of collecting a fresh snapshot.",
            ),
        ] = None,
    ) -> None:
        """Collect fresh evidence and append an immutable monitored probability version."""
        try:
            if evidence_id:
                application = _application(context, workspace_application_factory)
                item = application.forecasts.monitor(
                    ForecastId(forecast_id),
                    Decimal(str(probability)),
                    reason,
                    tuple(EvidenceId(value) for value in evidence_id),
                )
            else:
                research_application = _research_application(
                    context, research_workflow_application_factory
                )
                refresh = research_application.forecast_refresh
                if refresh is None:
                    raise ConfigurationError("Forecast refresh workflow is not configured")

                async def execute_refresh() -> ForecastVersion:
                    try:
                        return await refresh.refresh(
                            ForecastId(forecast_id),
                            Decimal(str(probability)),
                            reason=reason,
                        )
                    finally:
                        await research_application.close()

                item = asyncio.run(execute_refresh())
        except Exception as error:
            _fail(error)
        typer.echo(
            f"Forecast {item.forecast.id} updated to v{item.version:03d} | "
            f"probability {item.probability} | "
            f"forecasts/{item.forecast.id}/v{item.version:03d}.md"
        )

    @cli.command()
    def resolve(
        context: typer.Context,
        forecast_id: str,
        value: Annotated[
            ForecastResolutionValue,
            typer.Option("--value", help="Resolved binary or ambiguous value."),
        ],
        resolver: Annotated[
            str,
            typer.Option("--resolver", help="Person or deterministic rule applying resolution."),
        ],
        evidence_id: Annotated[
            list[str],
            typer.Option("--evidence-id", help="Persisted authoritative resolution evidence."),
        ],
        ambiguity_notes: Annotated[
            str | None,
            typer.Option("--ambiguity-notes", help="Required explanation for ambiguous outcomes."),
        ] = None,
    ) -> None:
        """Resolve and deterministically score a forecast from persisted evidence."""
        try:
            application = _application(context, workspace_application_factory)
            result = application.forecasts.resolve(
                ForecastId(forecast_id),
                value,
                resolver,
                tuple(EvidenceId(item) for item in evidence_id),
                ambiguity_notes=ambiguity_notes,
            )
        except Exception as error:
            _fail(error)
        score = "ambiguous" if result.score.brier_score is None else str(result.score.brier_score)
        typer.echo(
            f"Forecast {forecast_id} resolved {result.outcome.value.value} | "
            f"Brier {score} | outcomes/{result.outcome.id}.md"
        )

    @cli.command()
    def runs(context: typer.Context) -> None:
        """List research runs from Markdown front matter."""
        try:
            application = _application(context, workspace_application_factory)
            items = application.runs.list()
        except Exception as error:
            _fail(error)
        typer.echo("Research Runs")
        for item in items:
            artifact = item.artifact.location if item.artifact else "unavailable"
            typer.echo(f"{item.id} | {item.state.value} | {item.question} | {artifact}")

    @cli.command()
    def show(context: typer.Context, run_id: str) -> None:
        """Show one durable research run aggregate."""
        try:
            application = _application(context, workspace_application_factory)
            run = application.runs.show(ResearchRunId(run_id))
        except Exception as error:
            _fail(error)
        artifact = f"runs/{run.created_at.year:04d}/{run.created_at.month:02d}/{run.id}/run.md"
        typer.echo(f"Run: {run.id}")
        typer.echo(f"Question: {run.mandate.question}")
        typer.echo(f"State: {run.state.value}")
        typer.echo(f"Artifact: {artifact}")

    @research_cli.command("run")
    def research_run(
        context: typer.Context,
        question: Annotated[str, typer.Argument(help="Research question to plan and analyze.")],
        workflow: Annotated[
            ResearchMandateType,
            typer.Option("--workflow", help="Select the durable research workflow skeleton."),
        ] = ResearchMandateType.GENERAL_RESEARCH,
    ) -> None:
        """Run the durable plan, collect, analyze, verify, and synthesize skeleton."""
        try:
            application = _research_application(context, research_workflow_application_factory)

            async def execute() -> ResearchRun:
                try:
                    return await application.orchestrator.start(question, workflow)
                finally:
                    await application.close()

            run = asyncio.run(execute())
        except Exception as error:
            _fail(error)
        _show_research_outcome(run)

    @research_cli.command("crypto")
    def research_crypto(
        context: typer.Context,
        horizon_days: Annotated[
            int | None,
            typer.Option("--horizon-days", min=1, help="Investment horizon in days."),
        ] = None,
        risk_tolerance: Annotated[
            CryptoRiskTolerance | None,
            typer.Option("--risk-tolerance", help="Declared loss/risk tolerance."),
        ] = None,
        currency: Annotated[
            str,
            typer.Option("--currency", help="Three-letter quote currency."),
        ] = "USD",
        lookback_days: Annotated[
            int,
            typer.Option(
                "--lookback-days",
                min=30,
                max=365,
                help="Bounded history window used for deterministic analytics.",
            ),
        ] = 365,
    ) -> None:
        """Assess the bounded BTC/ETH market regime and persist a signal."""
        try:
            application = _research_application(context, research_workflow_application_factory)
            crypto = application.crypto
            if crypto is None:
                raise ConfigurationError("Crypto research workflow is not configured")

            async def execute() -> ResearchRun:
                try:
                    return await crypto.start(
                        CryptoResearchRequest(
                            horizon_days=horizon_days,
                            risk_tolerance=risk_tolerance,
                            currency=Currency(currency),
                            lookback_days=lookback_days,
                        )
                    )
                finally:
                    await application.close()

            run = asyncio.run(execute())
        except Exception as error:
            _fail(error)
        _show_research_outcome(run)

    @research_cli.command("crisis")
    def research_crisis(
        context: typer.Context,
        knowledge_cutoff: Annotated[
            str | None,
            typer.Option(
                "--knowledge-cutoff",
                help="Frozen UTC cutoff as YYYY-MM-DD or an ISO-8601 timestamp.",
            ),
        ] = None,
        horizon_days: Annotated[
            int | None,
            typer.Option("--horizon-days", min=1, help="Binary forecast horizon in days."),
        ] = None,
        company_cik: Annotated[
            str,
            typer.Option("--company-cik", help="SEC CIK used for the selected filing facts."),
        ] = "1657853",
    ) -> None:
        """Research oil/fertilizer transmission and persist a forecast and risk graph."""
        try:
            application = _research_application(context, research_workflow_application_factory)
            crisis = application.crisis
            if crisis is None:
                raise ConfigurationError("Crisis research workflow is not configured")
            cutoff = _utc_datetime(knowledge_cutoff) if knowledge_cutoff is not None else None

            async def execute() -> ResearchRun:
                try:
                    return await crisis.start(
                        CrisisResearchRequest(cutoff, horizon_days, company_cik)
                    )
                finally:
                    await application.close()

            run = asyncio.run(execute())
        except Exception as error:
            _fail(error)
        _show_research_outcome(run)

    @research_cli.command("allocation")
    def research_allocation(
        context: typer.Context,
        horizon_years: Annotated[
            int | None,
            typer.Option("--horizon-years", min=1, help="Confirmed investment horizon."),
        ] = None,
        risk_tolerance: Annotated[
            RiskTolerance | None,
            typer.Option("--risk-tolerance", help="Confirmed risk tolerance."),
        ] = None,
        maximum_loss: Annotated[
            float | None,
            typer.Option("--maximum-loss", min=0, max=1, help="Maximum stress loss."),
        ] = None,
        liquidity_need: Annotated[
            float | None,
            typer.Option("--liquidity-need", min=0, max=1, help="Required liquid share."),
        ] = None,
        tax_jurisdiction: Annotated[
            str | None,
            typer.Option("--tax-jurisdiction", help="Confirmed tax jurisdiction code."),
        ] = None,
        investment_objective: Annotated[
            str | None,
            typer.Option("--investment-objective", help="Confirmed investment objective."),
        ] = None,
        risk_capacity: Annotated[
            RiskTolerance | None,
            typer.Option("--risk-capacity", help="Confirmed financial risk capacity."),
        ] = None,
        maximum_asset_weight: Annotated[
            float,
            typer.Option("--maximum-asset-weight", min=0.01, max=1),
        ] = 0.5,
        minimum_cash_weight: Annotated[
            float,
            typer.Option("--minimum-cash-weight", min=0, max=1),
        ] = 0.1,
    ) -> None:
        """Create a suitability-aware, constraint-bound research allocation."""
        try:
            application = _research_application(context, research_workflow_application_factory)
            allocation = application.allocation
            if allocation is None:
                raise ConfigurationError("Allocation research workflow is not configured")

            async def execute() -> ResearchRun:
                try:
                    return await allocation.start(
                        AllocationResearchRequest(
                            horizon_years=horizon_years,
                            risk_tolerance=risk_tolerance,
                            maximum_loss=(
                                Decimal(str(maximum_loss)) if maximum_loss is not None else None
                            ),
                            liquidity_need=(
                                Decimal(str(liquidity_need)) if liquidity_need is not None else None
                            ),
                            tax_jurisdiction=tax_jurisdiction,
                            investment_objective=investment_objective,
                            risk_capacity=risk_capacity,
                            maximum_asset_weight=Decimal(str(maximum_asset_weight)),
                            minimum_cash_weight=Decimal(str(minimum_cash_weight)),
                        )
                    )
                finally:
                    await application.close()

            run = asyncio.run(execute())
        except Exception as error:
            _fail(error)
        _show_research_outcome(run)

    @cli.command()
    def resume(context: typer.Context, run_id: str) -> None:
        """Resume from the next stage not checkpointed in Markdown."""
        try:
            application = _research_application(context, research_workflow_application_factory)
            before = application.research_repository.get(ResearchRunId(run_id))

            async def execute() -> ResearchRun:
                try:
                    return await application.orchestrator.resume(ResearchRunId(run_id))
                finally:
                    await application.close()

            run = asyncio.run(execute())
        except Exception as error:
            _fail(error)
        if before.state is ResearchRunState.COMPLETED:
            typer.echo(f"Run {run.id} already completed")
        _show_research_outcome(run)

    @sources_cli.command("list")
    def list_sources(context: typer.Context) -> None:
        """List enabled sources from validated manifests without live calls."""
        try:
            application = _source_application(context, source_application_factory)

            async def run() -> None:
                try:
                    typer.echo(
                        "Provider | Roles | Authority | Health | Freshness | Quota/limit warning"
                    )
                    for item in application.sources.list():
                        typer.echo(
                            f"{item.provider_id} | "
                            f"{','.join(role.value for role in item.roles)} | "
                            f"{item.authority} | {item.health} | {item.freshness} | "
                            f"{item.quota_warning or 'none'}"
                        )
                finally:
                    await application.close()

            asyncio.run(run())
        except Exception as error:
            _fail(error)

    @sources_cli.command("describe")
    def describe_source(context: typer.Context, provider: str) -> None:
        """Describe one validated source manifest without a live call."""
        try:
            application = _source_application(context, source_application_factory)

            async def run() -> None:
                try:
                    item = application.sources.describe(provider)
                    typer.echo(f"Provider: {item.provider_id}")
                    typer.echo(f"Adapter version: {item.adapter_version}")
                    typer.echo(f"Roles: {', '.join(role.value for role in item.roles)}")
                    typer.echo(f"Kinds: {', '.join(item.source_kinds)}")
                    typer.echo(f"Authority: {item.authority}")
                    typer.echo(f"Point in time: {str(item.point_in_time_support).lower()}")
                    typer.echo(f"Usage profiles: {', '.join(item.allowed_usage_profiles)}")
                    typer.echo(f"Raw retention: {item.raw_retention}")
                    typer.echo(f"Terms: {item.terms_url} (reviewed {item.terms_reviewed_at})")
                    typer.echo(f"Attribution: {item.required_attribution or 'none'}")
                finally:
                    await application.close()

            asyncio.run(run())
        except Exception as error:
            _fail(error)

    @sources_cli.command("check")
    def check_sources(
        context: typer.Context,
        provider: Annotated[str | None, typer.Argument(help="Provider ID to check.")] = None,
    ) -> None:
        """Make an explicit health call and persist its Markdown result."""
        try:
            application = _source_application(context, source_application_factory)

            async def run() -> bool:
                try:
                    records = await application.sources.check(provider)
                    for item in records:
                        typer.echo(
                            f"{item.provider_id} | {item.health.state.value} | "
                            f"{item.health.summary} | source-status/{item.provider_id}.md"
                        )
                    return all(item.health.ok for item in records)
                finally:
                    await application.close()

            ok = asyncio.run(run())
        except Exception as error:
            _fail(error)
        if not ok:
            raise typer.Exit(int(ExitCode.EXTERNAL_DEPENDENCY))

    return cli


def _context(context: typer.Context) -> _CliContext:
    return context.ensure_object(_CliContext)


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _application(
    context: typer.Context, factory: WorkspaceApplicationFactory | None
) -> WorkspaceApplication:
    if factory is None:
        raise ConfigurationError("Workspace application is not configured")
    return factory(_context(context).config_path)


def _source_application(
    context: typer.Context, factory: SourceApplicationFactory | None
) -> SourceApplication:
    if factory is None:
        raise ConfigurationError("Source application is not configured")
    return factory(_context(context).config_path)


def _research_application(
    context: typer.Context, factory: ResearchWorkflowApplicationFactory | None
) -> ResearchWorkflowApplication:
    if factory is None:
        raise ConfigurationError("Research workflow application is not configured")
    return factory(_context(context).config_path)


def _show_research_outcome(run: ResearchRun) -> None:
    artifact = f"runs/{run.created_at.year:04d}/{run.created_at.month:02d}/{run.id}/run.md"
    typer.echo(f"Run: {run.id}")
    typer.echo(f"State: {run.state.value}")
    typer.echo(f"Artifact: {artifact}")
    if run.state is ResearchRunState.COMPLETED:
        return
    if run.failure is not None:
        typer.echo(f"Limitation: {redact(run.failure.message)}")
    if run.state is ResearchRunState.NEEDS_USER_INPUT:
        raise typer.Exit(int(ExitCode.USER_INPUT_REQUIRED))
    external_failures = {
        FailureKind.ADAPTER_UNAVAILABLE,
        FailureKind.AUTHENTICATION_REQUIRED,
        FailureKind.CAPABILITY_UNSUPPORTED,
        FailureKind.CAPABILITY_UNAVAILABLE,
        FailureKind.RATE_LIMITED,
        FailureKind.QUOTA_EXCEEDED,
        FailureKind.EXTERNAL_DATA_INVALID,
        FailureKind.USAGE_POLICY_VIOLATION,
    }
    if run.failure is not None and run.failure.kind in external_failures:
        raise typer.Exit(int(ExitCode.EXTERNAL_DEPENDENCY))
    raise typer.Exit(int(ExitCode.INCOMPLETE))


def _fail(error: Exception) -> Never:
    code = exit_code_for(error)
    message = str(error) if code is not ExitCode.INTERNAL_ERROR else "Unexpected internal error"
    typer.echo(f"Error: {redact(message)}", err=True)
    raise typer.Exit(int(code)) from error


def _render_dashboard(snapshot: DashboardSnapshot, workspace: Path) -> str:
    lines = [
        f"FRA Dashboard | {workspace} | {snapshot.generated_at.isoformat().replace('+00:00', 'Z')}",
        "",
        "Signals",
        "Subject | Stance | Strength | Confidence | Horizon | Freshness | Status | Artifact",
    ]
    lines.extend(
        f"{item.subject} | {item.stance.value} | {item.strength.value} | "
        f"{item.confidence.value} | {item.horizon} | {item.freshness} | "
        f"{item.status.value} | {item.artifact.location}"
        for item in snapshot.signals
    )
    lines.extend(
        [
            "",
            "Forecasts",
            "Question | Probability | Horizon | Updated | State | Score | Artifact",
        ]
    )
    lines.extend(
        f"{item.question} | {item.probability} | "
        f"{item.horizon_end.isoformat().replace('+00:00', 'Z')} | "
        f"{item.updated_at.isoformat().replace('+00:00', 'Z')} | {item.state} | "
        f"{item.score} | {item.artifact.location}"
        for item in snapshot.forecasts
    )
    lines.extend(
        [
            "",
            "Risk Watch",
            "Event | Transmission path | Exposed subjects | Severity | Next check | Artifact",
        ]
    )
    lines.extend(
        f"{item.event} | {item.transmission_path} | {item.exposed_subjects} | "
        f"{item.severity} | {item.next_check} | {item.artifact.location}"
        for item in snapshot.risks
    )
    lines.extend(
        [
            "",
            "Sources",
            "Provider | Role | Freshness | Health | Capabilities | Quota/limit warning | Artifact",
        ]
    )
    lines.extend(
        f"{item.provider_id} | {item.role} | {item.freshness} | {item.health} | "
        f"{item.capability_summary} | "
        f"{item.quota_warning} | {item.artifact.location}"
        for item in snapshot.sources
    )
    lines.extend(["", "Recent Research", "Run | Mandate | State | Updated | Artifact"])
    lines.extend(
        f"{item.run_id} | {item.question} | {item.state} | "
        f"{item.updated_at.isoformat().replace('+00:00', 'Z')} | {item.artifact.location}"
        for item in snapshot.recent_runs
    )
    return "\n".join(lines)


app = create_app()


def main() -> None:
    """Run the CLI command tree."""
    app()

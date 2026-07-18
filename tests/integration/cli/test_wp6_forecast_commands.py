from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

from typer.testing import CliRunner

from fra.adapters.storage.markdown_exposure_graphs import MarkdownExposureGraphRepository
from fra.adapters.storage.markdown_forecasts import MarkdownForecastRepository
from fra.adapters.storage.markdown_research import MarkdownResearchRepository
from fra.adapters.storage.workspace import Workspace
from fra.bootstrap import build_cli
from fra.cli.exit_codes import ExitCode
from fra.domain.forecasts import (
    ExposureEdge,
    ExposureGraph,
    ExposureNode,
    ExposureNodeKind,
    Forecast,
    ForecastStatus,
    ForecastTrigger,
    ForecastVersion,
    InvalidationCondition,
    ResolutionRule,
)
from fra.domain.ids import (
    EvidenceId,
    ExposureGraphId,
    ForecastId,
    InstrumentId,
    MandateId,
    ResearchRunId,
)
from fra.domain.instruments import Currency
from fra.domain.market_data import MarketQuote
from fra.domain.research import Evidence, ResearchMandate, ResearchMandateType, ResearchRun
from fra.domain.sources import (
    AuthorityClass,
    DataEnvelope,
    DataKind,
    RawRetentionPolicy,
    SourceDescriptor,
    SourceKind,
    UsageProfile,
)

runner = CliRunner()


def test_wp6_forecast_commands_are_append_only_and_dashboard_backed_by_markdown(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    research = MarkdownResearchRepository(workspace)
    forecasts = MarkdownForecastRepository(workspace)
    run = _run(now)
    research.create(run)
    evidence = _evidence(run.id, now)
    research.add_evidence(run.id, cast(Evidence[object], evidence))
    active = _forecast(
        ForecastId("forecast_active"),
        run.id,
        now - timedelta(days=1),
        now + timedelta(days=30),
        Decimal("0.35"),
    )
    resolvable = _forecast(
        ForecastId("forecast_resolvable"),
        run.id,
        now - timedelta(days=10),
        now - timedelta(days=1),
        Decimal("0.40"),
    )
    forecasts.save(active)
    forecasts.save(resolvable)
    MarkdownExposureGraphRepository(workspace).save(_graph(now))
    config = tmp_path / "fra.toml"
    config.write_text(f'[workspace]\nroot = "{workspace.root}"\n')

    listed = runner.invoke(build_cli(), ["--config", str(config), "forecasts"])
    shown = runner.invoke(
        build_cli(),
        ["--config", str(config), "forecast", "show", "forecast_active"],
    )
    monitored = runner.invoke(
        build_cli(),
        [
            "--config",
            str(config),
            "monitor",
            "forecast_active",
            "--probability",
            "0.55",
            "--reason",
            "New official observation",
            "--evidence-id",
            str(evidence.id),
        ],
    )
    resolved = runner.invoke(
        build_cli(),
        [
            "--config",
            str(config),
            "resolve",
            "forecast_resolvable",
            "--value",
            "true",
            "--resolver",
            "fixture-rule",
            "--evidence-id",
            str(evidence.id),
        ],
    )
    dashboard = runner.invoke(build_cli(), ["--config", str(config), "dashboard", "--plain-text"])

    assert listed.exit_code == ExitCode.SUCCESS
    assert "forecast_active" in listed.output
    assert shown.exit_code == ExitCode.SUCCESS
    assert "Probability: 0.35" in shown.output
    assert monitored.exit_code == ExitCode.SUCCESS, monitored.output
    assert "v002" in monitored.output
    assert forecasts.get(active.forecast.id, 1).probability == Decimal("0.35")
    assert forecasts.get(active.forecast.id, 2).probability == Decimal("0.55")
    assert resolved.exit_code == ExitCode.SUCCESS, resolved.output
    assert "Brier 0.36" in resolved.output
    assert dashboard.exit_code == ExitCode.SUCCESS
    assert "forecasts/forecast_active/v002.md" in dashboard.output
    assert "resolved | 0.36" in dashboard.output
    assert "exposure-graphs/graph_fixture/v001.md" in dashboard.output


def _run(now: datetime) -> ResearchRun:
    created_at = now - timedelta(days=10)
    mandate = ResearchMandate(
        MandateId("mandate_fixture"),
        ResearchMandateType.GENERAL_RESEARCH,
        "Fixture forecast research",
        created_at,
    )
    return ResearchRun.create(ResearchRunId("run_fixture"), mandate, created_at)


def _evidence(run_id: ResearchRunId, now: datetime) -> Evidence[MarketQuote]:
    available_at = now - timedelta(days=10)
    descriptor = SourceDescriptor(
        provider_id="fixture-official",
        adapter_version="1",
        source_kinds=frozenset({SourceKind.MARKET_DATA}),
        authority_class=AuthorityClass.OFFICIAL,
        point_in_time_support=True,
        allowed_usage_profiles=frozenset({UsageProfile.LOCAL_PERSONAL_RESEARCH}),
        raw_retention=RawRetentionPolicy.PERMITTED,
        terms_url="https://fixture.test/terms",
        terms_reviewed_at=now.date(),
        independence_group="fixture",
    )
    envelope = DataEnvelope(
        value=MarketQuote(
            InstrumentId("fixture:asset"), Decimal("100"), Currency("USD"), available_at
        ),
        descriptor=descriptor,
        provider_record_id="record-1",
        source="https://fixture.test/evidence",
        available_at=available_at,
        retrieved_at=available_at,
    )
    return Evidence(
        EvidenceId("evidence_fixture"),
        run_id,
        DataKind.MARKET_QUOTE,
        "Fixture official outcome evidence",
        envelope,
        available_at,
        available_at,
    )


def _forecast(
    forecast_id: ForecastId,
    run_id: ResearchRunId,
    issued_at: datetime,
    horizon_end: datetime,
    probability: Decimal,
) -> ForecastVersion:
    forecast = Forecast(
        forecast_id,
        run_id,
        "Will the fixture event occur?",
        "The event occurs before the horizon.",
        ForecastTrigger("Official indicator crosses the threshold"),
        ResolutionRule(1, "Use the official outcome.", "fixture-official"),
        issued_at,
    )
    return ForecastVersion(
        forecast,
        1,
        probability,
        issued_at,
        issued_at,
        horizon_end,
        (EvidenceId("evidence_fixture"),),
        (InvalidationCondition("Official indicator reverses"),),
        "indicator -> event",
        ("The event does not occur",),
        ForecastStatus.ACTIVE,
    )


def _graph(now: datetime) -> ExposureGraph:
    return ExposureGraph(
        ExposureGraphId("graph_fixture"),
        1,
        "Fixture risk watch",
        (
            ExposureNode("event:fixture", ExposureNodeKind.EVENT, "Fixture event"),
            ExposureNode("industry:fixture", ExposureNodeKind.INDUSTRY, "Fixture industry"),
        ),
        (
            ExposureEdge(
                "event:fixture",
                "industry:fixture",
                "affects",
                "negative",
                "weeks",
                Decimal("0.8"),
                "GLOBAL",
                (EvidenceId("evidence_fixture"),),
                "Observed impact does not materialize",
            ),
        ),
        now,
    )

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from fra.bootstrap import build_cli, build_markdown_application
from fra.cli.exit_codes import ExitCode
from fra.domain.ids import EvidenceId, MandateId, ResearchRunId, SignalId
from fra.domain.research import ResearchMandate, ResearchMandateType, ResearchRun
from fra.domain.signals import Confidence, Signal, SignalStance, SignalStatus, SignalStrength

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)
runner = CliRunner()
FIXTURE = Path(__file__).parents[1] / "fixtures" / "agent_backends" / "fake_codex.py"


def write_config(tmp_path: Path) -> Path:
    config = tmp_path / "fra.toml"
    config.write_text(
        f'[workspace]\nroot = "{(tmp_path / "workspace").as_posix()}"\n\n'
        f'[agent.options]\nbinary = "{FIXTURE.as_posix()}"\n'
    )
    return config


def seed(config: Path) -> None:
    application = build_markdown_application(config)
    mandate = ResearchMandate(
        id=MandateId("mandate_0001"),
        kind=ResearchMandateType.GENERAL_RESEARCH,
        question="What changed?",
        created_at=NOW,
    )
    run = ResearchRun.create(ResearchRunId("run_0001"), mandate, NOW)
    application.research_repository.create(run)
    application.signal_repository.save(
        Signal(
            id=SignalId("signal_0001"),
            version=1,
            run_id=run.id,
            subject_ids=("crypto:bitcoin",),
            summary="Fixture observation",
            stance=SignalStance.NEUTRAL,
            strength=SignalStrength.MODERATE,
            confidence=Confidence.MEDIUM,
            horizon="3 months",
            issued_at=NOW,
            knowledge_cutoff_at=NOW,
            evidence_ids=(EvidenceId("evidence_0001"),),
            invalidation_conditions=("Fixture changes",),
            status=SignalStatus.ACTIVE,
        )
    )


def test_r0_init_restart_dashboard_and_read_commands_are_fully_markdown_backed(
    tmp_path: Path,
) -> None:
    config = write_config(tmp_path)
    first = runner.invoke(build_cli(), ["--config", str(config), "init"])
    second = runner.invoke(build_cli(), ["--config", str(config), "init"])
    assert first.exit_code == ExitCode.SUCCESS
    assert second.exit_code == ExitCode.SUCCESS
    assert "initialized" in first.output
    assert "already initialized" in second.output

    seed(config)

    # A new CLI object proves the projection is reconstructed after process-local state is gone.
    dashboard = runner.invoke(build_cli(), ["--config", str(config), "dashboard", "--plain-text"])
    signals = runner.invoke(build_cli(), ["--config", str(config), "signals"])
    runs = runner.invoke(build_cli(), ["--config", str(config), "runs"])
    shown = runner.invoke(build_cli(), ["--config", str(config), "show", "run_0001"])

    for result in (dashboard, signals, runs, shown):
        assert result.exit_code == ExitCode.SUCCESS, result.output
    assert "signals/signal_0001/v001.md" in dashboard.output
    assert "runs/2026/07/run_0001/run.md" in dashboard.output
    assert "signal_0001" in signals.output
    assert "run_0001" in runs.output
    assert "What changed?" in shown.output


def test_wp2_doctor_probes_initialized_workspace_and_atomic_writes(tmp_path: Path) -> None:
    config = write_config(tmp_path)
    runner.invoke(build_cli(), ["--config", str(config), "init"])

    result = runner.invoke(build_cli(), ["--config", str(config), "doctor"])

    assert result.exit_code == ExitCode.SUCCESS
    assert "Workspace" in result.output
    assert "Markdown atomic write" in result.output
    assert "10/10 checks passed" in result.output


def test_read_commands_use_stable_missing_and_corruption_exit_codes(tmp_path: Path) -> None:
    config = write_config(tmp_path)
    runner.invoke(build_cli(), ["--config", str(config), "init"])

    missing = runner.invoke(build_cli(), ["--config", str(config), "show", "run_missing"])
    assert missing.exit_code == ExitCode.USER_INPUT_REQUIRED

    seed(config)
    run_file = tmp_path / "workspace" / "runs" / "2026" / "07" / "run_0001" / "run.md"
    run_file.write_text(run_file.read_text().replace("schema_version: 1", "schema_version: 99", 1))
    corrupt = runner.invoke(build_cli(), ["--config", str(config), "dashboard", "--plain-text"])
    assert corrupt.exit_code == ExitCode.CORRUPTION
    assert "unsupported" in corrupt.output

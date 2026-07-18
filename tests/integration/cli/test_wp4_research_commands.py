from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fra.bootstrap import build_cli
from fra.cli.exit_codes import ExitCode

FIXTURE = Path(__file__).parents[2] / "fixtures" / "agent_backends" / "fake_codex.py"
runner = CliRunner()


def _config(tmp_path: Path) -> Path:
    config = tmp_path / "fra.toml"
    config.write_text(
        f'''[workspace]
root = "{tmp_path / "workspace"}"

[agent]
provider = "codex_cli"
timeout_seconds = 1

[agent.options]
binary = "{FIXTURE}"
sandbox = "read-only"
'''
    )
    return config


def test_general_research_without_an_evidence_workflow_fails_durably(tmp_path: Path) -> None:
    config = _config(tmp_path)
    initialized = runner.invoke(build_cli(), ["--config", str(config), "init"])
    researched = runner.invoke(
        build_cli(), ["--config", str(config), "research", "run", "What changed?"]
    )

    assert initialized.exit_code == ExitCode.SUCCESS
    assert researched.exit_code == ExitCode.EXTERNAL_DEPENDENCY, researched.output
    assert "State: failed" in researched.output
    assert "no evidence workflow is registered" in researched.output
    run_id = next(part for part in researched.output.split() if part.startswith("run_"))
    resumed = runner.invoke(build_cli(), ["--config", str(config), "resume", run_id])
    shown = runner.invoke(build_cli(), ["--config", str(config), "show", run_id])

    assert resumed.exit_code == ExitCode.EXTERNAL_DEPENDENCY
    assert "State: failed" in shown.output
    run_files = tuple((tmp_path / "workspace" / "runs").glob(f"*/*/{run_id}/run.md"))
    assert len(run_files) == 1
    run_text = run_files[0].read_text(encoding="utf-8")
    assert "fra.codex_cli.v1" in run_text
    assert (run_files[0].parent / "plan.md").is_file()
    assert (run_files[0].parent / "limitation.md").is_file()
    assert not (run_files[0].parent / "report.md").exists()


def test_timeout_resume_reaches_the_next_honest_missing_evidence_boundary(
    tmp_path: Path, monkeypatch: object
) -> None:
    config = _config(tmp_path)
    monkeypatch.setenv("FAKE_CODEX_MODE", "timeout")  # type: ignore[attr-defined]
    runner.invoke(build_cli(), ["--config", str(config), "init"])
    timed_out = runner.invoke(
        build_cli(), ["--config", str(config), "research", "run", "What changed?"]
    )

    assert timed_out.exit_code == ExitCode.INCOMPLETE
    assert "State: failed" in timed_out.output
    run_id = next(part for part in timed_out.output.split() if part.startswith("run_"))
    monkeypatch.setenv("FAKE_CODEX_MODE", "success")  # type: ignore[attr-defined]
    resumed = runner.invoke(build_cli(), ["--config", str(config), "resume", run_id])

    assert resumed.exit_code == ExitCode.EXTERNAL_DEPENDENCY, resumed.output
    assert "no evidence workflow is registered" in resumed.output


def test_doctor_checks_codex_binary_capability_and_auth_without_research(tmp_path: Path) -> None:
    config = _config(tmp_path)

    result = runner.invoke(build_cli(), ["--config", str(config), "doctor"])

    assert result.exit_code == ExitCode.SUCCESS, result.output
    assert "Agent binary" in result.output
    assert "Agent capabilities" in result.output
    assert "Agent authentication" in result.output
    assert "10/10 checks passed" in result.output


def test_doctor_reports_a_missing_configured_codex_profile(
    tmp_path: Path, monkeypatch: object
) -> None:
    config = _config(tmp_path)
    config.write_text(config.read_text().replace('sandbox = "read-only"', 'profile = "fra"'))
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))  # type: ignore[attr-defined]

    result = runner.invoke(build_cli(), ["--config", str(config), "doctor"])

    assert result.exit_code == ExitCode.EXTERNAL_DEPENDENCY
    assert "profile 'fra' is not configured" in result.output
    assert "fra.config.toml" in result.output

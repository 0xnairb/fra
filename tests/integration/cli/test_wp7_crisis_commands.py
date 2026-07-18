from pathlib import Path

from typer.testing import CliRunner

from fra.bootstrap import build_cli
from fra.cli.exit_codes import ExitCode

FIXTURE = Path(__file__).parents[2] / "fixtures" / "agent_backends" / "fake_codex.py"
runner = CliRunner()


def test_crisis_command_requires_cutoff_and_horizon_and_persists_blocked_run(
    tmp_path: Path,
) -> None:
    config = tmp_path / "fra.toml"
    workspace = tmp_path / "workspace"
    config.write_text(
        f'''[workspace]
root = "{workspace}"

[agent]
provider = "codex_cli"

[agent.options]
binary = "{FIXTURE}"
sandbox = "read-only"
'''
    )
    runner.invoke(build_cli(), ["--config", str(config), "init"])

    result = runner.invoke(build_cli(), ["--config", str(config), "research", "crisis"])

    assert result.exit_code == ExitCode.USER_INPUT_REQUIRED
    assert "State: needs_user_input" in result.output
    assert "knowledge cutoff" in result.output
    assert "forecast horizon" in result.output
    run_id = next(part for part in result.output.split() if part.startswith("run_"))
    assert len(tuple(workspace.glob(f"runs/*/*/{run_id}/run.md"))) == 1
    assert len(tuple(workspace.glob(f"runs/*/*/{run_id}/limitation.md"))) == 1


def test_crisis_command_exposes_frozen_case_inputs() -> None:
    result = runner.invoke(
        build_cli(),
        ["research", "crisis", "--help"],
        env={"FORCE_COLOR": None, "NO_COLOR": "1"},
    )

    assert result.exit_code == ExitCode.SUCCESS
    assert "--knowledge-cutoff" in result.output
    assert "--horizon-days" in result.output
    assert "--company-cik" in result.output

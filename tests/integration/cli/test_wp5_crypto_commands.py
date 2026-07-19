from pathlib import Path

from rich.text import Text
from typer.testing import CliRunner

from fra.bootstrap import build_cli
from fra.cli.exit_codes import ExitCode

FIXTURE = Path(__file__).parents[2] / "fixtures" / "agent_backends" / "fake_codex.py"
runner = CliRunner()


def test_crypto_command_requires_risk_inputs_and_persists_the_blocked_run(
    tmp_path: Path,
) -> None:
    config = tmp_path / "fra.toml"
    workspace = tmp_path / "workspace"
    config.write_text(
        f'''[workspace]
root = "{workspace.as_posix()}"

[agent]
provider = "codex_cli"

[agent.options]
binary = "{FIXTURE.as_posix()}"
sandbox = "read-only"
'''
    )
    runner.invoke(build_cli(), ["--config", str(config), "init"])

    result = runner.invoke(build_cli(), ["--config", str(config), "research", "crypto"])

    assert result.exit_code == ExitCode.USER_INPUT_REQUIRED
    assert "State: needs_user_input" in result.output
    assert "investment horizon" in result.output
    assert "risk tolerance" in result.output
    run_id = next(part for part in result.output.split() if part.startswith("run_"))
    assert len(tuple(workspace.glob(f"runs/*/*/{run_id}/run.md"))) == 1
    assert len(tuple(workspace.glob(f"runs/*/*/{run_id}/limitation.md"))) == 1


def test_crypto_command_exposes_bounded_typed_options() -> None:
    result = runner.invoke(build_cli(), ["research", "crypto", "--help"])
    output = Text.from_ansi(result.output).plain

    assert result.exit_code == ExitCode.SUCCESS
    assert "--horizon-days" in output
    assert "--risk-tolerance" in output
    assert "--lookback-days" in output

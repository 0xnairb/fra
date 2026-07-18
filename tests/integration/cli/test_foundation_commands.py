from pathlib import Path

import pytest
from typer.testing import CliRunner

from fra.bootstrap import build_cli
from fra.cli.exit_codes import ExitCode

runner = CliRunner()


def test_help_lists_foundation_commands() -> None:
    result = runner.invoke(build_cli(), ["--help"])

    assert result.exit_code == ExitCode.SUCCESS
    assert "--version" in result.output
    assert "doctor" in result.output


def test_doctor_passes_without_configuration_or_external_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(build_cli(), ["doctor"])

    assert result.exit_code == ExitCode.SUCCESS
    assert "Python runtime" in result.output
    assert "Configuration" in result.output
    assert "2/2 checks passed" in result.output


def test_doctor_rejects_inline_secret_without_echoing_it(tmp_path: Path) -> None:
    secret = "cli-must-never-print-this"
    config = tmp_path / "fra.toml"
    config.write_text(f'[data_sources.coingecko.options]\napi_key = "{secret}"\n')

    result = runner.invoke(build_cli(), ["--config", str(config), "doctor"])

    assert result.exit_code == ExitCode.CONFIGURATION
    assert "inline secret" in result.output.lower()
    assert secret not in result.output

"""Opt-in local CoinGecko plus installed-Codex release smoke test."""

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fra.bootstrap import build_cli
from fra.cli.exit_codes import ExitCode


@pytest.mark.skipif(
    os.environ.get("FRA_RUN_LIVE_CRYPTO") != "1" or not os.environ.get("COINGECKO_DEMO_API_KEY"),
    reason="set FRA_RUN_LIVE_CRYPTO=1 and COINGECKO_DEMO_API_KEY for the live smoke",
)
def test_live_coingecko_and_installed_codex_crypto_workflow(tmp_path: Path) -> None:
    config = tmp_path / "fra.toml"
    config.write_text(
        f'''[workspace]
root = "{tmp_path / "workspace"}"
usage_profile = "local_personal_research"

[agent]
provider = "codex_cli"
timeout_seconds = 900

[agent.options]
binary = "codex"
sandbox = "read-only"

[data_sources.coingecko]
enabled = true
roles = ["primary"]
allowed_usage_profiles = ["local_personal_research"]

[data_sources.coingecko.options]
base_url = "https://api.coingecko.com/api/v3"
api_key_env = "COINGECKO_DEMO_API_KEY"
'''
    )
    runner = CliRunner()
    initialized = runner.invoke(build_cli(), ["--config", str(config), "init"])
    result = runner.invoke(
        build_cli(),
        [
            "--config",
            str(config),
            "research",
            "crypto",
            "--horizon-days",
            "365",
            "--risk-tolerance",
            "medium",
            "--lookback-days",
            "30",
        ],
    )

    assert initialized.exit_code == ExitCode.SUCCESS
    assert result.exit_code == ExitCode.SUCCESS, result.output
    assert "State: completed" in result.output

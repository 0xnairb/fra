from pathlib import Path

from typer.testing import CliRunner

from fra.bootstrap import build_cli
from fra.cli.exit_codes import ExitCode

runner = CliRunner()
FIXTURE = Path(__file__).parents[2] / "fixtures" / "agent_backends" / "fake_codex.py"


def _config(tmp_path: Path) -> Path:
    config = tmp_path / "fra.toml"
    config.write_text(
        f'''[workspace]
root = "{tmp_path / "workspace"}"

[agent.options]
binary = "{FIXTURE}"

[data_sources.manual_documents]
enabled = true
roles = ["primary"]
terms_url = "https://official.example/terms"
terms_reviewed_at = 2026-07-18

[[data_sources.manual_documents.documents]]
provider_record_id = "release-001"
title = "Official release"
url = "https://official.example/release-001"
published_at = 2026-07-18T08:00:00Z
'''
    )
    return config


def test_source_list_describe_check_and_dashboard_use_persisted_status(tmp_path: Path) -> None:
    config = _config(tmp_path)
    runner.invoke(build_cli(), ["--config", str(config), "init"])

    listed = runner.invoke(build_cli(), ["--config", str(config), "sources", "list"])
    described = runner.invoke(
        build_cli(), ["--config", str(config), "sources", "describe", "manual_documents"]
    )
    before_check_dashboard = runner.invoke(
        build_cli(), ["--config", str(config), "dashboard", "--plain-text"]
    )
    assert not (tmp_path / "workspace/source-status/manual_documents.md").exists()
    checked = runner.invoke(
        build_cli(), ["--config", str(config), "sources", "check", "manual_documents"]
    )
    dashboard = runner.invoke(build_cli(), ["--config", str(config), "dashboard", "--plain-text"])

    for result in (listed, described, before_check_dashboard, checked, dashboard):
        assert result.exit_code == ExitCode.SUCCESS, result.output
    assert "manual_documents | primary | official | unknown" in listed.output
    assert "Raw retention: metadata_only" in described.output
    assert "manual_documents | healthy" in checked.output
    assert "manual_documents | primary |" in dashboard.output
    assert "healthy" in dashboard.output
    assert "Capabilities | Quota/limit warning" in dashboard.output
    assert "validated" in dashboard.output
    assert (tmp_path / "workspace/source-status/manual_documents.md").is_file()


def test_wp3_doctor_validates_sources_without_making_a_live_call(tmp_path: Path) -> None:
    config = _config(tmp_path)

    result = runner.invoke(build_cli(), ["--config", str(config), "doctor"])

    assert result.exit_code == ExitCode.SUCCESS
    assert "Source manifests" in result.output
    assert "Source capabilities" in result.output
    assert "manual_documents=unknown" in result.output
    assert "Source terms reviews" in result.output
    assert "10/10 checks passed" in result.output
    assert not (tmp_path / "workspace/source-status/manual_documents.md").exists()

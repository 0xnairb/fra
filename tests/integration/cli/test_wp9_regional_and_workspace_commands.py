from pathlib import Path

import yaml
from typer.testing import CliRunner

from fra.bootstrap import build_cli
from fra.cli.exit_codes import ExitCode

runner = CliRunner()
AGENT = Path(__file__).parents[2] / "fixtures/agent_backends/fake_codex.py"


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "fra.toml"
    path.write_text(
        f'''[workspace]
root = "{(tmp_path / "workspace").as_posix()}"

[agent.options]
binary = "{AGENT.as_posix()}"
'''
    )
    return path


def test_regional_pack_commands_expose_krx_and_vietnam_decisions(tmp_path: Path) -> None:
    config = _config(tmp_path)
    runner.invoke(build_cli(), ["--config", str(config), "init"])

    listed = runner.invoke(build_cli(), ["--config", str(config), "regions", "list"])
    korean = runner.invoke(build_cli(), ["--config", str(config), "regions", "describe", "KR"])
    vietnam = runner.invoke(build_cli(), ["--config", str(config), "regions", "describe", "VN"])

    assert listed.exit_code == ExitCode.SUCCESS
    assert "US | United States | ready" in listed.output
    assert "KR | South Korea | partial" in listed.output
    assert "OpenDART corporation code | 8 digits" in korean.output
    assert "KRX market data is blocked until membership" in korean.output
    assert "Decision completed 2026-07-19" in vietnam.output
    assert "no authoritative price provider is approved" in vietnam.output


def test_workspace_export_migrate_and_disposable_index_recover_from_markdown(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    initialized = runner.invoke(build_cli(), ["--config", str(config), "init"])
    assert initialized.exit_code == ExitCode.SUCCESS
    workspace = tmp_path / "workspace"
    marker = workspace / "workspace.md"
    marker.write_text(marker.read_text().replace("schema_version: 1", "schema_version: 0", 1))

    destination = tmp_path / "migrated"
    migrated = runner.invoke(
        build_cli(),
        ["--config", str(config), "workspace", "migrate", str(destination)],
    )
    assert migrated.exit_code == ExitCode.SUCCESS, migrated.output
    metadata = yaml.safe_load((destination / "workspace.md").read_text().split("---\n")[1])
    assert metadata["schema_version"] == 1
    assert (destination / "migration-report.md").is_file()

    # Restore the source marker, then prove the generated index is optional and rebuildable.
    marker.write_text(marker.read_text().replace("schema_version: 0", "schema_version: 1", 1))
    first = runner.invoke(build_cli(), ["--config", str(config), "workspace", "rebuild-index"])
    assert first.exit_code == ExitCode.SUCCESS, first.output
    generated = workspace / ".indexes/artifacts.json"
    generated.unlink()
    (workspace / "index.md").unlink()
    second = runner.invoke(build_cli(), ["--config", str(config), "workspace", "rebuild-index"])
    dashboard = runner.invoke(build_cli(), ["--config", str(config), "dashboard", "--plain-text"])
    assert second.exit_code == ExitCode.SUCCESS
    assert generated.is_file()
    assert dashboard.exit_code == ExitCode.SUCCESS

    exported = tmp_path / "exported"
    result = runner.invoke(
        build_cli(), ["--config", str(config), "workspace", "export", str(exported)]
    )
    assert result.exit_code == ExitCode.SUCCESS
    assert tuple(exported.rglob("*"))
    assert all(path.suffix == ".md" for path in exported.rglob("*") if path.is_file())
    assert not (exported / ".indexes").exists()

from typer.testing import CliRunner

from fra.cli.app import app
from fra.version import __version__

runner = CliRunner()


def test_version_reports_packaged_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"fra {__version__}\n"

"""Top-level command tree."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from fra.application.doctor_service import DoctorService
from fra.cli.exit_codes import ExitCode, exit_code_for
from fra.errors import ConfigurationError
from fra.security.redaction import redact
from fra.version import __version__


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"fra {__version__}")
        raise typer.Exit


@dataclass(frozen=True, slots=True)
class _CliContext:
    config_path: Path | None


def create_app(doctor_service: DoctorService | None = None) -> typer.Typer:
    """Create presentation handlers around injected application services."""
    cli = typer.Typer(
        name="fra",
        help="Local-first finance research agents.",
        no_args_is_help=True,
        pretty_exceptions_enable=False,
    )

    @cli.callback()
    def root(
        context: typer.Context,
        version: Annotated[
            bool | None,
            typer.Option(
                "--version",
                callback=_version_callback,
                is_eager=True,
                help="Show the installed FRA version and exit.",
            ),
        ] = None,
        config: Annotated[
            Path | None,
            typer.Option(
                "--config",
                dir_okay=False,
                readable=True,
                resolve_path=True,
                help="Read configuration from this TOML file.",
            ),
        ] = None,
    ) -> None:
        """Run FRA commands."""
        context.obj = _CliContext(config_path=config)

    @cli.command()
    def doctor(context: typer.Context) -> None:
        """Validate the runtime and configuration without external calls."""
        try:
            if doctor_service is None:
                raise ConfigurationError("Doctor service is not configured")
            report = doctor_service.check(context.ensure_object(_CliContext).config_path)
        except Exception as error:
            code = exit_code_for(error)
            message = (
                str(error) if code is not ExitCode.INTERNAL_ERROR else "Unexpected internal error"
            )
            typer.echo(f"Error: {redact(message)}", err=True)
            raise typer.Exit(int(code)) from error

        for check in report.checks:
            marker = "pass" if check.ok else "fail"
            typer.echo(f"[{marker}] {check.name}: {check.detail}")
        passed = sum(check.ok for check in report.checks)
        typer.echo(f"{passed}/{len(report.checks)} checks passed")
        if not report.ok:
            raise typer.Exit(int(ExitCode.EXTERNAL_DEPENDENCY))

    return cli


app = create_app()


def main() -> None:
    """Run the CLI command tree."""
    app()

"""Staged, side-effect-free environment diagnostics."""

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MINIMUM_PYTHON = (3, 12)


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


class DoctorService:
    """Validate only the Python runtime and configuration during WP0."""

    def __init__(
        self,
        *,
        configuration_probe: Callable[[Path | None], str],
        python_version: Callable[[], tuple[int, int, int]] | None = None,
    ) -> None:
        self._configuration_probe = configuration_probe
        self._python_version = python_version or _current_python_version

    def check(self, config_path: Path | None) -> DoctorReport:
        version = self._python_version()
        runtime_ok = version[:2] >= MINIMUM_PYTHON
        runtime = DoctorCheck(
            name="Python runtime",
            ok=runtime_ok,
            detail=(
                f"{version[0]}.{version[1]}.{version[2]} "
                f"(requires >= {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]})"
            ),
        )
        configuration_source = self._configuration_probe(config_path)
        configuration = DoctorCheck(
            name="Configuration",
            ok=True,
            detail=f"valid ({configuration_source})",
        )
        return DoctorReport(checks=(runtime, configuration))


def _current_python_version() -> tuple[int, int, int]:
    return sys.version_info.major, sys.version_info.minor, sys.version_info.micro

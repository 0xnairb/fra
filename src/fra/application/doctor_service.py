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
    """Run staged, injected diagnostics without network or agent calls."""

    def __init__(
        self,
        *,
        configuration_probe: Callable[[Path | None], str],
        python_version: Callable[[], tuple[int, int, int]] | None = None,
        workspace_probe: Callable[[Path | None], DoctorCheck] | None = None,
        atomic_repository_probe: Callable[[Path | None], DoctorCheck] | None = None,
        source_probes: Callable[[Path | None], tuple[DoctorCheck, ...]] | None = None,
        agent_probes: Callable[[Path | None], tuple[DoctorCheck, ...]] | None = None,
    ) -> None:
        self._configuration_probe = configuration_probe
        self._python_version = python_version or _current_python_version
        self._workspace_probe = workspace_probe
        self._atomic_repository_probe = atomic_repository_probe
        self._source_probes = source_probes
        self._agent_probes = agent_probes

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
        checks = [runtime, configuration]
        if self._workspace_probe is not None:
            checks.append(self._workspace_probe(config_path))
        if self._atomic_repository_probe is not None:
            checks.append(self._atomic_repository_probe(config_path))
        if self._source_probes is not None:
            checks.extend(self._source_probes(config_path))
        if self._agent_probes is not None:
            checks.extend(self._agent_probes(config_path))
        return DoctorReport(checks=tuple(checks))


def _current_python_version() -> tuple[int, int, int]:
    return sys.version_info.major, sys.version_info.minor, sys.version_info.micro

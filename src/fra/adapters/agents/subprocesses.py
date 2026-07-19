"""Cross-platform subprocess discovery and process-tree termination."""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import sys
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Protocol, cast


class _PosixOs(Protocol):
    def killpg(self, pid: int, signal_number: int) -> None: ...


class _PosixSignal(Protocol):
    SIGKILL: int


_posix_os = cast(_PosixOs, os)
_posix_signal = cast(_PosixSignal, signal)


def executable_command(binary: str, environment: Mapping[str, str]) -> tuple[str, ...]:
    """Resolve PATH shims while keeping Python fixtures directly executable."""
    path = Path(binary)
    if path.suffix.lower() == ".py" and path.is_file():
        return sys.executable, str(path)
    resolved = shutil.which(binary, path=environment.get("PATH"))
    return (resolved or binary,)


async def terminate_process_tree(process: asyncio.subprocess.Process) -> None:
    """Terminate a spawned agent and every child process it started."""
    if process.returncode is not None:
        return
    if os.name == "nt":  # pragma: no cover - exercised by the Windows CI leg
        await _terminate_windows_process_tree(process)
        return
    try:
        _posix_os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=0.5)
    except TimeoutError:
        with suppress(ProcessLookupError):
            _posix_os.killpg(process.pid, _posix_signal.SIGKILL)
        await process.wait()


async def _terminate_windows_process_tree(process: asyncio.subprocess.Process) -> None:
    try:
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        process.kill()
    else:
        await killer.wait()
        if killer.returncode != 0 and process.returncode is None:
            process.kill()
    await process.wait()

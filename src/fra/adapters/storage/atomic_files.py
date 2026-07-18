"""Crash-safe file replacement and per-aggregate process locks."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from contextlib import suppress
from io import TextIOWrapper
from pathlib import Path
from types import TracebackType

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None  # type: ignore[assignment]


class AggregateLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: TextIOWrapper | None = None

    def __enter__(self) -> AggregateLock:
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle = self._path.open("a", encoding="utf-8")
        os.chmod(self._path, 0o600)
        _lock(handle)
        self._handle = handle
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        assert self._handle is not None
        handle = self._handle
        _unlock(handle)
        handle.close()
        self._handle = None


class AtomicFileWriter:
    def __init__(self, *, replace: Callable[[Path, Path], None] | None = None) -> None:
        self._replace = replace or os.replace

    def write_text(self, target: Path, content: str) -> None:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with suppress(AttributeError, OSError):
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            self._replace(temporary, target)
            try:
                directory = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                # Windows and some network filesystems do not permit directory fsync.
                pass
        finally:
            temporary.unlink(missing_ok=True)


def _lock(handle: TextIOWrapper) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return
    import msvcrt  # pragma: no cover - Windows only

    handle.seek(0)
    if handle.read(1) == "":
        handle.write("0")
        handle.flush()
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)


def _unlock(handle: TextIOWrapper) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    import msvcrt  # pragma: no cover - Windows only

    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

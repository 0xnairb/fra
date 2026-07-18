"""Codex CLI subprocess adapter with normalized, secret-safe results."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import signal
import sys
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fra.domain.shared import Failure, FailureKind, HealthState, HealthStatus
from fra.ports.agent_backend import (
    AgentCapabilities,
    AgentEvent,
    AgentEventHandler,
    AgentResultStatus,
    AgentStageRequest,
    AgentStageResult,
    AgentUsage,
    JsonValue,
    StructuredAgentOutput,
)
from fra.security.redaction import redact


class CodexCliAgentAdapter:
    """Invoke stable `codex exec` and translate its JSONL stream once."""

    adapter_version = "fra.codex_cli.v1"

    def __init__(
        self,
        *,
        binary: str = "codex",
        profile: str | None = None,
        sandbox: str = "read-only",
        environment: Mapping[str, str] | None = None,
        secrets: Sequence[str] = (),
    ) -> None:
        self._binary = binary
        self._profile = profile
        self._sandbox = sandbox
        self._environment = {**os.environ, **(environment or {})}
        self._secrets = tuple(secrets)
        self._capabilities = AgentCapabilities(
            structured_output=True,
            session_resume=True,
            event_streaming=True,
            provider_name="codex_cli",
        )

    def capabilities(self) -> AgentCapabilities:
        return self._capabilities

    async def health(self) -> HealthStatus:
        checked_at = datetime.now(UTC)
        version = await self._simple_command((*self._binary_command(), "--version"))
        if version is None:
            return HealthStatus(
                HealthState.UNAVAILABLE,
                checked_at,
                f"Codex binary not available: {self._binary}",
                Failure(
                    FailureKind.ADAPTER_UNAVAILABLE,
                    f"Codex binary not available: {self._binary}",
                    retryable=True,
                    provider_id="codex_cli",
                ),
            )
        help_result = await self._simple_command((*self._binary_command(), "exec", "--help"))
        help_text = help_result[1] if help_result is not None else ""
        self._capabilities = AgentCapabilities(
            structured_output="--output-schema" in help_text,
            session_resume="resume" in help_text,
            event_streaming="--json" in help_text,
            provider_name="codex_cli",
        )
        if not all(
            (
                self._capabilities.structured_output,
                self._capabilities.session_resume,
                self._capabilities.event_streaming,
            )
        ):
            return HealthStatus(
                HealthState.UNAVAILABLE,
                checked_at,
                "Installed Codex lacks required exec capabilities",
                Failure(
                    FailureKind.CAPABILITY_UNSUPPORTED,
                    "Codex requires --json, --output-schema, and exec resume support",
                    provider_id="codex_cli",
                ),
            )
        profile_path = self._profile_path()
        if profile_path is not None and not profile_path.is_file():
            message = f"Codex profile '{self._profile}' is not configured; expected {profile_path}"
            return HealthStatus(
                HealthState.UNAVAILABLE,
                checked_at,
                message,
                Failure(
                    FailureKind.CAPABILITY_UNAVAILABLE,
                    message,
                    provider_id="codex_cli",
                ),
            )
        auth = await self._simple_command(
            (*self._binary_command(), "login", "status"), include_failure=True
        )
        if auth is None or auth[0] != 0:
            detail = auth[1] if auth is not None else "authentication status unavailable"
            return HealthStatus(
                HealthState.UNAVAILABLE,
                checked_at,
                "Codex authentication required",
                Failure(
                    FailureKind.AUTHENTICATION_REQUIRED,
                    redact(detail, secrets=self._secrets),
                    provider_id="codex_cli",
                ),
            )
        return HealthStatus(
            HealthState.HEALTHY,
            checked_at,
            f"Codex {self._version_from_text(version[1])} authenticated",
        )

    async def execute(
        self,
        request: AgentStageRequest,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult:
        return await self._run(request, on_event=on_event)

    async def resume(
        self,
        provider_session_id: str,
        request: AgentStageRequest,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult:
        return await self._run(request, provider_session_id=provider_session_id, on_event=on_event)

    async def _run(
        self,
        request: AgentStageRequest,
        *,
        provider_session_id: str | None = None,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult:
        started_at = datetime.now(UTC)
        try:
            version_result = await self._simple_command((*self._binary_command(), "--version"))
        except asyncio.CancelledError:
            return AgentStageResult(
                status=AgentResultStatus.CANCELLED,
                output=None,
                final_text=None,
                provider_name="codex_cli",
                started_at=started_at,
                ended_at=datetime.now(UTC),
                failure=Failure(
                    FailureKind.CANCELLED,
                    "Codex stage cancelled during capability probing",
                    retryable=True,
                    provider_id="codex_cli",
                ),
            )
        cli_version = (
            self._version_from_text(version_result[1]) if version_result is not None else None
        )
        with tempfile.TemporaryDirectory(prefix="fra-codex-") as temp_directory:
            temp = Path(temp_directory)
            schema_path = temp / "schema.json"
            output_path = temp / "last-message.json"
            schema_path.write_text(json.dumps(request.output_schema), encoding="utf-8")
            arguments = self._arguments(
                request,
                schema_path=schema_path,
                output_path=output_path,
                provider_session_id=provider_session_id,
            )
            try:
                process = await asyncio.create_subprocess_exec(
                    *arguments,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=request.working_directory,
                    env=self._environment,
                    start_new_session=True,
                )
            except FileNotFoundError:
                return self._failure_result(
                    started_at,
                    cli_version,
                    Failure(
                        FailureKind.ADAPTER_UNAVAILABLE,
                        f"Codex binary not available: {self._binary}",
                        retryable=True,
                        provider_id="codex_cli",
                    ),
                )

            assert process.stdin is not None
            process.stdin.write(request.instructions.encode())
            await process.stdin.drain()
            process.stdin.close()

            parser = _CodexEventParser(self._secrets)
            stdout_task = asyncio.create_task(self._read_stdout(process, parser, on_event))
            stderr_task = asyncio.create_task(self._read_stderr(process))
            try:
                await asyncio.wait_for(process.wait(), timeout=request.timeout_seconds)
            except TimeoutError:
                await self._terminate_process_group(process)
                stdout = await stdout_task
                stderr = await stderr_task
                del stdout
                return self._failure_result(
                    started_at,
                    cli_version,
                    Failure(
                        FailureKind.TIMEOUT,
                        f"Codex {request.stage_type.value} stage timed out after "
                        f"{request.timeout_seconds} seconds",
                        retryable=True,
                        provider_id="codex_cli",
                    ),
                    session_id=parser.session_id,
                    warnings=(*parser.warnings, *self._diagnostic_warnings(stderr)),
                )
            except asyncio.CancelledError:
                await self._terminate_process_group(process)
                await stdout_task
                stderr = await stderr_task
                return AgentStageResult(
                    status=AgentResultStatus.CANCELLED,
                    output=None,
                    final_text=parser.final_text,
                    provider_name="codex_cli",
                    provider_session_id=parser.session_id,
                    cli_version=cli_version,
                    model=parser.model,
                    usage=parser.usage,
                    started_at=started_at,
                    ended_at=datetime.now(UTC),
                    warnings=(*parser.warnings, *self._diagnostic_warnings(stderr)),
                    failure=Failure(
                        FailureKind.CANCELLED,
                        "Codex stage cancelled",
                        retryable=True,
                        provider_id="codex_cli",
                    ),
                )

            await stdout_task
            stderr = await stderr_task
            warnings = (*parser.warnings, *self._diagnostic_warnings(stderr))
            if process.returncode != 0:
                detail = (
                    stderr.strip() or parser.error_message or "Codex exited with a non-zero status"
                )
                failure_kind = self._classify_failure(detail)
                return self._failure_result(
                    started_at,
                    cli_version,
                    Failure(
                        failure_kind,
                        redact(detail, secrets=self._secrets),
                        retryable=failure_kind is not FailureKind.AUTHENTICATION_REQUIRED,
                        provider_id="codex_cli",
                    ),
                    session_id=parser.session_id,
                    warnings=warnings,
                )
            try:
                raw_output = json.loads(output_path.read_text(encoding="utf-8"))
                if not isinstance(raw_output, dict):
                    raise ValueError("final structured output must be a JSON object")
                output = StructuredAgentOutput(cast(Mapping[str, JsonValue], raw_output))
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                return self._failure_result(
                    started_at,
                    cli_version,
                    Failure(
                        FailureKind.STRUCTURED_OUTPUT_INVALID,
                        f"Codex returned invalid structured output: {error}",
                        provider_id="codex_cli",
                    ),
                    session_id=parser.session_id,
                    warnings=warnings,
                )
            return AgentStageResult(
                status=AgentResultStatus.COMPLETED,
                output=output,
                final_text=parser.final_text,
                provider_name="codex_cli",
                provider_session_id=parser.session_id,
                cli_version=cli_version,
                model=parser.model,
                usage=parser.usage,
                started_at=started_at,
                ended_at=datetime.now(UTC),
                warnings=warnings,
            )

    def _arguments(
        self,
        request: AgentStageRequest,
        *,
        schema_path: Path,
        output_path: Path,
        provider_session_id: str | None,
    ) -> list[str]:
        arguments = [
            *self._binary_command(),
            "exec",
            "--json",
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "--skip-git-repo-check",
            "--sandbox",
            self._sandbox,
            "--cd",
            str(request.working_directory),
        ]
        if self._profile:
            arguments.extend(("--profile", self._profile))
        if provider_session_id:
            arguments.extend(("resume", provider_session_id))
        arguments.append("-")
        return arguments

    async def _read_stdout(
        self,
        process: asyncio.subprocess.Process,
        parser: _CodexEventParser,
        on_event: AgentEventHandler | None,
    ) -> tuple[str, ...]:
        assert process.stdout is not None
        lines: list[str] = []
        while line := await process.stdout.readline():
            text = line.decode(errors="replace").rstrip("\r\n")
            lines.append(text)
            event = parser.parse(text)
            if event is not None and on_event is not None:
                outcome = on_event(event)
                if inspect.isawaitable(outcome):
                    await outcome
        return tuple(lines)

    async def _read_stderr(self, process: asyncio.subprocess.Process) -> str:
        assert process.stderr is not None
        return (await process.stderr.read()).decode(errors="replace")

    async def _simple_command(
        self, arguments: tuple[str, ...], *, include_failure: bool = False
    ) -> tuple[int, str] | None:
        try:
            process = await asyncio.create_subprocess_exec(
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._environment,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        except (FileNotFoundError, TimeoutError):
            return None
        text = (stdout if process.returncode == 0 else stderr).decode(errors="replace").strip()
        if process.returncode != 0 and not include_failure:
            return None
        return process.returncode or 0, redact(text, secrets=self._secrets)

    @staticmethod
    async def _terminate_process_group(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            if hasattr(os, "killpg"):
                os.killpg(process.pid, signal.SIGTERM)
            else:  # pragma: no cover - Windows only
                process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=0.5)
        except TimeoutError:
            with suppress(ProcessLookupError):
                if hasattr(os, "killpg"):
                    os.killpg(process.pid, signal.SIGKILL)
                else:  # pragma: no cover - Windows only
                    process.kill()
            await process.wait()

    def _diagnostic_warnings(self, stderr: str) -> tuple[str, ...]:
        text = redact(stderr.strip(), secrets=self._secrets)
        return (text,) if text else ()

    def _profile_path(self) -> Path | None:
        if self._profile is None:
            return None
        configured_home = self._environment.get("CODEX_HOME")
        codex_home = Path(configured_home) if configured_home else Path.home() / ".codex"
        return codex_home / f"{self._profile}.config.toml"

    def _binary_command(self) -> tuple[str, ...]:
        path = Path(self._binary)
        if path.suffix.lower() == ".py" and path.is_file():
            return sys.executable, str(path)
        return (self._binary,)

    @staticmethod
    def _classify_failure(stderr: str) -> FailureKind:
        lowered = stderr.lower()
        if "not logged in" in lowered or "authentication" in lowered or "unauthorized" in lowered:
            return FailureKind.AUTHENTICATION_REQUIRED
        return FailureKind.CAPABILITY_UNAVAILABLE

    @staticmethod
    def _version_from_text(value: str) -> str:
        return value.rsplit(" ", 1)[-1]

    @staticmethod
    def _failure_result(
        started_at: datetime,
        cli_version: str | None,
        failure: Failure,
        *,
        session_id: str | None = None,
        warnings: tuple[str, ...] = (),
    ) -> AgentStageResult:
        return AgentStageResult(
            status=AgentResultStatus.FAILED,
            output=None,
            final_text=None,
            provider_name="codex_cli",
            provider_session_id=session_id,
            cli_version=cli_version,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            warnings=warnings,
            failure=failure,
        )


class _CodexEventParser:
    def __init__(self, secrets: Sequence[str]) -> None:
        self._secrets = secrets
        self.session_id: str | None = None
        self.final_text: str | None = None
        self.model: str | None = None
        self.usage: AgentUsage | None = None
        self.warnings: tuple[str, ...] = ()
        self.error_message: str | None = None

    def parse(self, line: str) -> AgentEvent | None:
        try:
            event: Any = json.loads(line)
        except json.JSONDecodeError:
            warning = redact(f"invalid Codex event: {line}", secrets=self._secrets)
            self.warnings = (*self.warnings, warning)
            return None
        if not isinstance(event, dict):
            self.warnings = (*self.warnings, "Codex emitted a non-object event")
            return None
        kind = str(event.get("type", "unknown"))
        if kind in {"error", "turn.failed"}:
            error = event.get("error")
            detail = event.get("message")
            if not isinstance(detail, str) and isinstance(error, dict):
                detail = error.get("message")
            if isinstance(detail, str) and detail:
                self.error_message = redact(detail, secrets=self._secrets)
        if kind == "thread.started":
            self.session_id = _optional_text(event.get("thread_id"))
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            self.final_text = _optional_text(item.get("text"))
        self.model = _optional_text(event.get("model")) or self.model
        usage = event.get("usage")
        if isinstance(usage, dict):
            self.usage = AgentUsage(
                input_tokens=_optional_int(usage.get("input_tokens")),
                cached_input_tokens=_optional_int(usage.get("cached_input_tokens")),
                output_tokens=_optional_int(usage.get("output_tokens")),
                reasoning_output_tokens=_optional_int(usage.get("reasoning_output_tokens")),
            )
        message = self.final_text if kind == "item.completed" and self.final_text else kind
        return AgentEvent(kind, redact(message, secrets=self._secrets), datetime.now(UTC))


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None

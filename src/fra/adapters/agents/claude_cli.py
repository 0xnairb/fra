"""Claude Code CLI adapter using non-interactive schema-constrained JSON output."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import cast

from fra.adapters.agents.subprocesses import executable_command, terminate_process_tree
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


class ClaudeCliAgentAdapter:
    adapter_version = "fra.claude_cli.v1"

    def __init__(
        self,
        *,
        binary: str = "claude",
        permission_mode: str = "plan",
        environment: Mapping[str, str] | None = None,
        secrets: Sequence[str] = (),
    ) -> None:
        self._binary = binary
        self._permission_mode = permission_mode
        self._environment = {**os.environ, **(environment or {})}
        self._secrets = tuple(secrets)
        self._capabilities = AgentCapabilities(True, True, True, "claude_cli")

    def capabilities(self) -> AgentCapabilities:
        return self._capabilities

    async def health(self) -> HealthStatus:
        checked_at = datetime.now(UTC)
        version = await self._command((*self._binary_command(), "--version"))
        if version is None:
            return _health_failure(
                checked_at,
                FailureKind.ADAPTER_UNAVAILABLE,
                f"Claude binary not available: {self._binary}",
            )
        help_result = await self._command((*self._binary_command(), "--help"), include_failure=True)
        help_text = help_result[1] if help_result else ""
        self._capabilities = AgentCapabilities(
            "--json-schema" in help_text,
            "--resume" in help_text,
            "--output-format" in help_text,
            "claude_cli",
        )
        if not all(
            (
                self._capabilities.structured_output,
                self._capabilities.session_resume,
                self._capabilities.event_streaming,
            )
        ):
            return _health_failure(
                checked_at,
                FailureKind.CAPABILITY_UNSUPPORTED,
                "Claude requires --output-format, --json-schema, and --resume support",
            )
        auth = await self._command(
            (*self._binary_command(), "auth", "status"), include_failure=True
        )
        if auth is None or auth[0] != 0:
            return _health_failure(
                checked_at,
                FailureKind.AUTHENTICATION_REQUIRED,
                redact(
                    auth[1] if auth else "Claude authentication status unavailable",
                    secrets=self._secrets,
                ),
            )
        return HealthStatus(
            HealthState.HEALTHY,
            checked_at,
            f"Claude Code {_version(version[1])} authenticated",
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
        return await self._run(
            request,
            provider_session_id=provider_session_id,
            on_event=on_event,
        )

    async def _run(
        self,
        request: AgentStageRequest,
        *,
        provider_session_id: str | None = None,
        on_event: AgentEventHandler | None = None,
    ) -> AgentStageResult:
        started_at = datetime.now(UTC)
        arguments = [
            *self._binary_command(),
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(request.output_schema, sort_keys=True, separators=(",", ":")),
            "--permission-mode",
            self._permission_mode,
            "--tools",
            "Read,Grep,Glob",
        ]
        if provider_session_id:
            arguments.extend(("--resume", provider_session_id))
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
            return self._failure(
                started_at,
                Failure(FailureKind.ADAPTER_UNAVAILABLE, "Claude binary is unavailable"),
            )
        communication = asyncio.create_task(process.communicate(request.instructions.encode()))
        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.shield(communication), timeout=request.timeout_seconds
            )
        except TimeoutError:
            await terminate_process_tree(process)
            await communication
            return self._failure(
                started_at,
                Failure(
                    FailureKind.TIMEOUT,
                    f"Claude {request.stage_type.value} stage timed out after "
                    f"{request.timeout_seconds} seconds",
                    retryable=True,
                    provider_id="claude_cli",
                ),
            )
        except asyncio.CancelledError:
            await terminate_process_tree(process)
            await communication
            return AgentStageResult(
                AgentResultStatus.CANCELLED,
                None,
                None,
                "claude_cli",
                started_at=started_at,
                ended_at=datetime.now(UTC),
                failure=Failure(
                    FailureKind.CANCELLED,
                    "Claude stage cancelled",
                    retryable=True,
                    provider_id="claude_cli",
                ),
            )
        stderr_text = redact(stderr.decode(errors="replace"), secrets=self._secrets)
        if process.returncode != 0:
            kind = (
                FailureKind.AUTHENTICATION_REQUIRED
                if "auth" in stderr_text.lower() or "login" in stderr_text.lower()
                else FailureKind.ADAPTER_UNAVAILABLE
            )
            return self._failure(
                started_at,
                Failure(kind, stderr_text.strip() or "Claude exited unsuccessfully"),
            )
        try:
            payload = json.loads(stdout)
            if not isinstance(payload, dict):
                raise ValueError("Claude result must be a JSON object")
            structured = payload.get("structured_output")
            if not isinstance(structured, dict):
                raise ValueError("Claude result is missing structured_output")
            output = StructuredAgentOutput(cast(Mapping[str, JsonValue], structured))
        except (UnicodeError, json.JSONDecodeError, ValueError) as error:
            return self._failure(
                started_at,
                Failure(
                    FailureKind.STRUCTURED_OUTPUT_INVALID,
                    f"Claude returned invalid structured output: {error}",
                    provider_id="claude_cli",
                ),
            )
        event = AgentEvent("completed", "Claude stage complete", datetime.now(UTC))
        if on_event is not None:
            callback = on_event(event)
            if inspect.isawaitable(callback):
                await callback
        usage_value = payload.get("usage")
        usage = _usage(usage_value) if isinstance(usage_value, dict) else None
        return AgentStageResult(
            AgentResultStatus.COMPLETED,
            output,
            str(payload.get("result", "")),
            "claude_cli",
            provider_session_id=_text(payload.get("session_id")),
            cli_version=_text(payload.get("version")),
            model=_text(payload.get("model")),
            usage=usage,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            warnings=(stderr_text.strip(),) if stderr_text.strip() else (),
        )

    async def _command(
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
        output = (stdout if process.returncode == 0 else stderr).decode(errors="replace").strip()
        if process.returncode != 0 and not include_failure:
            return None
        return process.returncode or 0, output

    def _binary_command(self) -> tuple[str, ...]:
        return executable_command(self._binary, self._environment)

    @staticmethod
    def _failure(started_at: datetime, failure: Failure) -> AgentStageResult:
        return AgentStageResult(
            AgentResultStatus.FAILED,
            None,
            None,
            "claude_cli",
            started_at=started_at,
            ended_at=datetime.now(UTC),
            failure=failure,
        )


def _usage(value: dict[str, object]) -> AgentUsage:
    return AgentUsage(
        input_tokens=_integer(value.get("input_tokens")),
        cached_input_tokens=_integer(value.get("cache_read_input_tokens")),
        output_tokens=_integer(value.get("output_tokens")),
    )


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _version(value: str) -> str:
    return next((part for part in value.split() if any(char.isdigit() for char in part)), value)


def _health_failure(checked_at: datetime, kind: FailureKind, message: str) -> HealthStatus:
    return HealthStatus(
        HealthState.UNAVAILABLE,
        checked_at,
        message,
        Failure(kind, message, provider_id="claude_cli"),
    )

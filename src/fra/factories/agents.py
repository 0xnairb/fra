"""Agent backend construction from validated provider-neutral configuration."""

from fra.adapters.agents.claude_cli import ClaudeCliAgentAdapter
from fra.adapters.agents.codex_cli import CodexCliAgentAdapter
from fra.config.models import AgentConfig
from fra.errors import ConfigurationError
from fra.ports.agent_backend import AgentBackend


class AgentBackendFactory:
    @staticmethod
    def create(config: AgentConfig) -> AgentBackend:
        if config.provider == "codex_cli":
            return CodexCliAgentAdapter(
                binary=config.options.binary,
                profile=config.options.profile,
                sandbox=config.options.sandbox,
            )
        if config.provider == "claude_cli":
            permission_mode = "plan" if config.options.sandbox == "read-only" else "acceptEdits"
            return ClaudeCliAgentAdapter(
                binary=config.options.binary,
                permission_mode=permission_mode,
            )
        raise ConfigurationError(f"Agent provider {config.provider} is not implemented")

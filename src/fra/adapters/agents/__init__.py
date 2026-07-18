"""Installed agentic CLI adapters."""

from fra.adapters.agents.claude_cli import ClaudeCliAgentAdapter
from fra.adapters.agents.codex_cli import CodexCliAgentAdapter

__all__ = ["ClaudeCliAgentAdapter", "CodexCliAgentAdapter"]

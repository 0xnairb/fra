"""TOML loading and boundary-safe validation."""

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from fra.config.models import FRAConfig
from fra.errors import ConfigurationError

_INLINE_SECRET_KEY = re.compile(
    r"(?:^|_)(?:api_?key|token|secret|password|credential)(?:$|_)", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class LoadedConfig:
    """A validated configuration and the file it came from, if any."""

    config: FRAConfig
    source: Path | None


def _inline_secret_paths(value: Any, path: tuple[str, ...] = ()) -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = key.replace("-", "_")
            child_path = (*path, key)
            if _INLINE_SECRET_KEY.search(normalized) and not normalized.lower().endswith("_env"):
                paths.append(".".join(child_path))
            paths.extend(_inline_secret_paths(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            paths.extend(_inline_secret_paths(child, (*path, str(index))))
    return paths


def _validation_message(error: ValidationError) -> str:
    issues: list[str] = []
    for item in error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in item["loc"])
        issues.append(f"{location}: {item['msg']}")
    return "; ".join(issues)


def load_config(path: Path | None = None) -> LoadedConfig:
    """Load a configuration file, or safe defaults when no default file exists."""
    source = path
    if source is None:
        candidate = Path.cwd() / "fra.toml"
        source = candidate if candidate.is_file() else None

    raw: dict[str, Any] = {}
    resolved_source: Path | None = None
    if source is not None:
        resolved_source = source.expanduser().resolve()
        if not resolved_source.is_file():
            raise ConfigurationError(f"Configuration file does not exist: {resolved_source}")
        try:
            with resolved_source.open("rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise ConfigurationError(
                f"Could not read valid TOML configuration: {resolved_source}"
            ) from error

    inline_secrets = _inline_secret_paths(raw)
    if inline_secrets:
        locations = ", ".join(sorted(inline_secrets))
        raise ConfigurationError(
            "Inline secret values are forbidden; reference an environment variable with an "
            f"*_env option instead. Invalid option(s): {locations}"
        )

    try:
        config = FRAConfig.model_validate(raw)
    except ValidationError as error:
        raise ConfigurationError(f"Invalid configuration: {_validation_message(error)}") from error
    return LoadedConfig(config=config, source=resolved_source)


def validate_configuration(path: Path | None) -> str:
    """Validate configuration and return a human-readable, secret-free source label."""
    loaded = load_config(path)
    if loaded.source is None:
        return "built-in defaults"
    return str(loaded.source)

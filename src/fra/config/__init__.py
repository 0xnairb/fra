"""Typed FRA configuration."""

from fra.config.loader import LoadedConfig, load_config
from fra.config.models import FRAConfig

__all__ = ["FRAConfig", "LoadedConfig", "load_config"]

"""Python entry-point discovery used while constructing source adapters."""

from collections.abc import Callable, Iterable
from importlib.metadata import entry_points
from typing import Protocol

from fra.domain.errors import DomainValidationError
from fra.errors import ConfigurationError

SOURCE_ENTRY_POINT_GROUP = "fra.data_sources"


class EntryPointLike(Protocol):
    name: str

    def load(self) -> object: ...


class SourcePluginDiscovery:
    def __init__(
        self,
        discover: Callable[[], Iterable[EntryPointLike]] | None = None,
    ) -> None:
        self._discover = discover

    def load_enabled(self, enabled_names: frozenset[str]) -> tuple[tuple[str, object], ...]:
        if not enabled_names:
            return ()
        candidates = (
            tuple(self._discover())
            if self._discover is not None
            else tuple(entry_points(group=SOURCE_ENTRY_POINT_GROUP))
        )
        names = [item.name for item in candidates]
        duplicate_names = sorted({name for name in names if names.count(name) > 1})
        if duplicate_names:
            raise ConfigurationError(
                "duplicate source plugin entry point name(s): " + ", ".join(duplicate_names)
            )
        by_name = {item.name: item for item in candidates}
        missing = sorted(enabled_names - by_name.keys())
        if missing:
            raise ConfigurationError("enabled source plugin not installed: " + ", ".join(missing))
        loaded = []
        for name in sorted(enabled_names):
            try:
                factory = by_name[name].load()
                if not callable(factory):
                    raise TypeError("entry point must load a zero-argument adapter factory")
                adapter = factory()
            except Exception as error:
                raise ConfigurationError(f"could not load source plugin {name}: {error}") from error
            if not callable(getattr(adapter, "descriptor", None)) or not callable(
                getattr(adapter, "capabilities", None)
            ):
                raise DomainValidationError(
                    f"source plugin {name} does not expose descriptor and capabilities"
                )
            loaded.append((name, adapter))
        return tuple(loaded)

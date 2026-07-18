"""Project-owned typed failures shared across application boundaries."""


class FRAError(Exception):
    """Base class for an expected FRA failure."""


class IncompleteResultError(FRAError):
    """A command completed with a deliberately incomplete result."""


class UserInputRequiredError(FRAError):
    """A command cannot continue without user input."""


class ConfigurationError(FRAError):
    """Configuration is missing or invalid."""


class ExternalDependencyError(FRAError):
    """An external program or service is unavailable."""


class CorruptDataError(FRAError):
    """Persisted data is malformed or unsupported."""

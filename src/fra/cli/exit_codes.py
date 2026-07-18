"""Stable process exit behavior for CLI boundaries."""

from enum import IntEnum

from fra.errors import (
    ConfigurationError,
    CorruptDataError,
    ExternalDependencyError,
    IncompleteResultError,
    UserInputRequiredError,
)


class ExitCode(IntEnum):
    """Public CLI exit codes."""

    SUCCESS = 0
    INCOMPLETE = 1
    USER_INPUT_REQUIRED = 2
    CONFIGURATION = 3
    EXTERNAL_DEPENDENCY = 4
    CORRUPTION = 5
    INTERNAL_ERROR = 70


def exit_code_for(error: BaseException) -> ExitCode:
    """Map a typed failure to its stable process exit code."""
    mappings: tuple[tuple[type[BaseException], ExitCode], ...] = (
        (IncompleteResultError, ExitCode.INCOMPLETE),
        (UserInputRequiredError, ExitCode.USER_INPUT_REQUIRED),
        (ConfigurationError, ExitCode.CONFIGURATION),
        (ExternalDependencyError, ExitCode.EXTERNAL_DEPENDENCY),
        (CorruptDataError, ExitCode.CORRUPTION),
    )
    for error_type, code in mappings:
        if isinstance(error, error_type):
            return code
    return ExitCode.INTERNAL_ERROR

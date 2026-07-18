import pytest

from fra.cli.exit_codes import ExitCode, exit_code_for
from fra.errors import (
    ConfigurationError,
    CorruptDataError,
    ExternalDependencyError,
    IncompleteResultError,
    UserInputRequiredError,
)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (IncompleteResultError("incomplete"), ExitCode.INCOMPLETE),
        (UserInputRequiredError("input"), ExitCode.USER_INPUT_REQUIRED),
        (ConfigurationError("config"), ExitCode.CONFIGURATION),
        (ExternalDependencyError("external"), ExitCode.EXTERNAL_DEPENDENCY),
        (CorruptDataError("corrupt"), ExitCode.CORRUPTION),
    ],
)
def test_expected_failures_have_stable_exit_codes(error: Exception, expected: ExitCode) -> None:
    assert exit_code_for(error) is expected


def test_unexpected_failure_uses_internal_error_exit_code() -> None:
    assert exit_code_for(RuntimeError("boom")) is ExitCode.INTERNAL_ERROR

import pytest

from fra.application.results import failure_from_error
from fra.domain.errors import (
    AdapterUnavailableError,
    AuthenticationRequiredError,
    ExternalTimeoutError,
    UsagePolicyViolationError,
)
from fra.domain.shared import FailureKind


@pytest.mark.parametrize(
    ("error", "expected_kind", "retryable"),
    [
        (
            AdapterUnavailableError("provider unavailable"),
            FailureKind.ADAPTER_UNAVAILABLE,
            True,
        ),
        (
            AuthenticationRequiredError("authentication required"),
            FailureKind.AUTHENTICATION_REQUIRED,
            False,
        ),
        (ExternalTimeoutError("provider timed out"), FailureKind.TIMEOUT, True),
        (
            UsagePolicyViolationError("usage is not permitted"),
            FailureKind.USAGE_POLICY_VIOLATION,
            False,
        ),
    ],
)
def test_expected_adapter_errors_map_to_typed_application_failures(
    error: AdapterUnavailableError
    | AuthenticationRequiredError
    | ExternalTimeoutError
    | UsagePolicyViolationError,
    expected_kind: FailureKind,
    retryable: bool,
) -> None:
    failure = failure_from_error(error)

    assert failure.kind is expected_kind
    assert failure.retryable is retryable

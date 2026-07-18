"""Secret-safe diagnostic text handling."""

import re
from collections.abc import Iterable

REDACTION = "[REDACTED]"

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret|credential)"
    r"(\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)(\bBearer\s+)[^\s,;]+")


def redact(text: str, *, secrets: Iterable[str] = ()) -> str:
    """Remove known values and common credential assignments from text."""
    result = text
    known_values = sorted({value for value in secrets if value}, key=len, reverse=True)
    for value in known_values:
        result = result.replace(value, REDACTION)

    result = _SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTION}", result
    )
    return _BEARER_TOKEN.sub(lambda match: f"{match.group(1)}{REDACTION}", result)

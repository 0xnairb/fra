from fra.security.redaction import redact


def test_redact_removes_known_and_structured_secrets() -> None:
    text = (
        "known=top-secret-value "
        "api_key=abc123 "
        "password: swordfish "
        "Authorization: Bearer bearer-token"
    )

    redacted = redact(text, secrets=("top-secret-value",))

    assert "top-secret-value" not in redacted
    assert "abc123" not in redacted
    assert "swordfish" not in redacted
    assert "bearer-token" not in redacted
    assert redacted.count("[REDACTED]") == 4


def test_redact_ignores_empty_known_secret() -> None:
    assert redact("unchanged", secrets=("",)) == "unchanged"

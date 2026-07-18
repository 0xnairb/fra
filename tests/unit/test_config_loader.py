from pathlib import Path

import pytest

from fra.config.loader import load_config
from fra.errors import ConfigurationError


def test_load_config_uses_safe_defaults_when_no_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    loaded = load_config()

    assert loaded.source is None
    assert loaded.config.workspace.root == Path("fra-workspace")
    assert loaded.config.agent.provider == "codex_cli"


def test_example_configuration_is_valid() -> None:
    example = Path(__file__).parents[2] / "fra.example.toml"

    loaded = load_config(example)

    assert loaded.source == example.resolve()
    assert loaded.config.data_sources.coingecko.enabled is True
    assert loaded.config.storage.provider == "markdown"


def test_unknown_nested_option_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "fra.toml"
    config.write_text('[workspace]\nroot = "workspace"\nunexpected = true\n')

    with pytest.raises(ConfigurationError) as captured:
        load_config(config)

    assert "workspace.unexpected" in str(captured.value)


def test_inline_secret_is_rejected_without_echoing_value() -> None:
    config = Path(__file__).parents[1] / "fixtures" / "config" / "inline-secret.toml"
    secret = "do-not-print-this-value"

    with pytest.raises(ConfigurationError) as captured:
        load_config(config)

    message = str(captured.value)
    assert "inline secret" in message.lower()
    assert "data_sources.coingecko.options.api_key" in message
    assert secret not in message


def test_environment_variable_reference_must_be_a_name(tmp_path: Path) -> None:
    config = tmp_path / "fra.toml"
    config.write_text('[data_sources.eia.options]\napi_key_env = "not a valid environment name"\n')

    with pytest.raises(ConfigurationError) as captured:
        load_config(config)

    assert "data_sources.eia.options.api_key_env" in str(captured.value)

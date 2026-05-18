from pathlib import Path

import pytest

from memorii.core.env_config import (
    EnvironmentConfigError,
    RuntimeEnvironment,
    SecretSource,
    load_memorii_environment,
    require_environment_keys,
)


def test_local_dotenv_file_is_loaded_without_mutating_process_env(tmp_path: Path) -> None:
    local_env_path = tmp_path / "memorii.env"
    local_env_path.write_text(
        "\n".join(
            [
                "# chezmoi managed values",
                "MEMORII_LLM_PROVIDER=openai",
                "export OPENAI_API_KEY='from-file'",
                'MEMORII_LLM_MODEL="gpt test"',
                "ANTHROPIC_API_KEY=key#with-hash # comment",
            ]
        ),
        encoding="utf-8",
    )

    snapshot = load_memorii_environment(env={}, local_env_path=local_env_path)

    assert snapshot.runtime_environment is RuntimeEnvironment.LOCAL
    assert snapshot.secret_source is SecretSource.LOCAL_FILE
    assert snapshot.env["MEMORII_LLM_PROVIDER"] == "openai"
    assert snapshot.env["OPENAI_API_KEY"] == "from-file"
    assert snapshot.env["MEMORII_LLM_MODEL"] == "gpt test"
    assert snapshot.env["ANTHROPIC_API_KEY"] == "key#with-hash"


def test_default_local_path_uses_canonical_memorii_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "memorii.env"
    canonical_path.write_text("MEMORII_LLM_PROVIDER=openai\n", encoding="utf-8")
    monkeypatch.setattr("memorii.core.env_config.DEFAULT_LOCAL_ENV_PATH", canonical_path)

    snapshot = load_memorii_environment(env={})

    assert snapshot.secret_source is SecretSource.LOCAL_FILE
    assert snapshot.env["MEMORII_LLM_PROVIDER"] == "openai"
    assert str(canonical_path) in snapshot.source_description


def test_process_environment_overrides_local_file_values(tmp_path: Path) -> None:
    local_env_path = tmp_path / "memorii.env"
    local_env_path.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")

    snapshot = load_memorii_environment(
        env={"OPENAI_API_KEY": "from-process"},
        local_env_path=local_env_path,
    )

    assert snapshot.env["OPENAI_API_KEY"] == "from-process"


def test_github_actions_detects_ci_and_uses_github_actions_source(tmp_path: Path) -> None:
    snapshot = load_memorii_environment(
        env={"GITHUB_ACTIONS": "true"},
        local_env_path=tmp_path / "missing.env",
    )

    assert snapshot.runtime_environment is RuntimeEnvironment.CI
    assert snapshot.secret_source is SecretSource.GITHUB_ACTIONS


def test_explicit_secret_source_overrides_runtime_default(tmp_path: Path) -> None:
    snapshot = load_memorii_environment(
        env={"MEMORII_ENV": "production", "MEMORII_SECRET_SOURCE": "process"},
        local_env_path=tmp_path / "missing.env",
    )

    assert snapshot.runtime_environment is RuntimeEnvironment.PRODUCTION
    assert snapshot.secret_source is SecretSource.PROCESS


def test_test_environment_defaults_to_process_source(tmp_path: Path) -> None:
    snapshot = load_memorii_environment(
        env={"MEMORII_ENV": "test"},
        local_env_path=tmp_path / "memorii.env",
    )

    assert snapshot.runtime_environment is RuntimeEnvironment.TEST
    assert snapshot.secret_source is SecretSource.PROCESS


def test_production_defaults_to_azure_key_vault_and_requires_url(tmp_path: Path) -> None:
    with pytest.raises(EnvironmentConfigError, match="MEMORII_AKV_URL"):
        load_memorii_environment(
            env={"MEMORII_ENV": "production"},
            local_env_path=tmp_path / "missing.env",
        )


def test_invalid_runtime_environment_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(EnvironmentConfigError, match="Invalid MEMORII_ENV"):
        load_memorii_environment(
            env={"MEMORII_ENV": "staging"},
            local_env_path=tmp_path / "missing.env",
        )


def test_invalid_secret_source_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(EnvironmentConfigError, match="Invalid MEMORII_SECRET_SOURCE"):
        load_memorii_environment(
            env={"MEMORII_SECRET_SOURCE": "vaultish"},
            local_env_path=tmp_path / "missing.env",
        )


def test_require_environment_keys_reports_missing_values() -> None:
    with pytest.raises(EnvironmentConfigError, match="OPENAI_API_KEY"):
        require_environment_keys(
            {"MEMORII_LLM_PROVIDER": "openai", "OPENAI_API_KEY": ""},
            {"MEMORII_LLM_PROVIDER", "OPENAI_API_KEY"},
            context="provider",
        )


def test_snapshot_repr_does_not_include_environment_values(tmp_path: Path) -> None:
    snapshot = load_memorii_environment(
        env={"OPENAI_API_KEY": "secret-value"},
        local_env_path=tmp_path / "missing.env",
    )

    assert "secret-value" not in repr(snapshot)

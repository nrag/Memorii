"""Environment loading for local, CI, test, and production runs."""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class EnvironmentConfigError(RuntimeError):
    """Raised when environment source detection or loading is invalid."""


class RuntimeEnvironment(str, Enum):
    LOCAL = "local"
    TEST = "test"
    CI = "ci"
    PRODUCTION = "production"


class SecretSource(str, Enum):
    PROCESS = "process"
    LOCAL_FILE = "local_file"
    GITHUB_ACTIONS = "github_actions"
    AZURE_KEY_VAULT = "azure_key_vault"


class EnvironmentSnapshot(BaseModel):
    runtime_environment: RuntimeEnvironment
    secret_source: SecretSource
    source_description: str
    env: Mapping[str, str] = Field(repr=False)

    model_config = ConfigDict(extra="forbid", frozen=True)


DEFAULT_LOCAL_ENV_PATH = Path.home() / ".config" / "memorii" / "memory.env"
MEMORII_ENV_KEY = "MEMORII_ENV"
MEMORII_SECRET_SOURCE_KEY = "MEMORII_SECRET_SOURCE"
MEMORII_AKV_URL_KEY = "MEMORII_AKV_URL"
AZURE_KEY_VAULT_URL_KEY = "AZURE_KEY_VAULT_URL"
MEMORII_AKV_SECRET_NAMES_KEY = "MEMORII_AKV_SECRET_NAMES"
MEMORII_AKV_SECRET_PREFIX_KEY = "MEMORII_AKV_SECRET_PREFIX"


def load_memorii_environment(
    env: Mapping[str, str] | None = None,
    local_env_path: Path | None = None,
) -> EnvironmentSnapshot:
    """Load a source-aware environment mapping without mutating ``os.environ``."""

    process_env = _string_mapping(os.environ if env is None else env)
    resolved_local_env_path = local_env_path or DEFAULT_LOCAL_ENV_PATH
    local_file_exists = resolved_local_env_path.exists()
    runtime_environment = _detect_runtime_environment(process_env, local_file_exists)
    secret_source = _detect_secret_source(process_env, runtime_environment, local_file_exists)

    if secret_source is SecretSource.LOCAL_FILE:
        file_env = _read_dotenv_file(resolved_local_env_path)
        merged_env = {**file_env, **process_env}
        source_description = f"local dotenv file at {resolved_local_env_path}"
    elif secret_source is SecretSource.AZURE_KEY_VAULT:
        azure_env = _load_azure_key_vault_env(process_env)
        merged_env = {**process_env, **azure_env}
        vault_url = _get_akv_url(process_env)
        source_description = f"Azure Key Vault at {vault_url}"
    elif secret_source is SecretSource.GITHUB_ACTIONS:
        merged_env = dict(process_env)
        source_description = "GitHub Actions injected process environment"
    else:
        merged_env = dict(process_env)
        source_description = "process environment"

    return EnvironmentSnapshot(
        runtime_environment=runtime_environment,
        secret_source=secret_source,
        source_description=source_description,
        env=merged_env,
    )


def require_environment_keys(
    env: Mapping[str, str],
    keys: set[str] | frozenset[str],
    *,
    context: str,
) -> None:
    """Validate that a mapping contains non-empty values for the requested keys."""

    missing_keys = sorted(key for key in keys if not env.get(key))
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise EnvironmentConfigError(f"Missing required {context} environment variables: {missing}")


def _detect_runtime_environment(env: Mapping[str, str], local_file_exists: bool) -> RuntimeEnvironment:
    explicit_value = env.get(MEMORII_ENV_KEY)
    if explicit_value:
        return _parse_runtime_environment(explicit_value)
    if env.get("GITHUB_ACTIONS", "").lower() == "true":
        return RuntimeEnvironment.CI
    if env.get(MEMORII_AKV_URL_KEY) or env.get(AZURE_KEY_VAULT_URL_KEY):
        return RuntimeEnvironment.PRODUCTION
    if local_file_exists:
        return RuntimeEnvironment.LOCAL
    return RuntimeEnvironment.LOCAL


def _detect_secret_source(
    env: Mapping[str, str],
    runtime_environment: RuntimeEnvironment,
    local_file_exists: bool,
) -> SecretSource:
    explicit_value = env.get(MEMORII_SECRET_SOURCE_KEY)
    if explicit_value:
        return _parse_secret_source(explicit_value)
    if runtime_environment is RuntimeEnvironment.CI:
        return SecretSource.GITHUB_ACTIONS
    if runtime_environment is RuntimeEnvironment.PRODUCTION:
        return SecretSource.AZURE_KEY_VAULT
    if runtime_environment is RuntimeEnvironment.TEST:
        return SecretSource.PROCESS
    if local_file_exists:
        return SecretSource.LOCAL_FILE
    return SecretSource.PROCESS


def _parse_runtime_environment(value: str) -> RuntimeEnvironment:
    normalized_value = value.strip().lower()
    try:
        return RuntimeEnvironment(normalized_value)
    except ValueError as error:
        allowed_values = ", ".join(item.value for item in RuntimeEnvironment)
        raise EnvironmentConfigError(
            f"Invalid {MEMORII_ENV_KEY}={value!r}. Expected one of: {allowed_values}."
        ) from error


def _parse_secret_source(value: str) -> SecretSource:
    normalized_value = value.strip().lower()
    try:
        return SecretSource(normalized_value)
    except ValueError as error:
        allowed_values = ", ".join(item.value for item in SecretSource)
        raise EnvironmentConfigError(
            f"Invalid {MEMORII_SECRET_SOURCE_KEY}={value!r}. Expected one of: {allowed_values}."
        ) from error


def _read_dotenv_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise EnvironmentConfigError(f"Local environment file does not exist: {path}")

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise EnvironmentConfigError(f"Invalid dotenv line {line_number} in {path}: missing '='.")

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise EnvironmentConfigError(f"Invalid dotenv line {line_number} in {path}: missing key.")
        values[key] = _parse_dotenv_value(raw_value.strip())
    return values


def _parse_dotenv_value(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(("'", '"')):
        comment_index = _find_unquoted_comment_index(value)
        if comment_index is not None:
            return value[:comment_index].rstrip()
        return value
    try:
        parsed_values = shlex.split(value, comments=False, posix=True)
    except ValueError as error:
        raise EnvironmentConfigError(f"Invalid dotenv value {value!r}: {error}") from error
    if not parsed_values:
        return ""
    return " ".join(parsed_values)


def _find_unquoted_comment_index(value: str) -> int | None:
    for index, character in enumerate(value):
        if character == "#" and index > 0 and value[index - 1].isspace():
            return index
    return None


def _load_azure_key_vault_env(env: Mapping[str, str]) -> dict[str, str]:
    vault_url = _get_akv_url(env)
    if not vault_url:
        raise EnvironmentConfigError(
            f"{MEMORII_AKV_URL_KEY} or {AZURE_KEY_VAULT_URL_KEY} is required when "
            f"{MEMORII_SECRET_SOURCE_KEY}={SecretSource.AZURE_KEY_VAULT.value}."
        )

    secret_names = _parse_akv_secret_names(env)
    require_environment_keys(
        {MEMORII_AKV_SECRET_NAMES_KEY: ",".join(secret_names)},
        {MEMORII_AKV_SECRET_NAMES_KEY},
        context="Azure Key Vault source",
    )

    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError as error:
        raise EnvironmentConfigError(
            "Azure Key Vault environment loading requires the 'azure' optional dependency. "
            "Install Memorii with the azure extra."
        ) from error

    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)
    secret_prefix = env.get(MEMORII_AKV_SECRET_PREFIX_KEY, "")
    loaded_env: dict[str, str] = {}
    for env_key in secret_names:
        vault_secret_name = f"{secret_prefix}{env_key}".replace("_", "-")
        loaded_env[env_key] = client.get_secret(vault_secret_name).value or ""
    return loaded_env


def _get_akv_url(env: Mapping[str, str]) -> str:
    return env.get(MEMORII_AKV_URL_KEY) or env.get(AZURE_KEY_VAULT_URL_KEY) or ""


def _parse_akv_secret_names(env: Mapping[str, str]) -> tuple[str, ...]:
    raw_secret_names = env.get(MEMORII_AKV_SECRET_NAMES_KEY, "")
    return tuple(name.strip() for name in raw_secret_names.split(",") if name.strip())


def _string_mapping(env: Mapping[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in env.items()}

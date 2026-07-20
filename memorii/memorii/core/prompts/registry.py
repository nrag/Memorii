from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel

from memorii.core.prompts.models import PromptContract
from memorii.core.prompts.runtime_manifest import (
    PromptOwner,
    PromptRuntimeRegistration,
    prompt_runtime_registrations,
)
from memorii.core.prompts.schema_parity import (
    assert_output_schema_matches_model,
    assert_supported_json_schema,
)


def default_prompt_root() -> Path:
    """Return the package-owned prompt-contract directory."""

    return Path(__file__).resolve().parents[2] / "prompts"


class RegisteredPromptContract(PromptContract):
    """Prompt text, schema, and security policy loaded as one atomic unit."""

    runtime_registration: PromptRuntimeRegistration
    registration_digest: str


def prompt_registration_digest(
    contract: PromptContract,
    runtime_registration: PromptRuntimeRegistration,
) -> str:
    payload = {
        "contract": contract.model_dump(mode="json", include=set(PromptContract.model_fields)),
        "runtime_registration": runtime_registration.model_dump(mode="json"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PromptRegistry:
    def __init__(
        self,
        *,
        prompt_root: str | Path | None = None,
        registrations: dict[str, PromptRuntimeRegistration] | None = None,
    ):
        self.prompt_root = Path(prompt_root or default_prompt_root()).resolve()
        self.registrations = registrations or prompt_runtime_registrations()

    def load(
        self,
        prompt_ref: str,
        *,
        owner: PromptOwner | str,
        output_model: type[BaseModel],
    ) -> RegisteredPromptContract:
        runtime_registration = self.registrations.get(prompt_ref)
        if runtime_registration is None:
            raise ValueError(f"Prompt is not registered in the contract manifest: {prompt_ref}")
        expected_owner = owner.value if isinstance(owner, PromptOwner) else owner
        if runtime_registration.owning_adapter.value != expected_owner:
            raise ValueError(
                f"Prompt {prompt_ref} is owned by {runtime_registration.owning_adapter.value}, not {owner}"
            )
        path = self._resolve_prompt_path(prompt_ref)
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found for ref: {prompt_ref}")
        payload = yaml.safe_load(path.read_text())
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid prompt YAML for ref: {prompt_ref}")
        contract = PromptContract.model_validate(payload)
        actual_ref = f"{contract.prompt_id}:{contract.version}"
        if actual_ref != prompt_ref:
            raise ValueError(f"Prompt YAML identity {actual_ref} does not match requested ref {prompt_ref}")
        assert_supported_json_schema(
            schema_name=f"{prompt_ref}.input_schema",
            schema=contract.input_schema,
        )
        assert_output_schema_matches_model(
            prompt_ref=prompt_ref,
            output_schema=contract.output_schema,
            output_model=output_model,
        )
        return RegisteredPromptContract.model_validate(
            {
                **contract.model_dump(mode="python"),
                "runtime_registration": runtime_registration,
                "registration_digest": prompt_registration_digest(contract, runtime_registration),
            }
        )

    def list_prompt_refs(self) -> list[str]:
        refs: list[str] = []
        for prompt_file in sorted(self.prompt_root.glob("**/*.yaml")):
            rel = prompt_file.relative_to(self.prompt_root)
            refs.append(f"{rel.parent.as_posix()}:{rel.stem}")
        return refs

    def _resolve_prompt_path(self, prompt_ref: str) -> Path:
        rel = self._prompt_ref_to_relative_path(prompt_ref)
        resolved = (self.prompt_root / rel).resolve()
        if self.prompt_root not in resolved.parents:
            raise ValueError(f"Malformed prompt_ref: {prompt_ref}")
        return resolved

    def _prompt_ref_to_relative_path(self, prompt_ref: str) -> Path:
        if prompt_ref.count(":") != 1:
            raise ValueError(f"Malformed prompt_ref: {prompt_ref}")
        prompt_id, version = prompt_ref.split(":", 1)
        if not prompt_id or not version:
            raise ValueError(f"Malformed prompt_ref: {prompt_ref}")
        if prompt_id.startswith("/") or version.startswith("/"):
            raise ValueError(f"Malformed prompt_ref: {prompt_ref}")
        return Path(prompt_id) / f"{version}.yaml"

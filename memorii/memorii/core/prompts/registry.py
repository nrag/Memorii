from __future__ import annotations

from pathlib import Path

import yaml

from memorii.core.prompts.manifest import PromptContractManifest, PromptOwner, prompt_contract_manifest
from memorii.core.prompts.models import PromptContract


class PromptRegistry:
    def __init__(
        self,
        *,
        prompt_root: str | Path,
        require_manifest: bool = False,
        manifest: PromptContractManifest | None = None,
    ):
        self.prompt_root = Path(prompt_root).resolve()
        self.require_manifest = require_manifest
        self.manifest = manifest or prompt_contract_manifest()

    def load(self, prompt_ref: str, *, owner: PromptOwner | str | None = None) -> PromptContract:
        manifest_entry = self.manifest.by_prompt_ref().get(prompt_ref)
        if self.require_manifest and manifest_entry is None:
            raise ValueError(f"Prompt is not registered in the contract manifest: {prompt_ref}")
        expected_owner = owner.value if isinstance(owner, PromptOwner) else owner
        if owner is not None and manifest_entry is not None and manifest_entry.owning_adapter.value != expected_owner:
            raise ValueError(
                f"Prompt {prompt_ref} is owned by {manifest_entry.owning_adapter.value}, not {owner}"
            )
        path = self._resolve_prompt_path(prompt_ref)
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found for ref: {prompt_ref}")
        payload = yaml.safe_load(path.read_text())
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid prompt YAML for ref: {prompt_ref}")
        return PromptContract.model_validate(payload)

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

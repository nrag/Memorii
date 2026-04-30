from __future__ import annotations

from pathlib import Path

import yaml

from memorii.core.prompts.models import PromptContract


class PromptRegistry:
    def __init__(self, *, prompt_root: str | Path):
        self.prompt_root = Path(prompt_root)

    def load(self, prompt_ref: str) -> PromptContract:
        path = self.prompt_root / self._prompt_ref_to_relative_path(prompt_ref)
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
            version = rel.stem
            prefix = str(rel.parent).replace("\\", "/")
            refs.append(f"{prefix}:{version}")
        return refs

    def _prompt_ref_to_relative_path(self, prompt_ref: str) -> Path:
        if prompt_ref.count(":") != 1:
            raise ValueError(f"Malformed prompt_ref: {prompt_ref}")
        prompt_id, version = prompt_ref.split(":", 1)
        if not prompt_id or not version:
            raise ValueError(f"Malformed prompt_ref: {prompt_ref}")
        return Path(prompt_id) / f"{version}.yaml"

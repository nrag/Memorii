from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from string import Formatter

from memorii.core.prompts.models import PromptContract, PromptRedactionPolicy, RenderedPrompt


def _serialize_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if value is None:
        return "null"
    return str(value)


def redact_variables(*, variables: dict[str, object], policy: PromptRedactionPolicy) -> dict[str, object]:
    redacted = deepcopy(variables)

    for key in policy.redact_input_fields:
        if key in redacted:
            redacted[key] = "[REDACTED]"

    input_payload = redacted.get("input_payload")
    if isinstance(input_payload, dict):
        for key in policy.redact_input_fields:
            if key in input_payload:
                input_payload[key] = "[REDACTED]"

    for output_key in ("actual_output", "expected_output"):
        output_payload = redacted.get(output_key)
        if isinstance(output_payload, dict):
            for key in policy.redact_output_fields:
                if key in output_payload:
                    output_payload[key] = "[REDACTED]"

    metadata = redacted.get("metadata")
    if isinstance(metadata, dict):
        for key in policy.redact_metadata_fields:
            if key in metadata:
                metadata[key] = "[REDACTED]"

    return redacted


class PromptRenderer:
    def render(self, *, contract: PromptContract, variables: dict[str, object]) -> RenderedPrompt:
        safe_variables = redact_variables(variables=variables, policy=contract.redaction)
        formatted_variables = {k: _serialize_value(v) for k, v in safe_variables.items()}

        for _, field_name, _, _ in Formatter().parse(contract.system_template + contract.user_template):
            if field_name and field_name not in formatted_variables:
                raise KeyError(field_name)

        system = contract.system_template.format(**formatted_variables)
        user = contract.user_template.format(**formatted_variables)

        normalized_contract = json.dumps(contract.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        payload = "\n".join([normalized_contract, system, user])
        prompt_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        return RenderedPrompt(
            prompt_ref=f"{contract.prompt_id}:{contract.version}",
            prompt_id=contract.prompt_id,
            version=contract.version,
            prompt_hash=prompt_hash,
            system=system,
            user=user,
            model_defaults=contract.model_defaults,
            expected_output_schema=contract.output_schema,
        )

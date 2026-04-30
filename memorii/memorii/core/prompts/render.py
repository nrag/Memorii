from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from string import Formatter

from memorii.core.prompts.models import PromptContract, PromptRedactionPolicy, RenderedPrompt

_PLACEHOLDER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _serialize_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if value is None:
        return "null"
    return str(value)


def _deep_redact(value: object, redact_fields: set[str]) -> object:
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, nested in value.items():
            if key in redact_fields:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _deep_redact(nested, redact_fields)
        return redacted
    if isinstance(value, list):
        return [_deep_redact(item, redact_fields) for item in value]
    return value


def redact_variables(*, variables: dict[str, object], policy: PromptRedactionPolicy) -> dict[str, object]:
    redacted = deepcopy(variables)
    input_fields = set(policy.redact_input_fields)

    for key in input_fields:
        if key in redacted:
            redacted[key] = "[REDACTED]"

    for key in ("input_payload", "actual_output", "expected_output", "metadata"):
        if key in redacted:
            if key == "metadata":
                redacted[key] = _deep_redact(redacted[key], set(policy.redact_metadata_fields))
            elif key in ("actual_output", "expected_output"):
                redacted[key] = _deep_redact(redacted[key], set(policy.redact_output_fields))
            else:
                redacted[key] = _deep_redact(redacted[key], input_fields)

    return redacted


def _validate_templates(contract: PromptContract, variables: dict[str, str]) -> None:
    for template in (contract.system_template, contract.user_template):
        for _, field_name, format_spec, conversion in Formatter().parse(template):
            if field_name is None:
                continue
            if conversion is not None or format_spec:
                raise ValueError("Only simple {variable_name} placeholders are allowed")
            if not _PLACEHOLDER_PATTERN.match(field_name):
                raise ValueError("Only simple {variable_name} placeholders are allowed")
            if field_name not in variables:
                raise KeyError(field_name)


class PromptRenderer:
    def render(self, *, contract: PromptContract, variables: dict[str, object]) -> RenderedPrompt:
        safe_variables = redact_variables(variables=variables, policy=contract.redaction)
        formatted_variables = {k: _serialize_value(v) for k, v in safe_variables.items()}
        _validate_templates(contract, formatted_variables)

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

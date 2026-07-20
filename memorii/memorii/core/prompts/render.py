from __future__ import annotations

import hashlib
import json
import re
from string import Formatter
from typing import TypeAlias, cast

from jsonschema import Draft202012Validator, FormatChecker

from memorii.core.prompts.models import PromptContract, PromptRedactionPolicy, RenderedPrompt
from memorii.core.prompts.registry import RegisteredPromptContract, prompt_registration_digest
from memorii.core.prompts.sensitivity import normalize_sensitive_key, sanitize_json_value

_PLACEHOLDER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def _serialize_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if value is None:
        return "null"
    return str(value)


def redact_variables(
    *,
    variables: dict[str, object],
    policy: PromptRedactionPolicy,
    forbidden_input_fields: set[str] | None = None,
) -> dict[str, object]:
    input_fields = frozenset(normalize_sensitive_key(key) for key in policy.redact_input_fields)
    forbidden_fields = frozenset(
        normalize_sensitive_key(key) for key in (forbidden_input_fields or set())
    )
    redacted = cast(
        dict[str, object],
        sanitize_json_value(
            variables,
            remove_fields=forbidden_fields,
            redact_fields=input_fields,
        ),
    )

    for key in ("input_payload", "actual_output", "expected_output", "metadata"):
        if key in redacted:
            if key == "metadata":
                redacted[key] = sanitize_json_value(
                    redacted[key],
                    redact_fields=frozenset(
                        normalize_sensitive_key(item) for item in policy.redact_metadata_fields
                    ),
                )
            elif key in ("actual_output", "expected_output"):
                redacted[key] = sanitize_json_value(
                    redacted[key],
                    redact_fields=frozenset(
                        normalize_sensitive_key(item) for item in policy.redact_output_fields
                    ),
                )
            else:
                redacted[key] = sanitize_json_value(redacted[key], redact_fields=input_fields)

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
    def render(self, *, contract: RegisteredPromptContract, variables: dict[str, object]) -> RenderedPrompt:
        prompt_ref = f"{contract.prompt_id}:{contract.version}"
        registration = contract.runtime_registration
        if registration.prompt_ref != prompt_ref:
            raise ValueError("registered prompt policy does not match prompt identity")
        expected_digest = prompt_registration_digest(contract, registration)
        if contract.registration_digest != expected_digest:
            raise ValueError("registered prompt contract was modified after registration")
        safe_variables = redact_variables(
            variables=variables,
            policy=contract.redaction,
            forbidden_input_fields=set(registration.visibility_policy.forbidden_input_fields),
        )
        json_variables = cast(dict[str, JsonValue], safe_variables)
        validation_errors = sorted(
            Draft202012Validator(
                contract.input_schema,
                format_checker=FormatChecker(),
            ).iter_errors(json_variables),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if validation_errors:
            error = validation_errors[0]
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            raise ValueError(f"Prompt input validation failed at {location}: {error.message}")
        formatted_variables = {k: _serialize_value(v) for k, v in safe_variables.items()}
        _validate_templates(contract, formatted_variables)

        system = contract.system_template.format(**formatted_variables)
        user = contract.user_template.format(**formatted_variables)

        normalized_contract = json.dumps(contract.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        payload = "\n".join([normalized_contract, system, user])
        prompt_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        return RenderedPrompt(
            prompt_ref=prompt_ref,
            prompt_id=contract.prompt_id,
            version=contract.version,
            prompt_hash=prompt_hash,
            system=system,
            user=user,
            model_defaults=contract.model_defaults,
            expected_output_schema=contract.output_schema,
        )

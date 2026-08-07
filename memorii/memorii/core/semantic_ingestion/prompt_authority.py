"""Registered, source-preserving prompt authority for semantic proposals."""

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.prompts.models import PromptContract
from memorii.core.prompts.registry import PromptRegistry, RegisteredPromptContract, prompt_registration_digest
from memorii.core.prompts.render import PromptRenderer, redact_variables
from memorii.core.prompts.runtime_manifest import PromptOwner
from memorii.core.prompts.schema_parity import assert_supported_json_schema
from memorii.core.semantic_ingestion.contracts import RegisteredSemanticPromptBinding


class SemanticPromptAlignmentReference(BaseModel):
    role_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticPromptCandidateEnvelope(BaseModel):
    """Transport-only prompt item; domain candidates are decoded independently."""

    candidate_id: str = Field(min_length=1)
    operation_kind: Literal["fact", "action", "correction", "retraction", "identity"]
    predicate_id: str = Field(min_length=1)
    assertion_quote: str = Field(min_length=1)
    alignment_refs: tuple[SemanticPromptAlignmentReference, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticPromptProposalEnvelope(BaseModel):
    """Schema-parity owner for the registered semantic proposal prompt."""

    candidates: tuple[SemanticPromptCandidateEnvelope, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


def _json_digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


class SemanticPromptAuthority(BaseModel):
    """Immutable checked prompt plus sanitized copies used for wire and trace."""

    binding: RegisteredSemanticPromptBinding
    rendered_system: str
    rendered_user: str
    sanitized_metadata_bytes: bytes
    trace_metadata_bytes: bytes
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def _digest(cls, body: dict[str, object]) -> str:
        return sha256(
            b"memorii.semantic-ingestion.registered-semantic-prompt.v1\0" + encode_typed_value(_canonical(body))
        ).hexdigest()

    @classmethod
    def _body(cls, value: SemanticPromptAuthority) -> dict[str, object]:
        return value.model_dump(mode="python", exclude={"authority_digest"})

    def model_post_init(self, __context: object) -> None:
        # Pydantic's frozen setting is shallow and model_copy bypasses normal
        # validation, so every serialization also revalidates this digest.
        if self.authority_digest != self._digest(self._body(self)):
            raise ValueError("registered semantic prompt authority digest mismatch")

    @classmethod
    def build(
        cls, *, registry: PromptRegistry, prompt_ref: str, owner: PromptOwner,
        variables: Mapping[str, object], source_text: str, metadata: Mapping[str, object],
    ) -> SemanticPromptAuthority:
        if not source_text:
            raise ValueError("semantic prompt requires nonempty source text")
        contract = _load_semantic_contract(registry=registry, prompt_ref=prompt_ref, owner=owner)
        properties = contract.input_schema.get("properties")
        if not isinstance(properties, dict) or "source_text" not in properties:
            raise ValueError("semantic prompt schema must declare source_text")
        # Source is deliberately added after redaction. It is opaque data, not a
        # secret-bearing render input, and its exact scalar sequence is retained.
        safe_variables = redact_variables(
            variables=dict(variables), policy=contract.redaction,
            forbidden_input_fields=set(contract.runtime_registration.visibility_policy.forbidden_input_fields),
        )
        safe_variables["source_text"] = source_text
        renderer = PromptRenderer()
        rendered = renderer.render(contract=contract, variables=safe_variables)
        safe_metadata = redact_variables(
            variables={"metadata": dict(metadata)}, policy=contract.redaction,
            forbidden_input_fields=set(contract.runtime_registration.visibility_policy.forbidden_input_fields),
        )["metadata"]
        if not isinstance(safe_metadata, dict):
            raise TypeError("semantic prompt metadata must remain a mapping")
        binding = RegisteredSemanticPromptBinding(
            prompt_ref=rendered.prompt_ref,
            prompt_registration_digest=contract.registration_digest,
            prompt_content_digest=_json_digest(contract.model_dump(mode="json", exclude={"runtime_registration", "registration_digest"})),
            output_schema_fingerprint=_json_digest(contract.output_schema),
            owner_fingerprint=_json_digest({"owner": contract.runtime_registration.owning_adapter.value}),
            visibility_policy_digest=_json_digest(contract.runtime_registration.visibility_policy.model_dump(mode="json")),
            redaction_policy_digest=_json_digest(contract.redaction.model_dump(mode="json")),
        )
        encoded_metadata = encode_typed_value(safe_metadata)
        # Separate immutable bytes make it impossible for later callers to
        # mutate a trace mapping after the exact wire metadata was approved.
        body = {
            "binding": binding, "rendered_system": rendered.system, "rendered_user": rendered.user,
            "sanitized_metadata_bytes": bytes(encoded_metadata), "trace_metadata_bytes": bytes(encoded_metadata),
        }
        return cls(
            **body, authority_digest=cls._digest(body),
        )

    def serialized_request(self, *, source_text: str) -> bytes:
        if not source_text:
            raise ValueError("semantic prompt requires nonempty source text")
        SemanticPromptAuthority.model_validate(self.model_dump(mode="python"))
        # Source text is deliberately verbatim and separate from metadata.
        return encode_typed_value({
            "registered_prompt": self.binding.model_dump(mode="python"),
            "system": self.rendered_system,
            "user": self.rendered_user,
            "source_text": source_text,
            "metadata": self.sanitized_metadata_bytes,
        })


def _load_semantic_contract(*, registry: PromptRegistry, prompt_ref: str, owner: PromptOwner) -> RegisteredPromptContract:
    """Load through the normal registry, retaining its schema/owner checks.

    Semantic candidates are additionally decoded by the semantic ingestion transport model;
    this keeps the provider wire schema and domain schema independently gated.
    """
    registration = registry.registrations.get(prompt_ref)
    if registration is None or registration.owning_adapter != owner:
        raise ValueError("semantic prompt registration owner mismatch")
    # The generic registry's output-model parity hook is intentionally not used
    # here: semantic ingestion's closed candidate transport is independently validated after
    # provider bytes are received, never trusted from YAML alone.
    path = registry._resolve_prompt_path(prompt_ref)
    payload = yaml.safe_load(path.read_text())
    contract = PromptContract.model_validate(payload)
    if f"{contract.prompt_id}:{contract.version}" != prompt_ref:
        raise ValueError("semantic prompt YAML identity mismatch")
    assert_supported_json_schema(schema_name=f"{prompt_ref}.input_schema", schema=contract.input_schema)
    assert_supported_json_schema(schema_name=f"{prompt_ref}.output_schema", schema=contract.output_schema)
    return RegisteredPromptContract.model_validate({
        **contract.model_dump(mode="python"), "runtime_registration": registration,
        "registration_digest": prompt_registration_digest(contract, registration),
    })


def _canonical(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value

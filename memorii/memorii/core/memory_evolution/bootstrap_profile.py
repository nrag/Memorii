"""Closed, source-only governed-source admission bootstrap profile contracts.

Operational trust roots are deliberately supplied by the host boundary; this
module contains no root, credential, network client, or writer-safe preplanning resource state.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from importlib.metadata import entry_points
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, TypedDict, Unpack, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
    decode_artifact,
    decode_typed_value,
    encode_typed_value,
    serialize_artifact,
)

if TYPE_CHECKING:
    from memorii.core.semantic_ingestion.contracts import TextPreparationPolicy

_DIGEST = Field(pattern=r"^[0-9a-f]{64}$")
_CTV_PROFILE_ID = "semantic_ingestion_typed_value"
_CTV_PROFILE_VERSION = 2
_CTV_PROFILE_DIGEST = "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f"
_BOOTSTRAP_ARTIFACT_BINDING_DIGESTS = {
    ("memorii.semantic_ingestion.bootstrap_local_profile_manifest", 1):
        "0136ac668b2cb67e9b3e4740da0299e757492707de47f079003ae2259173e87d",
    ("memorii.semantic_ingestion.bootstrap_grammar_capability_manifest", 1):
        "80a0adf476264036eca1e604596871a7abbf05e634f1b0fbac4421aa516d0121",
    # These are frozen CTV binding identities, not content digests.  Content
    # substitution is detected by the nested artifact and release digests.
    ("memorii.semantic_ingestion.bootstrap_local_profile_manifest", 2):
        "2a8f9ad8329124fbb24e28ac052f28e960c8a7fe94e9f1c75a83d8d3a23db9d1",
    ("memorii.semantic_ingestion.bootstrap_grammar_capability_manifest", 2):
        "25a93c7dba8b6f90df699e946fb3d1f621f21c3ace76a61ebd67942a041c3d3f",
    ("memorii.semantic_ingestion.bootstrap_freeform_admission_policy", 1):
        "0cdf3736b5bd73f5897fa1ba2eaf362811e234a2810e6e77cbe6245709289f30",
}


class BootstrapProfileCoordinate(BaseModel):
    """The sole installed Bootstrap V3 profile coordinate."""

    schema_id: Literal["memorii.semantic_ingestion.bootstrap_profile_coordinate"]
    schema_version: Literal[2]
    profile_id: Literal["memorii.bootstrap_local_english_rule"]
    profile_version: Literal[2]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


BOOTSTRAP_COORDINATE = BootstrapProfileCoordinate(
    schema_id="memorii.semantic_ingestion.bootstrap_profile_coordinate",
    schema_version=2,
    profile_id="memorii.bootstrap_local_english_rule",
    profile_version=2,
)
BootstrapArtifactCoordinate = BootstrapProfileCoordinate


class BootstrapFreeformAdmissionPolicy(BaseModel):
    """Installed V2 policy for admission before the unchanged V3 runtime."""

    schema_id: Literal["memorii.semantic_ingestion.bootstrap_freeform_admission_policy"]
    schema_version: Literal[1]
    bootstrap_coordinate: BootstrapProfileCoordinate
    policy_version: Literal[1]
    declared_language: Literal["en"]
    required_language_evidence: Literal["authenticated_host_declaration"]
    max_segment_unicode_scalars: int = Field(ge=1, le=4096)
    max_segment_utf8_bytes: int = Field(ge=1, le=16384)
    max_child_segments: int = Field(ge=1, le=16)
    allowed_unicode_normalization: Literal["NFC"]
    prohibited_residue_classes: tuple[Literal["control", "private_use", "unpaired_surrogate"], ...]
    require_nonempty_visible_text: Literal[True]
    policy_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_policy(self) -> BootstrapFreeformAdmissionPolicy:
        if self.prohibited_residue_classes != tuple(sorted(set(self.prohibited_residue_classes))):
            raise ValueError("freeform policy residue classes must be ordered and unique")
        if self.policy_digest != _content_digest(self, "policy_digest"):
            raise ValueError("freeform admission policy digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> BootstrapFreeformAdmissionPolicy:
        body = cls.model_construct(
            **values, policy_digest="0" * 64
        ).model_dump(mode="python", exclude={"policy_digest"})
        return cls(
            **values,
            policy_digest=sha256(encode_typed_value(body)).hexdigest(),
        )


class BootstrapTrustRootProvider(Protocol):
    """Host/OS trust capability for the installed Bootstrap V3 release."""

    def verify_active_release(self, metadata: object) -> bool: ...


class HostVerifiedBootstrapReleaseEvidence(BaseModel):
    """Host-only proof of the active Bootstrap V3 release."""

    coordinate: BootstrapProfileCoordinate
    signed_release_digest: str = _DIGEST
    bootstrap_anchor_digest: str = _DIGEST
    external_root_digest: str = _DIGEST
    active_lifecycle_snapshot_digest: str = _DIGEST
    lifecycle_state: Literal["active"]
    # ``local_level2`` is an installation-bound authorization mode for the
    # same current Bootstrap V3 release.  It is not another profile family.
    trust_domain: Literal["production", "local_level2", "scenario_test"]
    verified_at: datetime
    evidence_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_evidence(self) -> HostVerifiedBootstrapReleaseEvidence:
        if self.verified_at.utcoffset() is None:
            raise ValueError("bootstrap release evidence time must be timezone-aware")
        if self.evidence_digest != _domain_digest(
            b"memorii.semantic_ingestion.host_verified_bootstrap_release_evidence.v1",
            self.model_dump(mode="python", exclude={"evidence_digest"}),
        ):
            raise ValueError("bootstrap release evidence digest mismatch")
        return self


class CurrentBootstrapReleaseAssertion(BaseModel):
    """Ephemeral use-time proof; callers must never serialize this value."""

    coordinate: BootstrapProfileCoordinate
    signed_release_digest: str = _DIGEST
    bootstrap_anchor_digest: str = _DIGEST
    active_lifecycle_snapshot_digest: str = _DIGEST
    assertion_phase: Literal["prepared_publication", "pre_handoff_retry", "writer_handoff"]
    assertion_nonce: str = Field(min_length=1)
    assertion_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_assertion(self) -> CurrentBootstrapReleaseAssertion:
        if self.assertion_digest != _domain_digest(
            b"memorii.semantic_ingestion.current_bootstrap_release_assertion.v1",
            self.model_dump(mode="python", exclude={"assertion_digest"}),
        ):
            raise ValueError("bootstrap release assertion digest mismatch")
        return self


class CurrentBootstrapReleaseVerifier(Protocol):
    """Host-owned current-release authority.

    ``assert_current`` is invoked from the memory-plane transaction
    precondition at every state-changing bootstrap write.  Hosts must
    linearize that call with their release revocation state; the assertion is
    deliberately ephemeral and is never persisted as a substitute for that
    live check.
    """

    def assert_current(
        self,
        *,
        authorization: object,
        release_evidence: HostVerifiedBootstrapReleaseEvidence,
        assertion_phase: Literal["prepared_publication", "pre_handoff_retry", "writer_handoff"],
    ) -> CurrentBootstrapReleaseAssertion: ...


class _AuthenticatedLanguageEvidenceCreateValues(TypedDict):
    source_id: str
    source_digest: str
    original_text_digest: str
    delivery_principal_binding_digest: str
    segment_governance_set_digest: str
    governance_carrier_artifact_digest: str
    segment_governance_carriers_digest: str
    message_admission_carriers_digest: str
    language_declaration: str | None
    language_evidence_kind: Literal["authenticated_host_declaration", "missing", "untrusted", "mismatched"]
    language_evidence_trust: Literal["trusted", "missing", "untrusted", "mismatched"]
    language_governance_agreement: Literal["agrees", "missing", "disagrees"]


class BootstrapAuthenticatedLanguageEvidence(BaseModel):
    """Immutable Step-1 proof; current session authority is deliberately absent."""

    source_id: str = Field(min_length=1)
    source_digest: str = _DIGEST
    original_text_digest: str = _DIGEST
    delivery_principal_binding_digest: str = _DIGEST
    segment_governance_set_digest: str = _DIGEST
    governance_carrier_artifact_digest: str = _DIGEST
    segment_governance_carriers_digest: str = _DIGEST
    message_admission_carriers_digest: str = _DIGEST
    language_declaration: str | None
    language_evidence_kind: Literal["authenticated_host_declaration", "missing", "untrusted", "mismatched"]
    language_evidence_trust: Literal["trusted", "missing", "untrusted", "mismatched"]
    language_governance_agreement: Literal["agrees", "missing", "disagrees"]
    evidence_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_evidence(self) -> BootstrapAuthenticatedLanguageEvidence:
        body = self.model_dump(mode="python", exclude={"evidence_digest"})
        if self.evidence_digest != _domain_digest(
            b"memorii.semantic_ingestion.bootstrap_authenticated_language_evidence.v1", body
        ):
            raise ValueError("bootstrap language evidence digest mismatch")
        return self

    @classmethod
    def create(
        cls, **body: Unpack[_AuthenticatedLanguageEvidenceCreateValues]
    ) -> BootstrapAuthenticatedLanguageEvidence:
        return cls(
            **body,
            evidence_digest=_domain_digest(
                b"memorii.semantic_ingestion.bootstrap_authenticated_language_evidence.v1", body
            ),
        )


class BootstrapLanguageEvidence(Protocol):
    """Read-only language evidence shared by ingress and sealed Step-1 state."""

    language_declaration: str | None
    language_evidence_kind: str
    language_evidence_trust: str
    language_governance_agreement: str


class _AdmissionPinCreateValues(TypedDict):
    coordinate: BootstrapProfileCoordinate
    profile_digest: str
    release_evidence_digest: str
    bootstrap_language_evidence_digest: str
    source_id: str
    source_digest: str
    operation_fence_binding_digest: str


class BootstrapAdmissionPin(BaseModel):
    """Persisted Bootstrap V3 authority selected at admission."""

    coordinate: BootstrapProfileCoordinate
    profile_digest: str = _DIGEST
    release_evidence_digest: str = _DIGEST
    bootstrap_language_evidence_digest: str = _DIGEST
    source_id: str = Field(min_length=1)
    source_digest: str = _DIGEST
    operation_fence_binding_digest: str = _DIGEST
    pin_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_pin(self) -> BootstrapAdmissionPin:
        body = self.model_dump(mode="python", exclude={"pin_digest"})
        if self.pin_digest != _domain_digest(
            b"memorii.semantic_ingestion.bootstrap_admission_pin.v1", body
        ):
            raise ValueError("bootstrap admission pin digest mismatch")
        return self

    @classmethod
    def create(cls, **body: Unpack[_AdmissionPinCreateValues]) -> BootstrapAdmissionPin:
        digest_body = cls.model_construct(
            **body, pin_digest="0" * 64
        ).model_dump(mode="python", exclude={"pin_digest"})
        return cls(
            **body,
            pin_digest=_domain_digest(
                b"memorii.semantic_ingestion.bootstrap_admission_pin.v1",
                digest_body,
            ),
        )


@dataclass(frozen=True)
class HostVerifiedBootstrapMaterial:
    """Atomic host-verified Bootstrap V3 release material."""

    artifact_payloads: BootstrapProfileArtifactPayloads
    release_evidence: HostVerifiedBootstrapReleaseEvidence
    authenticated_ingress_resolver: object
    profile_enabled: bool
    trust_domain: Literal["production", "local_level2", "scenario_test"] = "production"


@dataclass(frozen=True)
class HostBootstrapMaterialPresentation:
    """Opaque host presentation awaiting external trust-domain verification.

    This is deliberately separate from the local runtime capability: a
    capability can carry release bytes, but it cannot authenticate those bytes
    for the provider composition root.
    """

    material: HostVerifiedBootstrapMaterial
    authentication_proof: object


class HostBootstrapMaterialVerifier(Protocol):
    """Host-owned verifier for release root, lifecycle, and trust domain."""

    def verify(
        self,
        *,
        presentation: HostBootstrapMaterialPresentation,
        required_trust_domain: Literal["production", "local_level2", "scenario_test"],
        server_time: datetime,
    ) -> HostVerifiedBootstrapMaterial | None: ...


class HostSemanticIngestionCapability(Protocol):
    """Opaque host boundary; core cannot read bundled authority before verification."""

    def load_bootstrap_material_presentation(self) -> HostBootstrapMaterialPresentation | None: ...

HostBootstrapCapability = HostSemanticIngestionCapability


class HostBootstrapCapabilityProvider(Protocol):
    def load(self) -> HostBootstrapCapability | None: ...


class InstalledHostBootstrapCapabilityProvider:
    """Discover the single host-installed capability without user configuration."""

    ENTRY_POINT_GROUP = "memorii.semantic_ingestion.host_capability"

    def load(self) -> HostBootstrapCapability | None:
        installed = tuple(entry_points(group=self.ENTRY_POINT_GROUP))
        if not installed:
            return None
        if len(installed) != 1:
            raise RuntimeError("multiple installed semantic-ingestion host capabilities")
        loaded = installed[0].load()
        value = loaded() if isinstance(loaded, type) else loaded
        if hasattr(value, "load"):
            value = value.load()
        return cast(HostBootstrapCapability | None, value)


class BootstrapProfileArtifactPayloads(BaseModel):
    """Exact CTV envelopes for the installed Bootstrap V3 artifact family."""

    profile_manifest: bytes
    grammar_capability_manifest: bytes
    freeform_admission_policy: bytes

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def bootstrap_artifact_binding(
    schema_id: str, *, schema_version: int
) -> CanonicalTypedValueProfileBinding:
    try:
        binding_digest = _BOOTSTRAP_ARTIFACT_BINDING_DIGESTS[(schema_id, schema_version)]
    except KeyError as exc:
        raise ValueError("unknown Bootstrap V3 artifact schema") from exc
    return CanonicalTypedValueProfileBinding(
        profile_id=_CTV_PROFILE_ID,
        profile_version=_CTV_PROFILE_VERSION,
        profile_digest=_CTV_PROFILE_DIGEST,
        schema_id=schema_id,
        schema_version=schema_version,
        binding_digest=binding_digest,
    )


def serialize_bootstrap_profile_artifacts(
    artifacts: BootstrapProfileArtifacts,
) -> BootstrapProfileArtifactPayloads:
    return BootstrapProfileArtifactPayloads(
        profile_manifest=serialize_artifact(
            artifacts.profile_manifest.model_dump(mode="python"),
            bootstrap_artifact_binding(
                artifacts.profile_manifest.schema_id,
                schema_version=artifacts.profile_manifest.schema_version,
            ),
        ),
        grammar_capability_manifest=serialize_artifact(
            artifacts.grammar_capability_manifest.model_dump(mode="python"),
            bootstrap_artifact_binding(
                artifacts.grammar_capability_manifest.schema_id,
                schema_version=artifacts.grammar_capability_manifest.schema_version,
            ),
        ),
        freeform_admission_policy=serialize_artifact(
            artifacts.freeform_admission_policy.model_dump(mode="python"),
            bootstrap_artifact_binding(
                artifacts.freeform_admission_policy.schema_id,
                schema_version=artifacts.freeform_admission_policy.schema_version,
            ),
        ),
    )


class BootstrapGrammarCapabilityManifest(BaseModel):
    schema_id: Literal["memorii.semantic_ingestion.bootstrap_grammar_capability_manifest"]
    schema_version: Literal[2]
    coordinate: BootstrapProfileCoordinate
    freeform_admission_policy_digest: str = _DIGEST
    manifest_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_digest(self) -> BootstrapGrammarCapabilityManifest:
        if self.manifest_digest != _content_digest(self, "manifest_digest"):
            raise ValueError("bootstrap grammar capability manifest digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> BootstrapGrammarCapabilityManifest:
        body = cls.model_construct(
            **values, manifest_digest="0" * 64
        ).model_dump(mode="python", exclude={"manifest_digest"})
        return cls(**values, manifest_digest=sha256(encode_typed_value(body)).hexdigest())


class BootstrapLocalProfileManifest(BaseModel):
    schema_id: Literal["memorii.semantic_ingestion.bootstrap_local_profile_manifest"]
    schema_version: Literal[2]
    coordinate: BootstrapProfileCoordinate
    preparation_policy: TextPreparationPolicy
    freeform_admission_policy_digest: str = _DIGEST
    component_root_digest: str = _DIGEST
    profile_digest: str = _DIGEST
    network_capability: Literal["denied"]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_manifest(self) -> BootstrapLocalProfileManifest:
        if self.preparation_policy.supported_languages != ("en",):
            raise ValueError("bootstrap preparation policy must authorize only English")
        if self.profile_digest != _content_digest(self, "profile_digest"):
            raise ValueError("bootstrap profile digest mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> BootstrapLocalProfileManifest:
        body = cls.model_construct(
            **values, profile_digest="0" * 64
        ).model_dump(mode="python", exclude={"profile_digest"})
        return cls(**values, profile_digest=sha256(encode_typed_value(body)).hexdigest())


class BootstrapProfileArtifacts(BaseModel):
    profile_manifest: BootstrapLocalProfileManifest
    grammar_capability_manifest: BootstrapGrammarCapabilityManifest
    freeform_admission_policy: BootstrapFreeformAdmissionPolicy

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_artifacts(self) -> BootstrapProfileArtifacts:
        if not (
            self.profile_manifest.coordinate
            == self.grammar_capability_manifest.coordinate
            == self.freeform_admission_policy.bootstrap_coordinate
            == BOOTSTRAP_COORDINATE
            and self.profile_manifest.freeform_admission_policy_digest
            == self.freeform_admission_policy.policy_digest
            and self.grammar_capability_manifest.freeform_admission_policy_digest
            == self.freeform_admission_policy.policy_digest
        ):
            raise ValueError("bootstrap artifacts are substituted")
        return self


class VerifiedBootstrapProfile(BaseModel):
    coordinate: BootstrapProfileCoordinate
    enabled: bool
    artifacts: BootstrapProfileArtifacts
    selection_digest: str = _DIGEST
    verification_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_profile(self) -> VerifiedBootstrapProfile:
        if self.coordinate != BOOTSTRAP_COORDINATE or self.artifacts.profile_manifest.coordinate != self.coordinate:
            raise ValueError("verified bootstrap profile coordinate is substituted")
        return self


def verify_bootstrap_profile(material: HostVerifiedBootstrapMaterial) -> VerifiedBootstrapProfile:
    """Verify only the installed Bootstrap V3 release artifacts."""

    evidence = material.release_evidence
    if (
        evidence.coordinate != BOOTSTRAP_COORDINATE
        or evidence.lifecycle_state != "active"
        or evidence.trust_domain != material.trust_domain
    ):
        raise BootstrapProfileVerificationError(BootstrapUnavailableReason.INVALID_MANIFEST)
    profile = BootstrapProfileReleaseVerifier.verify(
        payloads=material.artifact_payloads, enabled=material.profile_enabled
    )
    if evidence.signed_release_digest != profile.verification_digest:
        raise BootstrapProfileVerificationError(BootstrapUnavailableReason.ALTERED_MANIFEST)
    return profile


class GovernedSourceAdmissionFact(BaseModel):
    source_id: str
    source_digest: str = _DIGEST
    delivery_principal_binding_digest: str = _DIGEST
    delivery_key_digest: str = _DIGEST
    required_scope_set_digest: str = _DIGEST
    admission_index_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)


class BootstrapOutcomeBase(BaseModel):
    coordinate: BootstrapProfileCoordinate
    source_admission: GovernedSourceAdmissionFact

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProfileSelectedPipelinePending(BootstrapOutcomeBase):
    kind: Literal["selected_pipeline_pending"]
    selection_digest: str = _DIGEST
    verification_digest: str = _DIGEST


class ProfileDisabled(BootstrapOutcomeBase):
    kind: Literal["disabled"]
    disable_reason: Literal["operator_disabled"]


class BootstrapUnavailableReason(StrEnum):
    INVALID_MANIFEST = "invalid_manifest"
    ALTERED_MANIFEST = "altered_manifest"
    MISSING_MANIFEST = "missing_manifest"
    MISSING_COMPONENT = "missing_component"
    ALTERED_COMPONENT = "altered_component"
    INVALID_CORPUS = "invalid_corpus"
    INVALID_CONFIG = "invalid_config"


class BootstrapProfileVerificationError(ValueError):
    def __init__(self, reason: BootstrapUnavailableReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class ProfileUnavailable(BootstrapOutcomeBase):
    kind: Literal["unavailable"]
    reason: BootstrapUnavailableReason


class ProfileInputOutcome(BootstrapOutcomeBase):
    kind: Literal["unsupported_input", "abstained"]
    reason: Literal["missing_language_declaration", "untrusted_language", "language_mismatch", "non_english_language", "mixed_residue", "unsupported_grammar", "extractor_abstained"]
    input_normalized_digest: str = _DIGEST
    matched_corpus_case_id: str | None = None


class ProfileAcceptedCandidate(BootstrapOutcomeBase):
    kind: Literal["accepted_candidate"]
    candidate_digest: str = _DIGEST
    operation_fence_binding_digest: str = _DIGEST


class ProfileCommittedTerminal(BootstrapOutcomeBase):
    kind: Literal["committed_terminal"]
    terminal_result_digest: str = _DIGEST
    operation_fence_binding_digest: str = _DIGEST


BootstrapProfileOutcome = Annotated[
    ProfileSelectedPipelinePending | ProfileDisabled | ProfileUnavailable | ProfileInputOutcome
    | ProfileAcceptedCandidate | ProfileCommittedTerminal,
    Field(discriminator="kind"),
]


def normalized_input_digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def classify_bootstrap_input(
    *,
    profile: VerifiedBootstrapProfile,
    ingress: BootstrapLanguageEvidence,
    normalized_segment: bytes,
) -> tuple[str, str | None, str | None]:
    """Classify a segment using the installed free-form policy only."""

    if not profile.enabled:
        return "disabled", "operator_disabled", None
    evidence = (
        ingress.language_evidence_kind,
        ingress.language_evidence_trust,
        ingress.language_governance_agreement,
        ingress.language_declaration,
    )
    return _classify_freeform(
        policy=profile.artifacts.freeform_admission_policy,
        evidence=evidence,
        raw_segment=normalized_segment,
    )


def _classify_freeform(
    *,
    policy: BootstrapFreeformAdmissionPolicy,
    evidence: tuple[object, object, object, object],
    raw_segment: bytes,
) -> tuple[str, str | None, str | None]:
    """Validate policy-owned raw text without a language detector or corpus scan."""

    if evidence == ("missing", "missing", "missing", None):
        return "abstained", "missing_language_declaration", None
    if evidence == ("untrusted", "untrusted", "missing", None):
        return "abstained", "untrusted_language", None
    if evidence == ("mismatched", "mismatched", "disagrees", "en"):
        return "abstained", "language_mismatch", None
    if evidence[:3] == ("authenticated_host_declaration", "trusted", "agrees") and evidence[3] != "en":
        return "abstained", "non_english_language", None
    if evidence != ("authenticated_host_declaration", "trusted", "agrees", "en"):
        return "abstained", "untrusted_language", None
    try:
        text = raw_segment.decode("utf-8")
    except UnicodeDecodeError:
        return "unsupported_input", "prohibited_residue", None
    if not text or (policy.require_nonempty_visible_text and not any(not char.isspace() for char in text)):
        return "unsupported_input", "empty_segment", None
    if unicodedata.normalize("NFC", text) != text:
        return "unsupported_input", "normalization_mismatch", None
    if len(text) > policy.max_segment_unicode_scalars or len(raw_segment) > policy.max_segment_utf8_bytes:
        return "unsupported_input", "segment_limit", None
    for char in text:
        category = unicodedata.category(char)
        if (
            ("control" in policy.prohibited_residue_classes and category == "Cc")
            or ("private_use" in policy.prohibited_residue_classes and category == "Co")
            or ("unpaired_surrogate" in policy.prohibited_residue_classes and category == "Cs")
        ):
            return "unsupported_input", "prohibited_residue", None
    return "selected_pipeline_pending", None, None


def _content_digest(model: BaseModel, digest_field: str) -> str:
    return sha256(encode_typed_value(model.model_dump(mode="python", exclude={digest_field}))).hexdigest()


def _domain_digest(domain: bytes, value: object) -> str:
    """Hash a closed CTV body under its named, non-interchangeable domain."""

    return sha256(domain + b"\0" + encode_typed_value(value)).hexdigest()


def build_bootstrap_profile(
    *,
    policy: BootstrapFreeformAdmissionPolicy,
    enabled: bool = True,
) -> VerifiedBootstrapProfile:
    """Build the one current profile from installed free-form policy material."""

    if policy.bootstrap_coordinate != BOOTSTRAP_COORDINATE:
        raise ValueError("policy has the wrong bootstrap coordinate")
    TextPreparationPolicy = _bootstrap_manifest_model()
    preparation_policy = TextPreparationPolicy.create(
        max_segment_characters=policy.max_segment_unicode_scalars,
        supported_languages=(policy.declared_language,),
        segmentation_algorithm="memorii.semantic-ingestion.safe-sentence-first-paragraph-bounded.v1",
        context_window_algorithm="memorii.semantic-ingestion.owned-partition-whole-boundary-context.v1",
    )
    component_root_digest = sha256(
        b"memorii.bootstrap-current-freeform-components.v1\0"
        + Path(__file__).read_bytes()
    ).hexdigest()
    grammar = BootstrapGrammarCapabilityManifest.create(
        schema_id="memorii.semantic_ingestion.bootstrap_grammar_capability_manifest",
        schema_version=2,
        coordinate=BOOTSTRAP_COORDINATE,
        freeform_admission_policy_digest=policy.policy_digest,
    )
    manifest = BootstrapLocalProfileManifest.create(
        schema_id="memorii.semantic_ingestion.bootstrap_local_profile_manifest",
        schema_version=2,
        coordinate=BOOTSTRAP_COORDINATE,
        preparation_policy=preparation_policy,
        freeform_admission_policy_digest=policy.policy_digest,
        component_root_digest=component_root_digest,
        network_capability="denied",
    )
    artifacts = BootstrapProfileArtifacts(
        profile_manifest=manifest,
        grammar_capability_manifest=grammar,
        freeform_admission_policy=policy,
    )
    selection_body = {"coordinate": BOOTSTRAP_COORDINATE.model_dump(mode="python"), "enabled": enabled}
    verification_body = {
        "profile": manifest.profile_digest,
        "grammar": grammar.manifest_digest,
        "policy": policy.policy_digest,
    }
    return VerifiedBootstrapProfile(
        coordinate=BOOTSTRAP_COORDINATE,
        enabled=enabled,
        artifacts=artifacts,
        selection_digest=sha256(encode_typed_value(selection_body)).hexdigest(),
        verification_digest=sha256(encode_typed_value(verification_body)).hexdigest(),
    )


@dataclass(frozen=True)
class BootstrapProfileReleaseMaterial:
    """Release-tool output consumed by the matching current verifier."""

    artifacts: BootstrapProfileArtifacts
    payloads: BootstrapProfileArtifactPayloads


class BootstrapProfileReleaseBuilder:
    """Build the one release family from the installed policy resource."""

    _POLICY_RESOURCE = "bootstrap_freeform_admission_policy.json"

    @classmethod
    def build(cls, *, enabled: bool = True) -> BootstrapProfileReleaseMaterial:
        policy = cls.load_installed_policy()
        verified = build_bootstrap_profile(policy=policy, enabled=enabled)
        return BootstrapProfileReleaseMaterial(
            artifacts=verified.artifacts,
            payloads=serialize_bootstrap_profile_artifacts(verified.artifacts),
        )

    @classmethod
    def load_installed_policy(cls) -> BootstrapFreeformAdmissionPolicy:
        """Decode strict package JSON and recompute its declared digest."""

        import json

        raw = files("memorii.core.memory_evolution").joinpath(
            "resources", cls._POLICY_RESOURCE
        ).read_bytes()
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapProfileVerificationError(
                BootstrapUnavailableReason.INVALID_CONFIG
            ) from exc
        if not isinstance(value, dict):
            raise BootstrapProfileVerificationError(BootstrapUnavailableReason.INVALID_CONFIG)
        residues = value.get("prohibited_residue_classes")
        if isinstance(residues, list):
            # JSON has no tuple, while the persisted policy contract does.
            # Conversion is limited to this one declared JSON-array field;
            # every other field remains strict and closed.
            value["prohibited_residue_classes"] = tuple(residues)
        return BootstrapFreeformAdmissionPolicy.model_validate(value)


class BootstrapProfileReleaseVerifier:
    """Decode only the complete installed current-release artifact family."""

    @staticmethod
    def verify(
        *, payloads: BootstrapProfileArtifactPayloads, enabled: bool = True
    ) -> VerifiedBootstrapProfile:
        _bootstrap_manifest_model()

        def decode(raw: bytes, model: type[BaseModel], schema_id: str, schema_version: int) -> BaseModel:
            decoded = decode_artifact(
                raw,
            expected_binding=bootstrap_artifact_binding(
                    schema_id, schema_version=schema_version
                ),
            )
            return TypeAdapter(model).validate_python(
                decode_typed_value(decoded.canonical_value_bytes)
            )

        try:
            profile = decode(
                payloads.profile_manifest,
                BootstrapLocalProfileManifest,
                "memorii.semantic_ingestion.bootstrap_local_profile_manifest",
                2,
            )
            grammar = decode(
                payloads.grammar_capability_manifest,
                BootstrapGrammarCapabilityManifest,
                "memorii.semantic_ingestion.bootstrap_grammar_capability_manifest",
                2,
            )
            policy = decode(
                payloads.freeform_admission_policy,
                BootstrapFreeformAdmissionPolicy,
                "memorii.semantic_ingestion.bootstrap_freeform_admission_policy",
                1,
            )
            artifacts = BootstrapProfileArtifacts(
                profile_manifest=cast(BootstrapLocalProfileManifest, profile),
                grammar_capability_manifest=cast(BootstrapGrammarCapabilityManifest, grammar),
                freeform_admission_policy=cast(BootstrapFreeformAdmissionPolicy, policy),
            )
        except (ValueError, TypeError) as exc:
            raise BootstrapProfileVerificationError(
                BootstrapUnavailableReason.INVALID_MANIFEST
            ) from exc

        selection_body = {
            "coordinate": BOOTSTRAP_COORDINATE.model_dump(mode="python"),
            "enabled": enabled,
        }
        verification_body = {
            "profile": artifacts.profile_manifest.profile_digest,
            "grammar": artifacts.grammar_capability_manifest.manifest_digest,
            "policy": artifacts.freeform_admission_policy.policy_digest,
        }
        return VerifiedBootstrapProfile(
            coordinate=BOOTSTRAP_COORDINATE,
            enabled=enabled,
            artifacts=artifacts,
            selection_digest=sha256(encode_typed_value(selection_body)).hexdigest(),
            verification_digest=sha256(encode_typed_value(verification_body)).hexdigest(),
        )


def _bootstrap_manifest_model():
    """Resolve the preparation contract only after package initialization.

    ``memory_evolution`` is imported by semantic-ingestion package setup, so an
    eager contract import would make bootstrap verification circular.
    """

    from memorii.core.semantic_ingestion.contracts import TextPreparationPolicy

    BootstrapLocalProfileManifest.model_rebuild(
        _types_namespace={"TextPreparationPolicy": TextPreparationPolicy}
    )
    return TextPreparationPolicy

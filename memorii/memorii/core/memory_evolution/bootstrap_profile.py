"""Closed, source-only M1 bootstrap profile contracts.

Operational trust roots are deliberately supplied by the host boundary; this
module contains no root, credential, network client, or M2 resource state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from importlib import import_module
from importlib.metadata import PackageNotFoundError, entry_points, packages_distributions, version
from importlib.util import find_spec
from pathlib import Path
from typing import Annotated, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    CanonicalTypedValueProfileBinding,
    decode_artifact,
    decode_typed_value,
    encode_typed_value,
    serialize_artifact,
)

_DIGEST = Field(pattern=r"^[0-9a-f]{64}$")
_CTV_PROFILE_ID = "semantic_ingestion_typed_value"
_CTV_PROFILE_VERSION = 2
_CTV_PROFILE_DIGEST = "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f"
_BOOTSTRAP_ARTIFACT_BINDING_DIGESTS = {
    "memorii.semantic_ingestion.bootstrap_local_profile_manifest":
        "0136ac668b2cb67e9b3e4740da0299e757492707de47f079003ae2259173e87d",
    "memorii.semantic_ingestion.bootstrap_grammar_capability_manifest":
        "80a0adf476264036eca1e604596871a7abbf05e634f1b0fbac4421aa516d0121",
    "memorii.semantic_ingestion.bootstrap_grammar_corpus":
        "d69cd728deefa7e7c0b93a9d8422b1cb865c3b168d92f5246848796d71bd4c5e",
}


class BootstrapProfileCoordinate(BaseModel):
    profile_id: Literal["memorii.bootstrap_local_english_rule"]
    profile_version: Literal[1]

    model_config = ConfigDict(extra="forbid", frozen=True)


BOOTSTRAP_COORDINATE = BootstrapProfileCoordinate(
    profile_id="memorii.bootstrap_local_english_rule", profile_version=1
)


class BootstrapProfileTrustAnchor(BaseModel):
    schema_id: Literal["memorii.semantic_ingestion.bootstrap_profile_trust_anchor"] = "memorii.semantic_ingestion.bootstrap_profile_trust_anchor"
    schema_version: Literal[1] = 1
    coordinate: BootstrapProfileCoordinate
    profile_manifest_digest: str = _DIGEST
    grammar_capability_manifest_digest: str = _DIGEST
    grammar_corpus_digest: str = _DIGEST
    component_root_digest: str = _DIGEST
    trust_anchor_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> BootstrapProfileTrustAnchor:
        if self.trust_anchor_digest != _content_digest(self, "trust_anchor_digest"):
            raise ValueError("bootstrap trust anchor digest mismatch")
        return self


class BootstrapProfileReleaseMetadata(BaseModel):
    coordinate: BootstrapProfileCoordinate
    bootstrap_profile_trust_anchor_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)


class BootstrapTrustRootProvider(Protocol):
    """Host/OS trust capability; production code must not implement this from package bytes."""

    def verify_active_release(self, metadata: BootstrapProfileReleaseMetadata) -> bool: ...


@dataclass(frozen=True)
class HostVerifiedBootstrapMaterial:
    """Atomic result returned only after the host verifies its external release root."""

    release_metadata: BootstrapProfileReleaseMetadata
    trust_anchor: BootstrapProfileTrustAnchor
    artifact_payloads: BootstrapProfileArtifactPayloads
    authenticated_ingress_resolver: object
    profile_enabled: bool


class HostSemanticIngestionCapability(Protocol):
    """Opaque host boundary; core cannot read bundled authority before verification."""

    def load_verified_bootstrap_material(self) -> HostVerifiedBootstrapMaterial | None: ...

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


def verify_bootstrap_release(
    *,
    provider: BootstrapTrustRootProvider | None,
    metadata: BootstrapProfileReleaseMetadata,
    anchor: BootstrapProfileTrustAnchor,
) -> bool:
    """Fail closed before any artifact/component construction."""

    return bool(
        provider is not None
        and metadata.coordinate == anchor.coordinate == BOOTSTRAP_COORDINATE
        and metadata.bootstrap_profile_trust_anchor_digest == anchor.trust_anchor_digest
        and provider.verify_active_release(metadata)
    )


class BootstrapGrammarCorpusCase(BaseModel):
    case_id: str
    declared_language: str | None
    language_evidence_kind: Literal["authenticated_host_declaration", "missing", "untrusted", "mismatched"]
    language_evidence_trust: Literal["trusted", "missing", "untrusted", "mismatched"]
    governance_agreement: Literal["agrees", "missing", "disagrees"]
    normalized_segment_bytes: bytes
    disposition: Literal["supported_form", "unsupported_form", "abstain_form"]
    expected_reason: Literal["missing_language_declaration", "untrusted_language", "language_mismatch", "non_english_language", "mixed_residue", "unsupported_grammar", "extractor_abstained"] | None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_disposition(self) -> BootstrapGrammarCorpusCase:
        en = (self.language_evidence_kind, self.language_evidence_trust, self.governance_agreement, self.declared_language)
        if self.disposition == "supported_form":
            valid = en == ("authenticated_host_declaration", "trusted", "agrees", "en") and self.expected_reason is None
        elif self.disposition == "unsupported_form":
            valid = en == ("authenticated_host_declaration", "trusted", "agrees", "en") and self.expected_reason in {"mixed_residue", "unsupported_grammar"}
        else:
            valid = (en, self.expected_reason) in {
                (("missing", "missing", "missing", None), "missing_language_declaration"),
                (("untrusted", "untrusted", "missing", None), "untrusted_language"),
                (("mismatched", "mismatched", "disagrees", "en"), "language_mismatch"),
                (("authenticated_host_declaration", "trusted", "agrees", "en"), "extractor_abstained"),
            } or (en[:3] == ("authenticated_host_declaration", "trusted", "agrees") and en[3] not in {None, "en"} and self.expected_reason == "non_english_language")
        if not valid:
            raise ValueError("invalid bootstrap grammar corpus tuple")
        return self


class BootstrapGrammarCorpus(BaseModel):
    schema_id: Literal["memorii.semantic_ingestion.bootstrap_grammar_corpus"]
    schema_version: Literal[1]
    coordinate: BootstrapProfileCoordinate
    cases: tuple[BootstrapGrammarCorpusCase, ...]
    corpus_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_corpus(self) -> BootstrapGrammarCorpus:
        ids = tuple(case.case_id for case in self.cases)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("bootstrap corpus cases must be ordered and unique")
        if {case.disposition for case in self.cases} != {
            "supported_form",
            "unsupported_form",
            "abstain_form",
        }:
            raise ValueError("bootstrap corpus disposition inventory is incomplete")
        required_reasons = {
            "missing_language_declaration",
            "untrusted_language",
            "language_mismatch",
            "non_english_language",
            "mixed_residue",
            "unsupported_grammar",
            "extractor_abstained",
        }
        if {case.expected_reason for case in self.cases if case.expected_reason is not None} != required_reasons:
            raise ValueError("bootstrap corpus reason inventory is incomplete")
        if self.corpus_digest != _content_digest(self, "corpus_digest"):
            raise ValueError("bootstrap corpus digest mismatch")
        return self


class BootstrapGrammarCapabilityManifest(BaseModel):
    schema_id: Literal["memorii.semantic_ingestion.bootstrap_grammar_capability_manifest"]
    schema_version: Literal[1]
    coordinate: BootstrapProfileCoordinate
    grammar_corpus_digest: str = _DIGEST
    manifest_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> BootstrapGrammarCapabilityManifest:
        if self.manifest_digest != _content_digest(self, "manifest_digest"):
            raise ValueError("grammar capability manifest digest mismatch")
        return self


class ComponentSymbolFingerprint(BaseModel):
    module_path: str
    qualified_symbol: str
    distribution_name: str | None = None
    distribution_version: str | None = None
    repository_blob_identity: str | None = None
    source_or_package_content_digest: str = _DIGEST
    fingerprint_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> ComponentSymbolFingerprint:
        if (self.distribution_name is None) != (self.distribution_version is None):
            raise ValueError("component distribution name and version must be paired")
        if self.distribution_name is None and self.repository_blob_identity is None:
            raise ValueError("component without distribution identity requires repository blob identity")
        if self.repository_blob_identity is not None and not self.repository_blob_identity:
            raise ValueError("component repository blob identity must be non-empty")
        if self.fingerprint_digest != _component_fingerprint_digest(self):
            raise ValueError("component fingerprint digest mismatch")
        return self


class BootstrapLocalProfileManifest(BaseModel):
    schema_id: Literal["memorii.semantic_ingestion.bootstrap_local_profile_manifest"]
    schema_version: Literal[1]
    coordinate: BootstrapProfileCoordinate
    extractor_symbol: Literal["memorii.core.memory_evolution.extraction.EnglishRuleMemoryExtractor"]
    compiler_symbol: Literal["memorii.core.memory_evolution.semantic_compilation.SemanticIngestionCompiler"]
    validator_symbol: Literal["memorii.core.memory_evolution.validation.MemoryEvolutionValidator"]
    service_symbol: Literal["memorii.core.memory_evolution.service.MemoryEvolutionService"]
    grammar_capability_manifest_digest: str = _DIGEST
    grammar_corpus_digest: str = _DIGEST
    component_root_digest: str = _DIGEST
    component_fingerprints: tuple[ComponentSymbolFingerprint, ...]
    profile_digest: str = _DIGEST
    network_capability: Literal["denied"]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_manifest(self) -> BootstrapLocalProfileManifest:
        keys = tuple((item.module_path, item.qualified_symbol) for item in self.component_fingerprints)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("component fingerprints must be ordered and unique")
        required_keys = (
            ("memorii.core.memory_evolution.extraction", "EnglishRuleMemoryExtractor"),
            ("memorii.core.memory_evolution.semantic_compilation", "SemanticIngestionCompiler"),
            ("memorii.core.memory_evolution.service", "MemoryEvolutionService"),
            ("memorii.core.memory_evolution.validation", "MemoryEvolutionValidator"),
        )
        if keys != required_keys:
            raise ValueError("bootstrap component inventory is incomplete or substituted")
        if self.component_root_digest != _component_root(self.coordinate, self.component_fingerprints):
            raise ValueError("component root digest mismatch")
        if self.profile_digest != _content_digest(self, "profile_digest"):
            raise ValueError("bootstrap profile digest mismatch")
        return self


class BootstrapProfileArtifacts(BaseModel):
    profile_manifest: BootstrapLocalProfileManifest
    grammar_capability_manifest: BootstrapGrammarCapabilityManifest
    grammar_corpus: BootstrapGrammarCorpus

    model_config = ConfigDict(extra="forbid", frozen=True)


class BootstrapProfileArtifactPayloads(BaseModel):
    profile_manifest: bytes
    grammar_capability_manifest: bytes
    grammar_corpus: bytes

    model_config = ConfigDict(extra="forbid", frozen=True)


def bootstrap_artifact_binding(schema_id: str) -> CanonicalTypedValueProfileBinding:
    """Return the frozen decoder coordinate for one bootstrap content artifact."""

    try:
        binding_digest = _BOOTSTRAP_ARTIFACT_BINDING_DIGESTS[schema_id]
    except KeyError as exc:
        raise ValueError("unknown bootstrap artifact schema") from exc
    return CanonicalTypedValueProfileBinding(
        profile_id=_CTV_PROFILE_ID,
        profile_version=_CTV_PROFILE_VERSION,
        profile_digest=_CTV_PROFILE_DIGEST,
        schema_id=schema_id,
        schema_version=1,
        binding_digest=binding_digest,
    )


def serialize_bootstrap_profile_artifacts(
    artifacts: BootstrapProfileArtifacts,
) -> BootstrapProfileArtifactPayloads:
    """Envelope release-tooling bodies under their exact frozen CTV bindings."""

    return BootstrapProfileArtifactPayloads(
        profile_manifest=serialize_artifact(
            artifacts.profile_manifest.model_dump(mode="python"),
            bootstrap_artifact_binding(artifacts.profile_manifest.schema_id),
        ),
        grammar_capability_manifest=serialize_artifact(
            artifacts.grammar_capability_manifest.model_dump(mode="python"),
            bootstrap_artifact_binding(artifacts.grammar_capability_manifest.schema_id),
        ),
        grammar_corpus=serialize_artifact(
            artifacts.grammar_corpus.model_dump(mode="python"),
            bootstrap_artifact_binding(artifacts.grammar_corpus.schema_id),
        ),
    )


class VerifiedBootstrapProfile(BaseModel):
    coordinate: BootstrapProfileCoordinate
    enabled: bool
    artifacts: BootstrapProfileArtifacts
    selection_digest: str = _DIGEST
    verification_digest: str = _DIGEST

    model_config = ConfigDict(extra="forbid", frozen=True)


def verify_bootstrap_profile(material: HostVerifiedBootstrapMaterial) -> VerifiedBootstrapProfile:
    """Verify the externally rooted release and complete local artifact graph."""

    anchor = material.trust_anchor
    metadata = material.release_metadata
    if not (
        metadata.coordinate == anchor.coordinate == BOOTSTRAP_COORDINATE
        and metadata.bootstrap_profile_trust_anchor_digest == anchor.trust_anchor_digest
    ):
        raise BootstrapProfileVerificationError(BootstrapUnavailableReason.INVALID_MANIFEST)
    payloads = material.artifact_payloads
    artifacts = BootstrapProfileArtifacts(
        profile_manifest=TypeAdapter(BootstrapLocalProfileManifest).validate_python(
            decode_typed_value(
                decode_artifact(
                    payloads.profile_manifest,
                    expected_binding=bootstrap_artifact_binding(
                        "memorii.semantic_ingestion.bootstrap_local_profile_manifest"
                    ),
                ).canonical_value_bytes
            )
        ),
        grammar_capability_manifest=TypeAdapter(BootstrapGrammarCapabilityManifest).validate_python(
            decode_typed_value(
                decode_artifact(
                    payloads.grammar_capability_manifest,
                    expected_binding=bootstrap_artifact_binding(
                        "memorii.semantic_ingestion.bootstrap_grammar_capability_manifest"
                    ),
                ).canonical_value_bytes
            )
        ),
        grammar_corpus=TypeAdapter(BootstrapGrammarCorpus).validate_python(
            decode_typed_value(
                decode_artifact(
                    payloads.grammar_corpus,
                    expected_binding=bootstrap_artifact_binding(
                        "memorii.semantic_ingestion.bootstrap_grammar_corpus"
                    ),
                ).canonical_value_bytes
            )
        ),
    )
    profile = artifacts.profile_manifest
    grammar = artifacts.grammar_capability_manifest
    corpus = artifacts.grammar_corpus
    if not (
        anchor.coordinate == profile.coordinate == grammar.coordinate == corpus.coordinate == BOOTSTRAP_COORDINATE
        and anchor.profile_manifest_digest == profile.profile_digest
        and anchor.grammar_capability_manifest_digest == grammar.manifest_digest
        and anchor.grammar_corpus_digest == corpus.corpus_digest
        and anchor.component_root_digest == profile.component_root_digest
        and profile.grammar_capability_manifest_digest == grammar.manifest_digest
        and profile.grammar_corpus_digest == grammar.grammar_corpus_digest == corpus.corpus_digest
    ):
        raise BootstrapProfileVerificationError(BootstrapUnavailableReason.ALTERED_MANIFEST)
    for fingerprint in profile.component_fingerprints:
        spec = find_spec(fingerprint.module_path)
        if spec is None or spec.origin is None:
            raise BootstrapProfileVerificationError(BootstrapUnavailableReason.MISSING_COMPONENT)
        try:
            component_bytes = Path(spec.origin).read_bytes()
        except OSError as exc:
            raise BootstrapProfileVerificationError(
                BootstrapUnavailableReason.MISSING_COMPONENT
            ) from exc
        if sha256(component_bytes).hexdigest() != fingerprint.source_or_package_content_digest:
            raise BootstrapProfileVerificationError(BootstrapUnavailableReason.ALTERED_COMPONENT)
        if fingerprint.distribution_name is not None:
            try:
                installed_version = version(fingerprint.distribution_name)
            except PackageNotFoundError as exc:
                raise BootstrapProfileVerificationError(BootstrapUnavailableReason.MISSING_COMPONENT) from exc
            if installed_version != fingerprint.distribution_version:
                raise BootstrapProfileVerificationError(BootstrapUnavailableReason.ALTERED_COMPONENT)
        try:
            symbol: object = import_module(fingerprint.module_path)
            for component in fingerprint.qualified_symbol.split("."):
                symbol = getattr(symbol, component)
            if symbol is None:
                raise AttributeError("bootstrap component symbol is null")
        except (AttributeError, ImportError) as exc:
            raise BootstrapProfileVerificationError(BootstrapUnavailableReason.MISSING_COMPONENT) from exc
    selection_digest = sha256(
        encode_typed_value(
            {"coordinate": BOOTSTRAP_COORDINATE.model_dump(mode="python"), "enabled": material.profile_enabled}
        )
    ).hexdigest()
    verification_digest = sha256(
        encode_typed_value(
            {
                "anchor": anchor.trust_anchor_digest,
                "profile": profile.profile_digest,
                "grammar": grammar.manifest_digest,
                "corpus": corpus.corpus_digest,
                "components": profile.component_root_digest,
            }
        )
    ).hexdigest()
    return VerifiedBootstrapProfile(
        coordinate=BOOTSTRAP_COORDINATE,
        enabled=material.profile_enabled,
        artifacts=artifacts,
        selection_digest=selection_digest,
        verification_digest=verification_digest,
    )


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


BootstrapProfileOutcome = Annotated[
    ProfileSelectedPipelinePending | ProfileDisabled | ProfileUnavailable | ProfileInputOutcome,
    Field(discriminator="kind"),
]


def normalized_input_digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def disposition_outcome(case: BootstrapGrammarCorpusCase) -> Literal["selected_pipeline_pending", "unsupported_input", "abstained"]:
    """Map grammar disposition to the only legal M1 semantic result."""

    if case.disposition == "supported_form":
        return "selected_pipeline_pending"
    if case.disposition == "unsupported_form":
        return "unsupported_input"
    return "abstained"


def classify_bootstrap_input(
    *,
    profile: VerifiedBootstrapProfile,
    ingress: AuthenticatedIngressContext,
    normalized_segment: bytes,
) -> tuple[str, str | None, str | None]:
    """Classify only authenticated evidence against the exact verified corpus."""

    if not profile.enabled:
        return "disabled", "operator_disabled", None
    evidence = (
        ingress.language_evidence_kind,
        ingress.language_evidence_trust,
        ingress.language_governance_agreement,
        ingress.language_declaration,
    )
    for case in profile.artifacts.grammar_corpus.cases:
        case_evidence = (
            case.language_evidence_kind,
            case.language_evidence_trust,
            case.governance_agreement,
            case.declared_language,
        )
        if case.normalized_segment_bytes == normalized_segment and case_evidence == evidence:
            return disposition_outcome(case), case.expected_reason, case.case_id
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
    return "unsupported_input", "unsupported_grammar", None


def _content_digest(model: BaseModel, digest_field: str) -> str:
    return sha256(encode_typed_value(model.model_dump(mode="python", exclude={digest_field}))).hexdigest()


def _component_root(
    coordinate: BootstrapProfileCoordinate,
    fingerprints: tuple[ComponentSymbolFingerprint, ...],
) -> str:
    return _domain_digest(
        b"memorii.semantic_ingestion.bootstrap_package_root.v1",
        {
            "coordinate": coordinate.model_dump(mode="python"),
            "fingerprint_digests": tuple(item.fingerprint_digest for item in fingerprints),
        },
    )


def _domain_digest(domain: bytes, value: object) -> str:
    """Hash a closed CTV body under its named, non-interchangeable domain."""

    return sha256(domain + b"\0" + encode_typed_value(value)).hexdigest()


def _component_fingerprint_digest(fingerprint: ComponentSymbolFingerprint) -> str:
    return _domain_digest(
        b"memorii.semantic_ingestion.bootstrap_component_fingerprint.v1",
        fingerprint.model_dump(mode="python", exclude={"fingerprint_digest"}),
    )


def _component_distribution_identity(module_path: str) -> tuple[str | None, str | None]:
    top_level = module_path.split(".", 1)[0]
    distributions = packages_distributions().get(top_level, ())
    if len(distributions) != 1:
        return None, None
    distribution_name = distributions[0]
    try:
        return distribution_name, version(distribution_name)
    except PackageNotFoundError:
        return None, None


def build_bootstrap_profile_artifacts(
    cases: tuple[BootstrapGrammarCorpusCase, ...],
) -> BootstrapProfileArtifacts:
    """Build content-addressed artifacts for release tooling and deterministic tests."""

    corpus_fields = {
        "schema_id": "memorii.semantic_ingestion.bootstrap_grammar_corpus",
        "schema_version": 1,
        "coordinate": BOOTSTRAP_COORDINATE.model_dump(mode="python"),
        "cases": tuple(case.model_dump(mode="python") for case in cases),
    }
    corpus = BootstrapGrammarCorpus(
        **corpus_fields,
        corpus_digest=sha256(encode_typed_value(corpus_fields)).hexdigest(),
    )
    grammar_fields = {
        "schema_id": "memorii.semantic_ingestion.bootstrap_grammar_capability_manifest",
        "schema_version": 1,
        "coordinate": BOOTSTRAP_COORDINATE.model_dump(mode="python"),
        "grammar_corpus_digest": corpus.corpus_digest,
    }
    grammar = BootstrapGrammarCapabilityManifest(
        **grammar_fields,
        manifest_digest=sha256(encode_typed_value(grammar_fields)).hexdigest(),
    )
    symbols = (
        ("memorii.core.memory_evolution.extraction", "EnglishRuleMemoryExtractor"),
        ("memorii.core.memory_evolution.semantic_compilation", "SemanticIngestionCompiler"),
        ("memorii.core.memory_evolution.service", "MemoryEvolutionService"),
        ("memorii.core.memory_evolution.validation", "MemoryEvolutionValidator"),
    )
    fingerprints: list[ComponentSymbolFingerprint] = []
    for module_path, qualified_symbol in symbols:
        spec = find_spec(module_path)
        if spec is None or spec.origin is None:
            raise ValueError("bootstrap component is missing")
        distribution_name, distribution_version = _component_distribution_identity(module_path)
        component_digest = sha256(Path(spec.origin).read_bytes()).hexdigest()
        fields = {
            "module_path": module_path,
            "qualified_symbol": qualified_symbol,
            "distribution_name": distribution_name,
            "distribution_version": distribution_version,
            # A source checkout has no installed distribution identity.  Its
            # exact module digest is the repository-owned blob identity.
            "repository_blob_identity": None if distribution_name is not None else component_digest,
            "source_or_package_content_digest": component_digest,
        }
        fingerprints.append(
            ComponentSymbolFingerprint(
                **fields,
                fingerprint_digest=_domain_digest(
                    b"memorii.semantic_ingestion.bootstrap_component_fingerprint.v1", fields
                ),
            )
        )
    ordered = tuple(fingerprints)
    component_root_digest = _component_root(BOOTSTRAP_COORDINATE, ordered)
    profile_fields = {
        "schema_id": "memorii.semantic_ingestion.bootstrap_local_profile_manifest",
        "schema_version": 1,
        "coordinate": BOOTSTRAP_COORDINATE.model_dump(mode="python"),
        "extractor_symbol": "memorii.core.memory_evolution.extraction.EnglishRuleMemoryExtractor",
        "compiler_symbol": "memorii.core.memory_evolution.semantic_compilation.SemanticIngestionCompiler",
        "validator_symbol": "memorii.core.memory_evolution.validation.MemoryEvolutionValidator",
        "service_symbol": "memorii.core.memory_evolution.service.MemoryEvolutionService",
        "grammar_capability_manifest_digest": grammar.manifest_digest,
        "grammar_corpus_digest": corpus.corpus_digest,
        "component_root_digest": component_root_digest,
        "component_fingerprints": tuple(item.model_dump(mode="python") for item in ordered),
        "network_capability": "denied",
    }
    profile = BootstrapLocalProfileManifest(
        **profile_fields,
        profile_digest=sha256(encode_typed_value(profile_fields)).hexdigest(),
    )
    return BootstrapProfileArtifacts(
        profile_manifest=profile,
        grammar_capability_manifest=grammar,
        grammar_corpus=corpus,
    )


def build_bootstrap_trust_anchor(artifacts: BootstrapProfileArtifacts) -> BootstrapProfileTrustAnchor:
    fields = {
        "schema_id": "memorii.semantic_ingestion.bootstrap_profile_trust_anchor",
        "schema_version": 1,
        "coordinate": BOOTSTRAP_COORDINATE.model_dump(mode="python"),
        "profile_manifest_digest": artifacts.profile_manifest.profile_digest,
        "grammar_capability_manifest_digest": artifacts.grammar_capability_manifest.manifest_digest,
        "grammar_corpus_digest": artifacts.grammar_corpus.corpus_digest,
        "component_root_digest": artifacts.profile_manifest.component_root_digest,
    }
    return BootstrapProfileTrustAnchor(
        **fields,
        trust_anchor_digest=sha256(encode_typed_value(fields)).hexdigest(),
    )

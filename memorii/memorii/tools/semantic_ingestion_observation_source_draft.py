"""Produce review-only profile-3 observation declaration drafts.

This is intentionally an authoring aid.  It reflects the reviewed Pydantic
models only to make a *raw, unpublished* draft and is not imported by a
compiler, registry, decoder, or runtime service.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from memorii.core.memory_evolution import (
    graph_effect_contracts as effects,
)
from memorii.core.memory_evolution import (
    graph_ingestion_observation_records as ingestion,
)
from memorii.core.memory_evolution import (
    graph_ingestion_time_contracts as times,
)
from memorii.core.memory_evolution import (
    graph_observation_contracts as legacy_observation,
)
from memorii.core.memory_evolution import (
    graph_observation_public_contracts as public,
)
from memorii.core.memory_evolution import (
    graph_observation_records as observed,
)
from memorii.core.memory_evolution import (
    graph_observation_snapshot_contracts as snapshots,
)
from memorii.core.memory_evolution import (
    graph_records,
    reference_integrity,
)
from memorii.core.memory_evolution import (
    observation_ledger_contracts as ledger,
)
from memorii.core.memory_evolution import (
    observation_replay_contracts as replay,
)
from memorii.core.semantic_ingestion import (
    bootstrap_graph_projection_publication as publication,
)
from memorii.core.semantic_ingestion import (
    contracts as ingestion_contracts,
)
from memorii.domain.enums import SourceModality

_OUTPUT_DIRECTORY = Path("docs/work/semantic_ingestion/registry-publication/source-draft")
_DRAFT_NAME = "observation-profile3-authoring-draft.json"

# This is deliberately a static, reviewed inventory.  Schema identifiers are
# the normative class names, never module-derived reflection identifiers.
ROOT_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("ObservationLedgerHead", ledger.ObservationLedgerHead),
    ("ObservationLedgerEntry", ledger.ObservationLedgerEntry),
    ("ObservationGroupSemanticPayload", ledger.ObservationGroupSemanticPayload),
    ("ObservationSourceSemanticPayload", ledger.ObservationSourceSemanticPayload),
    ("SourceObservationIntent", ledger.SourceObservationIntent),
    ("ObservationLedgerActivation", ledger.ObservationLedgerActivation),
    ("IngestionObservationDelta", effects.IngestionObservationDelta),
    ("SourceFinalizationObservationDelta", effects.SourceFinalizationObservationDelta),
    ("IngestionObservationRecordMutation", effects.IngestionObservationRecordMutation),
    ("CanonicalSourceIntroductionRecord", effects.CanonicalSourceIntroductionRecord),
    ("CanonicalOperationIntroductionRecord", effects.CanonicalOperationIntroductionRecord),
    ("CanonicalOperationTerminalOutcomeRecord", effects.CanonicalOperationTerminalOutcomeRecord),
    ("CanonicalSourceTerminalOutcomeRecord", effects.CanonicalSourceTerminalOutcomeRecord),
    ("GraphRevisionDelta", effects.GraphRevisionDelta),
    ("ReferenceEdgeLedgerEntry", reference_integrity.ReferenceEdgeLedgerEntry),
    ("GraphRecordMutation", effects.GraphRecordMutation),
    ("SnapshotGraphRecord", graph_records.SnapshotGraphRecord),
    ("SegmentGovernanceBinding", ingestion_contracts.SegmentGovernanceBinding),
    ("MessageAdmissionIdentity", ingestion_contracts.MessageAdmissionIdentity),
    ("GovernanceCarrierArtifact", ingestion_contracts.GovernanceCarrierArtifact),
    ("SegmentGovernanceCarrierSet", ingestion_contracts.SegmentGovernanceCarrierSet),
    ("MessageAdmissionCarrierSet", ingestion_contracts.MessageAdmissionCarrierSet),
    ("RequiredOutcomeScopeSet", ingestion_contracts.RequiredOutcomeScopeSet),
    ("SourceSpanReference", ingestion_contracts.SourceSpanReference),
    ("OperationTemporalDecisionBinding", ingestion_contracts.OperationTemporalDecisionBinding),
    ("BootstrapGraphNativeProjectionPublicationReceiptV3", publication.BootstrapGraphNativeProjectionPublicationReceiptV3),
    ("BootstrapGraphNativeReplayAuthorityEvidenceV3", publication.BootstrapGraphNativeReplayAuthorityEvidenceV3),
    ("BootstrapGraphNativeReplayCheckpointEvidenceV3", publication.BootstrapGraphNativeReplayCheckpointEvidenceV3),
    ("ObservationReplayState", replay.ObservationReplayState),
    ("IngestionObservationReplayCheckpoint", replay.IngestionObservationReplayCheckpoint),
    ("ObservationCheckpointLifecycle", replay.ObservationCheckpointLifecycle),
    ("ObservationCheckpointSigningPreimage", replay.ObservationCheckpointSigningPreimage),
    ("ObservationCheckpointPublicationReceipt", replay.ObservationCheckpointPublicationReceipt),
    ("ObservationCheckpointBundle", replay.ObservationCheckpointBundle),
    # The historical foundation owns only these two digest-free values here.
    ("GraphObservationCohortSelector", legacy_observation.GraphObservationCohortSelector),
    ("GraphObservationFailure", legacy_observation.GraphObservationFailure),
    ("AuthenticatedGraphObservationContext", public.AuthenticatedGraphObservationContext),
    ("GraphObservationAuthorizationDecision", public.GraphObservationAuthorizationDecision),
    ("GraphObservationPagePolicySnapshot", public.GraphObservationPagePolicySnapshot),
    ("GraphObservationRequestCoordinates", public.GraphObservationRequestCoordinates),
    ("IngestionTimeAttestationRequestCoordinates", public.IngestionTimeAttestationRequestCoordinates),
    ("GraphObservationRequest", public.GraphObservationRequest),
    ("IngestionTimeAttestationRequest", public.IngestionTimeAttestationRequest),
    ("GraphRecordObservationSnapshot", public.GraphRecordObservationSnapshot),
    ("IngestionTimeObservationSnapshot", public.IngestionTimeObservationSnapshot),
    ("GraphObservationPage", public.GraphObservationPage),
    ("IngestionTimeAttestationPage", public.IngestionTimeAttestationPage),
    ("GraphObservationRecordKey", snapshots.GraphObservationRecordKey),
    ("GraphObservationCohortPreimage", snapshots.GraphObservationCohortPreimage),
    ("ResolvedGraphObservationCohort", snapshots.ResolvedGraphObservationCohort),
    ("GraphObservationCursorPayload", snapshots.GraphObservationCursorPayload),
    ("SourceRetentionTimeAttestation", times.SourceRetentionTimeAttestation),
    ("TransactionGroupCommitTimeAttestation", times.TransactionGroupCommitTimeAttestation),
    ("ObservedEntityReference", observed.ObservedEntityReference),
    ("ObservedAssertionEntityReference", observed.ObservedAssertionEntityReference),
    ("ObservedEntityRevision", observed.ObservedEntityRevision),
    ("ObservedAliasRevision", observed.ObservedAliasRevision),
    ("ObservedTypeEvidence", observed.ObservedTypeEvidence),
    ("ObservedClaimAssertion", observed.ObservedClaimAssertion),
    ("ObservedTemporalClaimProjection", observed.ObservedTemporalClaimProjection),
    ("ObservedTrustClaimProjection", observed.ObservedTrustClaimProjection),
    ("ObservedRelation", observed.ObservedRelation),
    ("ObservedActionRoleBinding", observed.ObservedActionRoleBinding),
    ("ObservedActionRevision", observed.ObservedActionRevision),
    ("ObservedCitationRecord", observed.ObservedCitationRecord),
    ("ObservedProvenanceRecord", observed.ObservedProvenanceRecord),
    ("ObservedTemporalTransition", observed.ObservedTemporalTransition),
    ("ObservedCertifiedTextEffectiveTime", observed.ObservedCertifiedTextEffectiveTime),
    ("ObservedAuthenticatedReferenceEffectiveTime", observed.ObservedAuthenticatedReferenceEffectiveTime),
    ("ObservedSystemRecordedEffectiveTime", observed.ObservedSystemRecordedEffectiveTime),
    ("ObservedIdentityTransition", observed.ObservedIdentityTransition),
    ("ObservedReferenceDisposition", observed.ObservedReferenceDisposition),
    ("ObservedSourceIntroduction", ingestion.ObservedSourceIntroduction),
    ("ObservedOperationIntroduction", ingestion.ObservedOperationIntroduction),
    ("ObservedOperationTerminalOutcome", ingestion.ObservedOperationTerminalOutcome),
    ("ObservedSourceTerminalOutcome", ingestion.ObservedSourceTerminalOutcome),
    ("ObservedSourceOutcomeConsistencyAssessment", ingestion.ObservedSourceOutcomeConsistencyAssessment),
)

# Reviewed exception: the owner exposes BaseModel, while its canonical adapter
# names this exact finite record closure.  Never emit an open BaseModel payload.
_SNAPSHOT_PAYLOAD_MODELS: tuple[type[BaseModel], ...] = (
    graph_records.EntityRevision, graph_records.AliasRevision, graph_records.TypeEvidence,
    ingestion_contracts.ClaimAssertion, graph_records.ClaimProjection, graph_records.RelationRevision,
    ingestion_contracts.ActionRevision, graph_records.CitationRecord, graph_records.ProvenanceRecord,
    ingestion_contracts.TemporalTransitionRecord, ingestion_contracts.IdentityLineageRecord,
    graph_records.ReferenceDispositionRecord,
)

_SELF_DIGEST_FIELDS = {
    "ObservationLedgerHead": "head_digest", "ObservationLedgerEntry": "entry_digest",
    "SourceObservationIntent": "intent_digest", "ObservationLedgerActivation": "activation_digest",
    "ObservationReplayState": "state_digest", "ObservationCheckpointLifecycle": "authority_digest",
    "ObservationCheckpointPublicationReceipt": "receipt_digest", "ObservationCheckpointBundle": "bundle_digest",
    "AuthenticatedGraphObservationContext": "context_digest",
    "GraphObservationAuthorizationDecision": "decision_digest",
    "GraphObservationPagePolicySnapshot": "policy_digest",
    "ResolvedGraphObservationCohort": "cohort_digest", "GraphObservationPage": "page_digest",
    "IngestionTimeAttestationPage": "page_digest",
    "ObservedSourceOutcomeConsistencyAssessment": "assessment_digest",
    "BootstrapGraphNativeProjectionPublicationReceiptV3": "receipt_digest",
    "BootstrapGraphNativeReplayAuthorityEvidenceV3": "evidence_digest",
    "BootstrapGraphNativeReplayCheckpointEvidenceV3": "evidence_digest",
    "ObservedEntityRevision": "record_digest", "ObservedAliasRevision": "record_digest",
    "ObservedTypeEvidence": "record_digest", "ObservedClaimAssertion": "record_digest",
    "ObservedTemporalClaimProjection": "record_digest", "ObservedTrustClaimProjection": "record_digest",
    "ObservedRelation": "record_digest", "ObservedActionRevision": "record_digest",
    "ObservedCitationRecord": "record_digest", "ObservedProvenanceRecord": "record_digest",
    "ObservedTemporalTransition": "record_digest", "ObservedIdentityTransition": "record_digest",
    "ObservedReferenceDisposition": "record_digest", "ObservedSourceIntroduction": "record_digest",
    "ObservedOperationIntroduction": "record_digest", "ObservedOperationTerminalOutcome": "record_digest",
    "ObservedSourceTerminalOutcome": "record_digest",
    "SourceRetentionTimeAttestation": "attestation_digest",
    "TransactionGroupCommitTimeAttestation": "attestation_digest",
}
_NORMATIVE_DOMAINS = {
    "BootstrapGraphNativeProjectionPublicationReceiptV3": "memorii.bootstrap-graph.native-projection-publication-receipt.v3",
    "BootstrapGraphNativeReplayAuthorityEvidenceV3": "memorii.bootstrap-graph.native-projection-authority-evidence.v3",
    "BootstrapGraphNativeReplayCheckpointEvidenceV3": "memorii.bootstrap-graph.native-projection-checkpoint-evidence.v3",
}
_ORDINARY_ROOTS = frozenset({
    "GraphObservationCohortSelector", "GraphObservationFailure", "GraphObservationCohortPreimage",
    "GraphObservationRecordKey", "GraphObservationRequestCoordinates", "IngestionTimeAttestationRequestCoordinates",
    "GraphObservationRequest", "IngestionTimeAttestationRequest", "GraphRecordObservationSnapshot",
    "IngestionTimeObservationSnapshot", "ObservationCheckpointSigningPreimage", "ObservationGroupSemanticPayload",
    "ObservationSourceSemanticPayload", "IngestionObservationDelta", "SourceFinalizationObservationDelta",
    "IngestionObservationRecordMutation", "CanonicalSourceIntroductionRecord", "CanonicalOperationIntroductionRecord",
    "CanonicalOperationTerminalOutcomeRecord", "CanonicalSourceTerminalOutcomeRecord", "GraphRevisionDelta",
    "ReferenceEdgeLedgerEntry", "GraphRecordMutation", "SegmentGovernanceBinding", "MessageAdmissionIdentity",
    "GovernanceCarrierArtifact", "SegmentGovernanceCarrierSet", "MessageAdmissionCarrierSet", "RequiredOutcomeScopeSet",
    "SourceSpanReference", "OperationTemporalDecisionBinding",
    "EntityRevisionStreamRecord", "AliasRevisionStreamRecord", "TypeEvidenceStreamRecord", "ClaimAssertionStreamRecord",
    "TemporalClaimProjectionStreamRecord", "TrustClaimProjectionStreamRecord", "RelationStreamRecord", "ActionRevisionStreamRecord",
    "CitationStreamRecord", "ProvenanceStreamRecord", "TemporalTransitionStreamRecord", "IdentityTransitionStreamRecord",
    "ReferenceDispositionStreamRecord", "SourceIntroductionStreamRecord", "OperationIntroductionStreamRecord",
    "OperationTerminalOutcomeStreamRecord", "SourceTerminalOutcomeStreamRecord",
})
_REVIEWED_ORDINARY_TRANSITIVE = frozenset({
    "AcceptedClaimIdentity", "AcceptedTemporalEvidence", "ActionRevision", "ActiveTemporalProjectionPointer",
    "ActiveTrustProjectionPointer", "AliasRevision", "AuthenticatedDocumentTimeReference",
    "AuthenticatedEventTimeReference", "AuthenticatedSourceIntervalEvidence", "CanonicalEntityRevisionRef",
    "CanonicalSourceTerminalOutcomeCore", "CitationRecord", "ClaimAssertion", "ClaimProjection",
    "CommittedMemoryRecordSnapshot", "CompiledIdentityLineageTransition", "EntityRevision",
    "EnvelopeFieldTextArtifactMappingProof", "EventBatchLogPosition", "EventProvenance", "GroundedMentionRef",
    "IdentityLineageRecord", "ImmutableAssertionEntityRef", "LineageEntityIdentity", "LineageEvidenceReference",
    "LineageReferenceDisposition", "LineageReverseReference", "MemoryEventMetadata", "MemoryScope",
    "ObservationGroupResultLocator", "ObservationSourceResultLocator", "ObservedActionRoleBinding",
    "ObservedAssertionEntityReference", "ObservedAuthenticatedReferenceEffectiveTime",
    "ObservedCertifiedTextEffectiveTime", "ObservedEntityReference", "ObservedSystemRecordedEffectiveTime",
    "OperationTemporalAttachmentBinding", "PredicateStateRule", "PredicateTrustRule", "ProjectionEvidenceRecord",
    "ProjectionHistoryReplayBinding", "ProjectionTextSpan", "ProvenanceRecord", "ReferenceDispositionRecord",
    "ReferenceTarget", "RelationRevision", "RetainedSourceTextArtifact", "RetainedSourceTextSpan",
    "SegmentLocalTextArtifact", "SegmentLocalTextSpan", "SemanticAssertionKey", "SemanticClaimSlotKey",
    "SemanticClaimValueKey", "SemanticConflictReplayBinding", "SemanticEventBinding", "SemanticGraphDelta",
    "SemanticMaterializedMemoryRecord", "SemanticMemoryEvent", "SemanticMemoryEventBatch", "SemanticMemoryEventPayload",
    "SemanticProjectionTextArtifact", "SemanticReplayAuthorityAggregate", "SemanticReplayAuthorityMemberBinding",
    "SemanticReplayCheckpoint", "SemanticReplayCheckpointBundle", "SemanticReplayState", "SemanticTerminalBindingSet",
    "SnapshotGraphRecord", "SourceAuthority", "SourceAuthorityEvidence", "SourceSpan", "TemporalEvidenceCandidate",
    "TemporalEvidenceDecisionClosure", "TemporalPolicyMigrationCertificate", "TemporalProjectionCommitCertificate",
    "TemporalProjectionGeneration", "TemporalProjectionHistoryEntry", "TemporalProjectionPublication", "TemporalProjectionRecord",
    "TemporalTransitionRecord", "TimeInterval", "TrustDecayStep", "TrustPolicyMigrationCertificate",
    "TrustProjectionCommitCertificate", "TrustProjectionGeneration", "TrustProjectionHistoryEntry",
    "TrustProjectionPublication", "TrustProjectionRecord", "TypeEvidence", "TypedLiteral",
    "VerbatimTextArtifactMappingProof",
})


def _issue(issues: list[dict[str, str]], schema_id: str, path: str, reason: str) -> None:
    issues.append({"schema_id": schema_id, "path": path, "reason": reason})


def _literal(values: tuple[object, ...], schema_id: str, path: str, issues: list[dict[str, str]]) -> dict[str, Any] | None:
    rendered: list[object] = []
    for value in values:
        if isinstance(value, (bool, str)):
            rendered.append(value)
        elif type(value) is int:
            rendered.append({"integer_value": str(value)})
        else:
            _issue(issues, schema_id, path, "unsupported_literal_value")
            return None
    return {"kind": "literal", "values": sorted(rendered, key=lambda item: json.dumps(item, sort_keys=True))}


def _type_expr(
    annotation: object,
    schema_id: str,
    path: str,
    issues: list[dict[str, str]],
    *,
    discriminator: str | None = None,
) -> dict[str, Any] | None:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Annotated:
        base, *metadata = args
        discriminator = next(
            (value for item in metadata if isinstance((value := getattr(item, "discriminator", None)), str)),
            None,
        )
        if discriminator is not None:
            return _discriminated_union(base, discriminator, schema_id, path, issues)
        expression = _type_expr(base, schema_id, path, issues)
        if expression is not None and expression["kind"] == "string":
            patterns = {getattr(item, "pattern", None) for item in metadata}
            if "^[0-9a-f]{64}$" in patterns:
                expression["lexical_rule"] = "sha256"
            elif "^[0-9a-f]{128}$" in patterns:
                expression["lexical_rule"] = "signature_hex128"
            elif any(getattr(item, "min_length", None) == 1 for item in metadata):
                expression["lexical_rule"] = "nonempty_unicode_scalar"
        return expression
    if origin is Literal:
        return _literal(args, schema_id, path, issues)
    if annotation is str:
        return {"kind": "string", "lexical_rule": "unicode_scalar"}
    if annotation is int:
        return {"kind": "integer", "lexical_rule": "canonical_decimal", "minimum": None, "maximum": None}
    if annotation is bool:
        return {"kind": "bool"}
    if annotation is bytes:
        return {"kind": "bytes", "lexical_rule": "rfc4648_standard_padded"}
    if annotation is datetime:
        return {"kind": "datetime", "lexical_rule": "utc_six_fractional_digits"}
    if annotation is timedelta:
        return {"kind": "duration_microseconds", "lexical_rule": "signed_i64"}
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if annotation is SourceModality:
            return {"kind": "enum_ref", "qualified_id": "memorii.domain.SourceModality"}
        _issue(issues, schema_id, path, "enum_has_no_reviewed_registered_qualified_id")
        return None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return {"kind": "model_ref", "schema_id": annotation.__name__, "schema_version": "1"}
    if origin in (list, set, frozenset):
        child = _type_expr(args[0], schema_id, path, issues)
        return None if child is None else {"kind": origin.__name__, "element": child}
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            child = _type_expr(args[0], schema_id, path, issues)
            return None if child is None else {"kind": "variadic_tuple", "element": child}
        children = [_type_expr(item, schema_id, path, issues) for item in args]
        return None if any(item is None for item in children) else {"kind": "fixed_tuple", "items": children}
    if origin in (dict, Mapping):
        if args[0] is not str:
            _issue(issues, schema_id, path, "map_key_is_not_string")
            return None
        child = _type_expr(args[1], schema_id, path, issues)
        return None if child is None else {"kind": "map", "key_kind": "string", "value": child}
    if origin in (Union, UnionType):
        if discriminator is not None:
            return _discriminated_union(annotation, discriminator, schema_id, path, issues)
        inferred_discriminator = _existing_literal_discriminator(annotation)
        if inferred_discriminator is not None:
            return _discriminated_union(annotation, inferred_discriminator, schema_id, path, issues)
        non_null = [item for item in args if item is not type(None)]
        if len(non_null) == 1 and len(non_null) != len(args):
            return _type_expr(non_null[0], schema_id, path, issues)
        _issue(issues, schema_id, path, "union_requires_reviewed_discriminator")
        return None
    _issue(issues, schema_id, path, "unsupported_annotation")
    return None


def _discriminated_union(
    annotation: object,
    discriminator: str,
    schema_id: str,
    path: str,
    issues: list[dict[str, str]],
) -> dict[str, Any] | None:
    """Render a reviewed ``Annotated[..., Field(discriminator=...)]`` union."""
    alternatives: list[dict[str, Any]] = []
    alternatives_models = _flatten_union_models(annotation)
    if not alternatives_models:
        _issue(issues, schema_id, path, "discriminated_union_member_is_not_model")
        return None
    for alternative in alternatives_models:
        field = alternative.model_fields.get(discriminator)
        if field is None or get_origin(field.annotation) is not Literal:
            _issue(issues, schema_id, path, "discriminated_union_lacks_literal_member")
            return None
        values = get_args(field.annotation)
        if len(values) != 1 or not isinstance(values[0], str):
            _issue(issues, schema_id, path, "discriminated_union_lacks_singleton_string_literal")
            return None
        alternatives.append(
            {
                "discriminator_value": values[0],
                "model": {"kind": "model_ref", "schema_id": alternative.__name__, "schema_version": "1"},
            }
        )
    if not alternatives or len({item["discriminator_value"] for item in alternatives}) != len(alternatives):
        _issue(issues, schema_id, path, "discriminated_union_alternatives_not_unique")
        return None
    return {"kind": "union", "discriminator": discriminator, "alternatives": sorted(alternatives, key=lambda item: item["discriminator_value"])}


def _flatten_union_models(annotation: object) -> tuple[type[BaseModel], ...]:
    """Flatten reviewed aliases without inventing a new union member."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _flatten_union_models(get_args(annotation)[0])
    if origin in (Union, UnionType):
        return tuple(model for item in get_args(annotation) for model in _flatten_union_models(item))
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return (annotation,)
    return ()


def _existing_literal_discriminator(annotation: object) -> str | None:
    """Use only an already-declared common singleton-Literal discriminator."""
    alternatives = _flatten_union_models(annotation)
    if len(alternatives) < 2:
        return None
    common = set(alternatives[0].model_fields)
    for alternative in alternatives[1:]:
        common &= set(alternative.model_fields)
    for name in sorted(common):
        values: list[str] = []
        for alternative in alternatives:
            field_annotation = alternative.model_fields[name].annotation
            if get_origin(field_annotation) is not Literal:
                break
            literal = get_args(field_annotation)
            if len(literal) != 1 or not isinstance(literal[0], str):
                break
            values.append(literal[0])
        else:
            if len(set(values)) == len(values):
                return name
    return None


def _field_policy(field: Any) -> str:
    nullable = type(None) in get_args(field.annotation)
    # Native codecs publish complete model_dump(mode="python") bodies.  Python
    # defaults are construction conveniences, never source-wire omission.
    return "required_nullable" if nullable else "required"


def _apply_field_constraints(
    expression: dict[str, Any], field: Any, schema_id: str, name: str, issues: list[dict[str, str]]
) -> dict[str, Any]:
    """Keep grammar-representable reviewed Field metadata in the raw draft."""
    patterns = {getattr(metadata, "pattern", None) for metadata in field.metadata}
    if expression["kind"] == "string":
        if "^[0-9a-f]{64}$" in patterns or name.endswith("_digest"):
            expression["lexical_rule"] = "sha256"
        elif "^[0-9a-f]{128}$" in patterns:
            expression["lexical_rule"] = "signature_hex128"
        elif any(getattr(metadata, "min_length", None) == 1 for metadata in field.metadata):
            expression["lexical_rule"] = "nonempty_unicode_scalar"
        elif any(pattern is not None for pattern in patterns):
            _issue(issues, schema_id, name, "unsupported_string_pattern")
    if expression["kind"] == "integer":
        minimum = maximum = None
        for metadata in field.metadata:
            ge, gt = getattr(metadata, "ge", None), getattr(metadata, "gt", None)
            le, lt = getattr(metadata, "le", None), getattr(metadata, "lt", None)
            if ge is not None:
                minimum = ge
            elif gt is not None:
                minimum = gt + 1 if type(gt) is int else "unsupported"
            if le is not None:
                maximum = le
            elif lt is not None:
                maximum = lt - 1 if type(lt) is int else "unsupported"
        if minimum == "unsupported" or maximum == "unsupported":
            _issue(issues, schema_id, name, "unsupported_noninteger_integer_bound")
        else:
            expression["minimum"] = None if minimum is None else str(minimum)
            expression["maximum"] = None if maximum is None else str(maximum)
    return expression


def _integrity_policy(schema_id: str, fields: list[dict[str, Any]], issues: list[dict[str, str]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if schema_id == "GraphObservationCursorPayload":
        return {"kind": "signature_only", "signature_field": "signature", "signature_purpose": "graph_observation_cursor", "signature_domain": "memorii.graph-observation.cursor.v3"}, [
            {**field, "integrity_role": "signature" if field["name"] == "signature" else "ordinary"} for field in fields
        ]
    if schema_id == "IngestionObservationReplayCheckpoint":
        return {"kind": "external_signing_preimage", "result_digest_field": "checkpoint_digest", "result_signature_field": "signature", "preimage_schema_id": "ObservationCheckpointSigningPreimage", "preimage_schema_version": "1", "binding_kind": "observation_checkpoint_v1", "signature_purpose": "observation_checkpoint", "signature_domain": "memorii.semantic_ingestion.observation.IngestionObservationReplayCheckpoint.v1", "proposal_requires_review": True}, [
            {**field, "integrity_role": "self_digest" if field["name"] == "checkpoint_digest" else "signature" if field["name"] == "signature" else "ordinary"} for field in fields
        ]
    digest_field = _SELF_DIGEST_FIELDS.get(schema_id)
    if digest_field is not None:
        domain = _NORMATIVE_DOMAINS.get(schema_id, f"memorii.semantic_ingestion.observation.{schema_id}.v1")
        policy: dict[str, Any] = {"kind": "self_digest", "digest_field": digest_field, "digest_domain": domain}
        if schema_id not in _NORMATIVE_DOMAINS:
            policy["proposal_requires_review"] = True
        return policy, [{**field, "integrity_role": "self_digest" if field["name"] == digest_field else "ordinary"} for field in fields]
    if schema_id in _ORDINARY_ROOTS | _REVIEWED_ORDINARY_TRANSITIVE:
        return {"kind": "ordinary"}, fields
    _issue(issues, schema_id, "digest-signature", "profile3_digest_or_signature_policy_not_yet_mapped")
    return {"kind": "unresolved"}, fields


def _schema_draft(schema_id: str, model: type[BaseModel], issues: list[dict[str, str]]) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    optional: list[dict[str, str]] = []
    try:
        hints = get_type_hints(model, include_extras=True)
    except NameError:
        # Several native classes intentionally keep import-cycle annotations
        # forward.  Preserve the unresolved field in the audit rather than
        # importing a guessed owner just to evaluate it.
        hints = {}
    for name, field in sorted(model.model_fields.items()):
        if model is graph_records.SnapshotGraphRecord and name == "payload":
            expr = {
                "kind": "union", "discriminator": "record_kind",
                "alternatives": sorted([
                    {"discriminator_value": payload.model_fields["record_kind"].default,
                     "model": {"kind": "model_ref", "schema_id": payload.__name__, "schema_version": "1"}}
                    for payload in _SNAPSHOT_PAYLOAD_MODELS
                ], key=lambda alternative: alternative["discriminator_value"]),
            }
        else:
            expr = _type_expr(
                hints.get(name, field.annotation),
                schema_id,
                name,
                issues,
                discriminator=field.discriminator if isinstance(field.discriminator, str) else None,
            )
        if expr is not None:
            expr = _apply_field_constraints(expr, field, schema_id, name, issues)
            fields.append({"name": name, "type": expr, "integrity_role": "ordinary"})
        optional.append({"field_name": name, "policy": _field_policy(field)})
    policy, fields = _integrity_policy(schema_id, fields, issues)
    enums: list[dict[str, Any]] = []
    if schema_id == "SegmentGovernanceBinding":
        enums.append(
            {
                "qualified_id": "memorii.domain.SourceModality",
                "members": [
                    {"member_id": member.name, "wire_value": member.value}
                    for member in sorted(SourceModality, key=lambda member: member.name)
                ],
            }
        )
    return {
        "schema": {"role": "schema", "schema_id": schema_id, "schema_version": "1", "root_kind": "model", "fields": fields},
        "enum": {"role": "enum", "schema_id": schema_id, "schema_version": "1", "enums": enums},
        "optional": {"role": "optional", "schema_id": schema_id, "schema_version": "1", "fields": optional},
        "numeric": {"role": "numeric", "schema_id": schema_id, "schema_version": "1", "fields": []},
        "digest_signature": {"role": "digest-signature", "schema_id": schema_id, "schema_version": "1", "policy": policy},
        "unresolved_roles": ["decoder", "upcast", "registry"],
    }


def _nested_models(annotation: object) -> tuple[type[BaseModel], ...]:
    """Find direct Pydantic references while preserving model type identity."""
    if get_origin(annotation) is Annotated:
        return _nested_models(get_args(annotation)[0])
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return (annotation,)
    return tuple(model for argument in get_args(annotation) for model in _nested_models(argument))


def build_draft() -> dict[str, Any]:
    """Return untrusted authoring data; this function never publishes it."""
    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    roots: list[dict[str, Any]] = []
    drafted: dict[str, type[BaseModel]] = {}
    for schema_id, model in ROOT_MODELS:
        if schema_id in seen:
            _issue(issues, schema_id, "schema_id", "duplicate_static_root_schema_id")
            continue
        seen.add(schema_id)
        drafted[schema_id] = model
        roots.append({"source_id": schema_id, "schema_id": schema_id})
    # Helper schema IDs use only reviewed class names.  A collision is reported
    # rather than repaired with a module-qualified, digest-authoritative name.
    pending = list(drafted.items())
    while pending:
        _, model = pending.pop()
        for field in model.model_fields.values():
            if model is graph_records.SnapshotGraphRecord and field.annotation is BaseModel:
                for payload in _SNAPSHOT_PAYLOAD_MODELS:
                    helper_id = payload.__name__
                    prior = drafted.get(helper_id)
                    if prior is None:
                        drafted[helper_id] = payload
                        pending.append((helper_id, payload))
                    elif prior is not payload:
                        _issue(issues, helper_id, "schema_id", "helper_schema_name_collision_requires_naming_review")
                continue
            for nested in _nested_models(field.annotation):
                helper_id = nested.__name__
                prior = drafted.get(helper_id)
                if prior is None:
                    drafted[helper_id] = nested
                    pending.append((helper_id, nested))
                elif prior is not nested:
                    _issue(issues, helper_id, "schema_id", "helper_schema_name_collision_requires_naming_review")
    schemas = [
        {"schema_id": schema_id, "draft": _schema_draft(schema_id, model, issues)}
        for schema_id, model in sorted(drafted.items())
    ]
    return {
        "status": "UNTRUSTED_AUTHORING_DRAFT_NOT_FOR_COMPILATION_OR_PUBLICATION",
        "source_ids": [root["source_id"] for root in roots],
        "roots": roots,
        "schemas": schemas,
        "unsupported_or_ambiguous": sorted(issues, key=lambda item: (item["schema_id"], item["path"], item["reason"])),
    }


def write_draft(output_directory: Path = _OUTPUT_DIRECTORY) -> Path:
    """Write the review artifact under the designated work-plan directory."""
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / _DRAFT_NAME
    output.write_text(json.dumps(build_draft(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(write_draft())

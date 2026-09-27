"""governed-source admission governed source admission and non-disclosing outcome access.

This module deliberately stops at source admission.  It does not allocate a
writer, acquire a lease, or publish a semantic generation; those are writer-safe preplanning
responsibilities.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from memorii.core.memory_evolution.bootstrap_profile import (
    BOOTSTRAP_COORDINATE,
    BootstrapAuthenticatedLanguageEvidence,
    BootstrapProfileOutcome,
    BootstrapUnavailableReason,
    GovernedSourceAdmissionFact,
    ProfileAcceptedCandidate,
    ProfileCommittedTerminal,
    ProfileDisabled,
    ProfileInputOutcome,
    ProfileSelectedPipelinePending,
    ProfileUnavailable,
    normalized_input_digest,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    OperationFenceBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.models import SourceObservation
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import MemoryPlaneRevisionConflictError, RecordAbsentPrecondition
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

if TYPE_CHECKING:
    from memorii.core.semantic_ingestion.contracts import SemanticTerminalOutcome


class SemanticIngestionOutcomeLookupRequest(BaseModel):
    """Purpose-bound authenticated lookup input; it contains no source payload."""

    delivery_identity: DeliveryIdentity

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticIngestionSourceReplayRequest(BaseModel):
    """Purpose-bound authenticated redelivery input; it contains no source payload."""

    delivery_identity: DeliveryIdentity

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticIngestionOutcomeLookupResponse(BaseModel):
    """One deliberately non-disclosing result shape for all unavailable cases."""

    available: bool = False
    outcome: BootstrapProfileOutcome | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceAdmissionAccepted(BaseModel):
    source_id: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_identity: DeliveryIdentity
    required_outcome_scopes: RequiredOutcomeScopeSet
    admission_index_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding: OperationFenceBinding
    observation: SourceObservation

    model_config = ConfigDict(extra="forbid", frozen=True)


class PreparedSourceAdmission(BaseModel):
    accepted: SourceAdmissionAccepted
    records: tuple[CanonicalMemoryRecord, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


class RetainedSourceOperationRequest(BaseModel):
    """Opaque immutable input for a new operation over an admitted source.

    The caller supplies canonical bytes, rather than an operation identifier or
    digest.  The core derives both values after it has joined those bytes to an
    authenticated retained source.
    """

    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_envelope: bytes = Field(min_length=1, max_length=65536)

    model_config = ConfigDict(extra="forbid", frozen=True)




class RetainedSourceOperationAccepted(BaseModel):
    """Authenticated allocation input for a second operation on one source."""

    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_identity: DeliveryIdentity
    required_outcome_scopes: RequiredOutcomeScopeSet
    source_admission_index_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_envelope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_fence_binding: OperationFenceBinding

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_join(self) -> RetainedSourceOperationAccepted:
        fence = self.operation_fence_binding
        if (
            fence.source_id != self.source_id
            or fence.source_digest != self.source_digest
            or fence.delivery_identity != self.delivery_identity
        ):
            raise ValueError("retained source operation fence does not join source")
        expected_operation_id = retained_source_operation_id(
            source_id=self.source_id,
            source_digest=self.source_digest,
            delivery_identity=self.delivery_identity,
            canonical_envelope_digest=self.canonical_envelope_digest,
        )
        if fence.operation_id != expected_operation_id:
            raise ValueError("retained source operation ID is not core derived")
        return self


class GovernedSourceAdmissionService:
    """Owns the small governed-source admission admission index and its authorization-before-result rule."""

    def __init__(self, memory_plane: MemoryPlaneService) -> None:
        self._memory_plane = memory_plane

    def allocate_retained_source_operation(
        self,
        *,
        request: RetainedSourceOperationRequest,
        authenticated_ingress: AuthenticatedIngressContext,
    ) -> RetainedSourceOperationAccepted:
        """Authorize and derive a distinct operation over one retained source.

        This does not retain the source again.  It validates the immutable
        source and its original admission index before deriving an operation
        coordinate from caller-independent canonical envelope bytes.
        """
        source = self._memory_plane.get_record(request.source_id)
        if source is None or source.source_kind not in {
            "semantic_ingestion_source", "semantic_ingestion_metadata_poor_snapshot",
        }:
            raise ValueError("retained source is unavailable")
        if source_admission_source_digest(source) != request.source_digest:
            raise ValueError("retained source digest is mismatched")
        indexes = tuple(
            record
            for record in self._memory_plane.list_records(
                source_kind="semantic_ingestion_admission_index"
            )
            if _index_binds_source(record, request.source_id, request.source_digest)
        )
        if len(indexes) != 1:
            raise ValueError("retained source admission is unavailable")
        index = indexes[0]
        try:
            original_fence = OperationFenceBinding.model_validate(
                index.content["operation_fence_binding"]
            )
            required = RequiredOutcomeScopeSet.create(
                tenant_partition_id=index.content["tenant_partition_id"],
                scopes=index.content["required_scopes"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("retained source admission is corrupt") from exc
        ingress = authenticated_ingress
        if (
            ingress.delivery_principal_binding.binding_digest
            != original_fence.delivery_principal_binding_digest
            or ingress.delivery_principal_binding.tenant_partition_id
            != required.tenant_partition_id
            or ingress.required_outcome_scopes != required
            or not set(required.scopes).issubset(ingress.current_authorized_scopes.scopes)
        ):
            raise ValueError("retained source access is denied")
        envelope_digest = sha256(
            b"memorii.semantic-ingestion.retained-source-envelope.v1\0"
            + request.canonical_envelope
        ).hexdigest()
        operation_id = retained_source_operation_id(
            source_id=request.source_id,
            source_digest=request.source_digest,
            delivery_identity=original_fence.delivery_identity,
            canonical_envelope_digest=envelope_digest,
        )
        return RetainedSourceOperationAccepted(
            source_id=request.source_id,
            source_digest=request.source_digest,
            delivery_identity=original_fence.delivery_identity,
            required_outcome_scopes=required,
            source_admission_index_digest=_index_digest(index),
            canonical_envelope_digest=envelope_digest,
            operation_fence_binding=OperationFenceBinding.create(
                operation_id=operation_id,
                source_id=request.source_id,
                source_digest=request.source_digest,
                delivery_identity=original_fence.delivery_identity,
            ),
        )

    def admit(
        self,
        *,
        source: CanonicalMemoryRecord,
        delivery_identity: DeliveryIdentity,
        ingress: AuthenticatedIngressContext,
        operation_id: str,
        outcome_kind: str = "selected_pipeline_pending",
        outcome_reason: str | None = None,
        normalized_input: bytes = b"",
        evidence_only: bool = False,
        matched_corpus_case_id: str | None = None,
        selection_digest: str | None = None,
        verification_digest: str | None = None,
        bootstrap_language_evidence: BootstrapAuthenticatedLanguageEvidence | None = None,
    ) -> SourceAdmissionAccepted:
        if self._memory_plane.get_record("semantic_ingestion:writer_admission:current") is not None:
            raise ValueError("governed source admission must use the semantic atomic store")
        _validate_governed_source(source)
        if delivery_identity.delivery_principal_binding_digest != ingress.delivery_principal_binding.binding_digest:
            raise ValueError("authenticated principal does not own delivery identity")
        # Required scopes are an authenticated host-governance assertion.  Do
        # not derive them from mutable/public provider-event metadata and do
        # not erase them for evidence-only outcomes.
        required = ingress.required_outcome_scopes
        if not set(required.scopes).issubset(ingress.current_authorized_scopes.scopes):
            raise ValueError("authenticated scope coverage is incomplete")
        source_digest = source_admission_source_digest(source)
        operation_fence = OperationFenceBinding.create(
            operation_id=operation_id,
            source_id=source.memory_id,
            source_digest=source_digest,
            delivery_identity=delivery_identity,
        )
        writer_coordinate = _source_admission_writer_coordinate(self._memory_plane)
        index = _index_record(
            delivery_identity=delivery_identity,
            required=required,
            operation_fence=operation_fence,
            writer_coordinate=writer_coordinate,
            timestamp=source.timestamp,
        )
        selection_status = (
            "disabled"
            if outcome_kind == "disabled"
            else ("selected" if selection_digest is not None else "unavailable")
        )
        verification_status = "verified" if verification_digest is not None else "unavailable"
        selection = _profile_evidence_record(
            index, "semantic_ingestion_profile_selection", {"status": selection_status}
        )
        verification = _profile_evidence_record(
            index, "semantic_ingestion_profile_verification", {"status": verification_status}
        )
        fact = GovernedSourceAdmissionFact(
            source_id=source.memory_id,
            source_digest=source_digest,
            delivery_principal_binding_digest=delivery_identity.delivery_principal_binding_digest,
            delivery_key_digest=delivery_identity.delivery_key_digest,
            required_scope_set_digest=required.required_scope_set_digest,
            admission_index_digest=_index_digest(index),
        )
        typed_outcome = _make_outcome(
            kind=outcome_kind,
            reason=outcome_reason,
            fact=fact,
            normalized_input=normalized_input,
            selection_digest=selection_digest or _index_digest(selection),
            verification_digest=verification_digest or _index_digest(verification),
            matched_corpus_case_id=matched_corpus_case_id,
        )
        outcome = _profile_evidence_record(
            index, "semantic_ingestion_profile_outcome", typed_outcome.model_dump(mode="json")
        )
        existing = self._memory_plane.get_record(index.memory_id)
        if existing is not None:
            return self._recover_exact_admission(
                source=source,
                source_digest=source_digest,
                index=index,
                existing=existing,
                delivery_identity=delivery_identity,
                required=required,
                operation_fence=operation_fence,
            )
        # A single memory-plane batch makes retained evidence and its protected
        # authorization index visible together.  It is intentionally not an writer-safe preplanning
        # semantic generation or writer protocol.
        try:
            with self._memory_plane.unit_of_work() as unit_of_work:
                self._memory_plane.write_records((source, index, selection, verification, outcome))
                unit_of_work.commit(
                    preconditions=(
                        RecordAbsentPrecondition(memory_id=source.memory_id),
                        RecordAbsentPrecondition(memory_id=index.memory_id),
                        RecordAbsentPrecondition(memory_id=selection.memory_id),
                        RecordAbsentPrecondition(memory_id=verification.memory_id),
                        RecordAbsentPrecondition(memory_id=outcome.memory_id),
                    )
                )
        except MemoryPlaneRevisionConflictError:
            existing = self._memory_plane.get_record(index.memory_id)
            if existing is None:
                raise
            return self._recover_exact_admission(
                source=source,
                source_digest=source_digest,
                index=index,
                existing=existing,
                delivery_identity=delivery_identity,
                required=required,
                operation_fence=operation_fence,
            )
        return SourceAdmissionAccepted(
            source_id=source.memory_id,
            source_digest=source_digest,
            delivery_identity=delivery_identity,
            required_outcome_scopes=required,
            admission_index_digest=_index_digest(index),
            operation_fence_binding=operation_fence,
            observation=_admitted_observation(
                source=source,
                source_digest=source_digest,
                delivery_identity=delivery_identity,
                bootstrap_language_evidence=bootstrap_language_evidence,
            ),
        )

    def prepare_atomic(
        self,
        *,
        source: CanonicalMemoryRecord,
        delivery_identity: DeliveryIdentity,
        ingress: AuthenticatedIngressContext,
        operation_id: str,
        outcome_kind: str = "selected_pipeline_pending",
        outcome_reason: str | None = None,
        normalized_input: bytes = b"",
        evidence_only: bool = False,
        matched_corpus_case_id: str | None = None,
        selection_digest: str | None = None,
        verification_digest: str | None = None,
        bootstrap_language_evidence: BootstrapAuthenticatedLanguageEvidence | None = None,
    ) -> PreparedSourceAdmission:
        """Prepare, but do not publish, the governed-source admission evidence for writer-safe preplanning atomic admission."""
        _validate_governed_source(source)
        if delivery_identity.delivery_principal_binding_digest != ingress.delivery_principal_binding.binding_digest:
            raise ValueError("authenticated principal does not own delivery identity")
        required = ingress.required_outcome_scopes
        if not set(required.scopes).issubset(ingress.current_authorized_scopes.scopes):
            raise ValueError("authenticated scope coverage is incomplete")
        source_digest = source_admission_source_digest(source)
        operation_fence = OperationFenceBinding.create(
            operation_id=operation_id,
            source_id=source.memory_id,
            source_digest=source_digest,
            delivery_identity=delivery_identity,
        )
        writer_coordinate = _source_admission_writer_coordinate(self._memory_plane)
        index = _index_record(
            delivery_identity=delivery_identity,
            required=required,
            operation_fence=operation_fence,
            writer_coordinate=writer_coordinate,
            timestamp=source.timestamp,
        )
        selection_status = (
            "disabled"
            if outcome_kind == "disabled"
            else ("selected" if selection_digest is not None else "unavailable")
        )
        verification_status = "verified" if verification_digest is not None else "unavailable"
        selection = _profile_evidence_record(
            index, "semantic_ingestion_profile_selection", {"status": selection_status}
        )
        verification = _profile_evidence_record(
            index, "semantic_ingestion_profile_verification", {"status": verification_status}
        )
        fact = GovernedSourceAdmissionFact(
            source_id=source.memory_id,
            source_digest=source_digest,
            delivery_principal_binding_digest=delivery_identity.delivery_principal_binding_digest,
            delivery_key_digest=delivery_identity.delivery_key_digest,
            required_scope_set_digest=required.required_scope_set_digest,
            admission_index_digest=_index_digest(index),
        )
        typed_outcome = _make_outcome(
            kind=outcome_kind,
            reason=outcome_reason,
            fact=fact,
            normalized_input=normalized_input,
            selection_digest=selection_digest or _index_digest(selection),
            verification_digest=verification_digest or _index_digest(verification),
            matched_corpus_case_id=matched_corpus_case_id,
        )
        outcome = _profile_evidence_record(
            index, "semantic_ingestion_profile_outcome", typed_outcome.model_dump(mode="json")
        )
        accepted = SourceAdmissionAccepted(
            source_id=source.memory_id,
            source_digest=source_digest,
            delivery_identity=delivery_identity,
            required_outcome_scopes=required,
            admission_index_digest=_index_digest(index),
            operation_fence_binding=operation_fence,
            observation=_admitted_observation(
                source=source,
                source_digest=source_digest,
                delivery_identity=delivery_identity,
                bootstrap_language_evidence=bootstrap_language_evidence,
            ),
        )
        return PreparedSourceAdmission(accepted=accepted, records=(source, index, selection, verification, outcome))

    def _recover_exact_admission(
        self,
        *,
        source: CanonicalMemoryRecord,
        source_digest: str,
        index: CanonicalMemoryRecord,
        existing: CanonicalMemoryRecord,
        delivery_identity: DeliveryIdentity,
        required: RequiredOutcomeScopeSet,
        operation_fence: OperationFenceBinding,
    ) -> SourceAdmissionAccepted:
        if existing.source_kind != "semantic_ingestion_admission_index" or existing.content != index.content:
            raise ValueError("delivery identity is already bound to a different admission")
        retained = self._memory_plane.get_record(source.memory_id)
        if retained is None or _immutable_source_identity(retained) != _immutable_source_identity(source):
            raise RuntimeError("admission index references missing or changed source evidence")
        return SourceAdmissionAccepted(
            source_id=source.memory_id,
            source_digest=source_digest,
            delivery_identity=delivery_identity,
            required_outcome_scopes=required,
            admission_index_digest=_index_digest(index),
            operation_fence_binding=operation_fence,
            observation=_admitted_observation(
                source=source,
                source_digest=source_digest,
                delivery_identity=delivery_identity,
            ),
        )

    def lookup(
        self,
        request: SemanticIngestionOutcomeLookupRequest,
        *,
        authenticated_ingress: AuthenticatedIngressContext,
    ) -> SemanticIngestionOutcomeLookupResponse:
        """Authorize from the protected index before touching any outcome store."""

        index_id = _index_id(request.delivery_identity.delivery_key_digest)
        index = self._memory_plane.get_record(index_id)
        if index is None or index.source_kind != "semantic_ingestion_admission_index":
            return SemanticIngestionOutcomeLookupResponse()
        content = index.content
        if (
            content.get("principal_binding_digest") != authenticated_ingress.delivery_principal_binding.binding_digest
            or content.get("delivery_key_digest") != request.delivery_identity.delivery_key_digest
            or content.get("tenant_partition_id")
            != authenticated_ingress.delivery_principal_binding.tenant_partition_id
        ):
            return SemanticIngestionOutcomeLookupResponse()
        required = tuple(content.get("required_scopes", ()))
        if not set(required).issubset(authenticated_ingress.current_authorized_scopes.scopes):
            return SemanticIngestionOutcomeLookupResponse()
        # Only after every non-disclosing authorization check may governed-source admission read its
        # protected outcome evidence.
        outcome = self._memory_plane.get_record(f"{index_id}:outcome")
        if outcome is None or outcome.source_kind != "semantic_ingestion_profile_outcome":
            return SemanticIngestionOutcomeLookupResponse()
        try:
            decoded = TypeAdapter(BootstrapProfileOutcome).validate_python(outcome.content)
        except ValueError:
            return SemanticIngestionOutcomeLookupResponse()
        fence_value = content.get("operation_fence_binding")
        try:
            fence = OperationFenceBinding.model_validate(fence_value)
        except ValueError:
            return SemanticIngestionOutcomeLookupResponse()
        control = self._memory_plane.get_record(f"semantic_ingestion:operation:{fence.operation_fence_id}")
        if control is not None and control.source_kind == "semantic_ingestion_preplanning_control":
            control_value = control.content.get("control")
            if isinstance(control_value, dict):
                state = control_value.get("state")
                generation = control_value.get("generation")
                if state == "terminal" and isinstance(generation, int):
                    lifecycle = self._lifecycle_transition(fence=fence, generation=generation)
                    terminal = self._terminal_result(fence=fence, generation=generation)
                    if (
                        terminal is None
                        or lifecycle is None
                        or lifecycle.terminal_digest is None
                        or lifecycle.terminal_digest != terminal.terminal_digest
                    ):
                        return SemanticIngestionOutcomeLookupResponse()
                    if lifecycle.to_kind == "committed_terminal":
                        decoded = ProfileCommittedTerminal(
                            kind="committed_terminal",
                            coordinate=decoded.coordinate,
                            source_admission=decoded.source_admission,
                            terminal_result_digest=lifecycle.terminal_digest,
                            operation_fence_binding_digest=fence.binding_digest,
                        )
                    elif lifecycle.to_kind in {"unsupported_input", "abstained"}:
                        source = self._memory_plane.get_record(decoded.source_admission.source_id)
                        if source is None or lifecycle.reason_code is None:
                            return SemanticIngestionOutcomeLookupResponse()
                        reason = (
                            lifecycle.reason_code
                            if lifecycle.reason_code != "retry_budget_exhausted"
                            else "extractor_abstained"
                        )
                        decoded = ProfileInputOutcome.model_validate(
                            {
                                "kind": lifecycle.to_kind,
                                "coordinate": decoded.coordinate,
                                "source_admission": decoded.source_admission,
                                "reason": reason,
                                "input_normalized_digest": normalized_input_digest(source.text.encode("utf-8")),
                                "matched_corpus_case_id": None,
                            }
                        )
                    else:
                        return SemanticIngestionOutcomeLookupResponse()
                elif state == "planned" and isinstance(generation, int):
                    lifecycle = self._lifecycle_transition(fence=fence, generation=generation)
                    if (
                        lifecycle is None
                        or lifecycle.to_kind != "accepted_candidate"
                        or lifecycle.candidate_digest is None
                    ):
                        return SemanticIngestionOutcomeLookupResponse()
                    decoded = ProfileAcceptedCandidate(
                        kind="accepted_candidate",
                        coordinate=decoded.coordinate,
                        source_admission=decoded.source_admission,
                        candidate_digest=lifecycle.candidate_digest,
                        operation_fence_binding_digest=fence.binding_digest,
                    )
        return SemanticIngestionOutcomeLookupResponse(available=True, outcome=decoded)

    def replay_retained_source(
        self,
        request: SemanticIngestionSourceReplayRequest,
        *,
        authenticated_ingress: AuthenticatedIngressContext,
    ) -> CanonicalMemoryRecord | None:
        """Return the winner's retained source bytes for an authorized redelivery.

        Authorization precedes byte access exactly as ``lookup`` precedes
        outcome access: principal, delivery key, tenant, and the complete
        stored scope set are validated against the protected admission index
        before any retained record is returned.  This is deliberately not an
        outcome lookup; it never decodes outcome evidence and returns only
        the immutable retained source whose digest binds to the indexed
        operation fence.  Any anomaly denies (returns ``None``) instead of
        disclosing bytes.
        """
        index_id = _index_id(request.delivery_identity.delivery_key_digest)
        index = self._memory_plane.get_record(index_id)
        if index is None or index.source_kind != "semantic_ingestion_admission_index":
            return None
        content = index.content
        if (
            content.get("principal_binding_digest") != authenticated_ingress.delivery_principal_binding.binding_digest
            or content.get("delivery_key_digest") != request.delivery_identity.delivery_key_digest
            or content.get("tenant_partition_id")
            != authenticated_ingress.delivery_principal_binding.tenant_partition_id
        ):
            return None
        required = tuple(content.get("required_scopes", ()))
        if not set(required).issubset(authenticated_ingress.current_authorized_scopes.scopes):
            return None
        try:
            fence = OperationFenceBinding.model_validate(content.get("operation_fence_binding"))
        except ValueError:
            return None
        retained = self._memory_plane.get_record(fence.source_id)
        try:
            retained_digest = source_admission_source_digest(retained) if retained is not None else None
        except ValueError:
            return None
        if (
            retained is None
            or retained.memory_id != fence.source_id
            or retained.source_kind
            not in {
                "semantic_ingestion_source",
                "semantic_ingestion_metadata_poor_snapshot",
            }
            or retained_digest != fence.source_digest
        ):
            return None
        return retained

    def recover_pending_admission(
        self,
        *,
        operation_fence: OperationFenceBinding,
        authenticated_ingress: AuthenticatedIngressContext,
    ) -> SourceAdmissionAccepted | None:
        """Rebuild the typed pending handoff input from atomically retained records."""

        from memorii.core.memory_evolution.record_projection import (
            source_observation_from_record,
        )

        delivery_identity = operation_fence.delivery_identity
        retained = self.replay_retained_source(
            SemanticIngestionSourceReplayRequest(delivery_identity=delivery_identity),
            authenticated_ingress=authenticated_ingress,
        )
        if retained is None:
            return None
        index = self._memory_plane.get_record(_index_id(delivery_identity.delivery_key_digest))
        if index is None or index.source_kind != "semantic_ingestion_admission_index":
            return None
        try:
            retained_fence = OperationFenceBinding.model_validate(index.content["operation_fence_binding"])
            required = RequiredOutcomeScopeSet.create(
                tenant_partition_id=index.content["tenant_partition_id"],
                scopes=index.content["required_scopes"],
            )
            observation = source_observation_from_record(retained)
        except (KeyError, TypeError, ValueError):
            return None
        if (
            retained_fence != operation_fence
            or required != authenticated_ingress.required_outcome_scopes
            or observation.source_id != operation_fence.source_id
            or observation.source_digest != operation_fence.source_digest
            or observation.delivery_key_digest != delivery_identity.delivery_key_digest
        ):
            return None
        return SourceAdmissionAccepted(
            source_id=operation_fence.source_id,
            source_digest=operation_fence.source_digest,
            delivery_identity=delivery_identity,
            required_outcome_scopes=required,
            admission_index_digest=_index_digest(index),
            operation_fence_binding=operation_fence,
            observation=observation,
        )

    def _terminal_result(
        self,
        *,
        fence: OperationFenceBinding,
        generation: int,
    ) -> SemanticTerminalOutcome | None:
        from memorii.core.semantic_ingestion.contracts import (
            SemanticTerminalOutcome,
            decode_semantic_contract,
        )

        manifest = self._memory_plane.get_record(
            f"semantic_ingestion:generation:{fence.operation_fence_id}:{generation}:manifest"
        )
        if manifest is None or manifest.source_kind != "semantic_ingestion_generation_manifest":
            return None
        members = manifest.content.get("members")
        if not isinstance(members, (list, tuple)):
            return None
        source_results = tuple(
            value for value in members if isinstance(value, dict) and value.get("kind") == "source_result"
        )
        if len(source_results) != 1:
            return None
        payload = source_results[0].get("canonical_payload")
        if not isinstance(payload, str):
            return None
        try:
            terminal = decode_semantic_contract(payload.encode("utf-8"), SemanticTerminalOutcome)
        except (ValueError, TypeError):
            return None
        return terminal if terminal.operation_id == fence.operation_id else None

    def _lifecycle_transition(self, *, fence: OperationFenceBinding, generation: int):
        from memorii.core.semantic_ingestion.contracts import (
            SemanticLifecycleTransition,
            decode_semantic_contract,
        )

        for candidate_generation in range(generation, 1, -1):
            manifest = self._memory_plane.get_record(
                f"semantic_ingestion:generation:{fence.operation_fence_id}:{candidate_generation}:manifest"
            )
            if manifest is None or manifest.source_kind != "semantic_ingestion_generation_manifest":
                return None
            members = manifest.content.get("members")
            if not isinstance(members, (list, tuple)):
                return None
            transitions = tuple(
                value for value in members if isinstance(value, dict) and value.get("kind") == "lifecycle"
            )
            if not transitions:
                continue
            if len(transitions) != 1:
                return None
            payload = transitions[0].get("canonical_payload")
            if not isinstance(payload, str):
                return None
            try:
                lifecycle = decode_semantic_contract(payload.encode("utf-8"), SemanticLifecycleTransition)
            except (ValueError, TypeError):
                return None
            return lifecycle if lifecycle.operation_id == fence.operation_id else None
        return None


def source_admission_source_digest(source: CanonicalMemoryRecord) -> str:
    material = source.content.get("source_admission")
    if isinstance(material, dict) and "step_one_material_ctv" in material:
        from memorii.core.memory_evolution.source_admission import step_one_source_digest

        key = material.get("delivery_key_digest")
        if not isinstance(key, str):
            raise ValueError("Step-1 source record has no delivery key")
        return step_one_source_digest(
            source_id=source.memory_id,
            delivery_key_digest=key,
            original_text=source.text,
        )
    return sha256(source_admission_source_bytes(source)).hexdigest()


def _admitted_observation(
    *,
    source: CanonicalMemoryRecord,
    source_digest: str,
    delivery_identity: DeliveryIdentity,
    bootstrap_language_evidence: BootstrapAuthenticatedLanguageEvidence | None = None,
) -> SourceObservation:
    """Project the immutable retained record without recomputing its identity."""

    from memorii.core.memory_evolution.record_projection import (
        source_observation_from_record,
        source_type_from_record,
    )

    if (
        isinstance(source.content.get("source_admission"), dict)
        and "step_one_material_ctv" in source.content["source_admission"]
    ):
        observation = source_observation_from_record(source)
        if (
            observation.source_digest != source_digest
            or observation.delivery_key_digest != delivery_identity.delivery_key_digest
        ):
            raise ValueError("Step-1 admission observation does not bind its delivery")
        return observation.model_copy(update={"bootstrap_language_evidence": bootstrap_language_evidence})

    return SourceObservation(
        source_id=source.memory_id,
        text=source.text,
        source_type=source_type_from_record(source),
        timestamp=source.timestamp,
        domain=source.domain,
        session_id=source.session_id,
        task_id=source.task_id,
        user_id=source.user_id,
        language=source.language,
        source_digest=source_digest,
        delivery_key_digest=delivery_identity.delivery_key_digest,
        bootstrap_language_evidence=bootstrap_language_evidence,
    )


def source_admission_source_bytes(source: CanonicalMemoryRecord) -> bytes:
    """Canonical immutable bytes that identify one governed raw source event."""

    return encode_typed_value(_immutable_source_identity(source))


def retained_source_operation_id(
    *,
    source_id: str,
    source_digest: str,
    delivery_identity: DeliveryIdentity,
    canonical_envelope_digest: str,
) -> str:
    """Derive the sole operation identity for one retained-source envelope."""
    if not source_id or len(source_digest) != 64 or len(canonical_envelope_digest) != 64:
        raise ValueError("retained source operation identity is invalid")
    return "retained-source:v1:" + sha256(
        b"memorii.semantic-ingestion.retained-source-operation.v1\0"
        + encode_typed_value(
            {
                "source_id": source_id,
                "source_digest": source_digest,
                "delivery_key_digest": delivery_identity.delivery_key_digest,
                "canonical_envelope_digest": canonical_envelope_digest,
            }
        )
    ).hexdigest()


def _immutable_source_identity(source: CanonicalMemoryRecord) -> dict[str, object]:
    """Exclude regenerated storage timestamps from delivery retry identity."""
    value = source.model_dump(mode="python")
    value.pop("timestamp", None)
    return value


def _index_digest(index: CanonicalMemoryRecord) -> str:
    return sha256(encode_typed_value(index.content)).hexdigest()


def _validate_governed_source(source: CanonicalMemoryRecord) -> None:
    if (
        source.domain != MemoryDomain.TRANSCRIPT
        or not source.is_raw_event
        or source.source_kind not in {"semantic_ingestion_source", "semantic_ingestion_metadata_poor_snapshot"}
        or source.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
    ):
        raise ValueError("admission requires a governed immutable source record")


def _index_id(delivery_key_digest: str) -> str:
    return f"semantic_ingestion:admission:{delivery_key_digest}"


def _index_binds_source(
    index: CanonicalMemoryRecord, source_id: str, source_digest: str
) -> bool:
    try:
        fence = OperationFenceBinding.model_validate(index.content["operation_fence_binding"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        index.source_kind == "semantic_ingestion_admission_index"
        and fence.source_id == source_id
        and fence.source_digest == source_digest
    )


def _index_record(
    *,
    delivery_identity: DeliveryIdentity,
    required: RequiredOutcomeScopeSet,
    operation_fence: OperationFenceBinding,
    writer_coordinate: tuple[int, str] | None,
    timestamp: datetime,
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=_index_id(delivery_identity.delivery_key_digest),
        domain=MemoryDomain.TRANSCRIPT,
        text="",
        content={
            "principal_binding_digest": delivery_identity.delivery_principal_binding_digest,
            "delivery_key_digest": delivery_identity.delivery_key_digest,
            "tenant_partition_id": required.tenant_partition_id,
            "required_scopes": list(required.scopes),
            "required_scope_set_digest": required.required_scope_set_digest,
            "operation_fence_binding": operation_fence.model_dump(mode="json"),
            "admitted_writer_epoch": writer_coordinate[0] if writer_coordinate is not None else None,
            "writer_admission_digest": writer_coordinate[1] if writer_coordinate is not None else None,
        },
        status=CommitStatus.COMMITTED,
        source_kind="semantic_ingestion_admission_index",
        timestamp=timestamp,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def _source_admission_writer_coordinate(memory_plane: MemoryPlaneService) -> tuple[int, str] | None:
    record = memory_plane.get_record("semantic_ingestion:writer_admission:current")
    if record is None:
        return None
    try:
        if record.content.get("draining", False):
            raise ValueError("semantic writer is draining and source admission is frozen")
        admission = record.content["admission"]
        return int(admission["writer_epoch"]), str(admission["admission_digest"])
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("semantic writer is draining"):
            raise
        raise ValueError("semantic writer admission coordinate is corrupt") from exc


def _profile_evidence_record(
    index: CanonicalMemoryRecord, kind: str, content: dict[str, object]
) -> CanonicalMemoryRecord:
    return index.model_copy(
        update={
            "memory_id": f"{index.memory_id}:{kind.rsplit('_', 1)[-1]}",
            "source_kind": kind,
            "content": content,
        }
    )


def _make_outcome(
    *,
    kind: str,
    reason: str | None,
    fact: GovernedSourceAdmissionFact,
    normalized_input: bytes,
    selection_digest: str,
    verification_digest: str,
    matched_corpus_case_id: str | None,
) -> ProfileSelectedPipelinePending | ProfileDisabled | ProfileUnavailable | ProfileInputOutcome:
    if kind == "selected_pipeline_pending":
        return ProfileSelectedPipelinePending(
            kind=kind,
            coordinate=BOOTSTRAP_COORDINATE,
            source_admission=fact,
            selection_digest=selection_digest,
            verification_digest=verification_digest,
        )
    if kind == "unavailable":
        return ProfileUnavailable(
            kind=kind,
            coordinate=BOOTSTRAP_COORDINATE,
            source_admission=fact,
            reason=BootstrapUnavailableReason(reason or "invalid_config"),
        )
    if kind == "disabled":
        return ProfileDisabled(
            kind=kind,
            coordinate=BOOTSTRAP_COORDINATE,
            source_admission=fact,
            disable_reason="operator_disabled",
        )
    if kind in {"unsupported_input", "abstained"} and reason is not None:
        return ProfileInputOutcome.model_validate(
            {
                "kind": kind,
                "coordinate": BOOTSTRAP_COORDINATE,
                "source_admission": fact,
                "reason": reason,
                "input_normalized_digest": normalized_input_digest(normalized_input),
                "matched_corpus_case_id": matched_corpus_case_id,
            }
        )
    raise ValueError("illegal governed-source admission bootstrap outcome")

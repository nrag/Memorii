"""Fence-bound atomic publication for graph-free source normalization.

The repository deliberately has no derivation API.  A caller must supply the
already sealed request, and the only successful return value is reloaded from
the exact generation which committed it.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Protocol

from memorii.core.memory_evolution.atomic_store import AtomicGenerationMember
from memorii.core.memory_evolution.ingestion_contracts import (
    OperationFenceBinding,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapAnalysisLaneResultV3,
    BootstrapGraphFreeInterpretationBundleV3,
    BootstrapNormalizationRequestCoreV3,
    BootstrapProposalRunPayloadV3,
    BootstrapRecoveryClaimV3,
    BootstrapRecoveryProbeResultV3,
    BootstrapRecoveryProbeV3,
    BootstrapSourceNormalizationAtomicWriteRequestV3,
    BootstrapSourceNormalizationEvidenceManifestV3,
    BootstrapSourceNormalizationRequestV3,
    BootstrapSourceNormalizationResultV3,
    BootstrapSourceProposalAlignmentV3,
    BootstrapSemanticReductionAuthorityMemberV3,
    SourceNormalizationAtomicWriteRequest,
    SourceNormalizationRecoveryAbsent,
    SourceNormalizationRecoveryFound,
    SourceNormalizationRecoveryRequest,
    SourceNormalizationRecoveryResult,
    SourceNormalizationRecoveryUnavailable,
    SourceNormalizationRecoveryValidationContext,
    SourceNormalizationResult,
    contract_digest,
    decode_semantic_contract,
    encode_semantic_contract,
)

_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_NODES = 20_000
_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_DEPTH = 128


class _AtomicSourceNormalizationStore(Protocol):
    def checkpoint_source_progress(
        self, request: SourceNormalizationAtomicWriteRequest | BootstrapSourceNormalizationAtomicWriteRequestV3
    ) -> tuple[AtomicGenerationMember, ...]: ...

    def get_operation(self, operation_fence: OperationFenceBinding): ...

    def generation_members(
        self, operation_fence: OperationFenceBinding, generation: int
    ) -> tuple[AtomicGenerationMember, ...]: ...

    def recover_source_normalization(
        self, *, request_identity: str
    ) -> tuple[int, str, tuple[AtomicGenerationMember, ...]] | None: ...

    def source_normalization_recovery_snapshot(
        self, *, request_identity: str
    ) -> tuple[int, int, str]: ...


class SourceNormalizationStage(Protocol):
    """The typed handoff required before provider graph or terminal work."""

    def normalize(
        self, request: SourceNormalizationAtomicWriteRequest | BootstrapSourceNormalizationAtomicWriteRequestV3,
    ) -> SourceNormalizationResult | BootstrapSourceNormalizationResultV3: ...


class AtomicStoreSourceNormalizationRepository:
    """Publish one sealed source-normalization closure and reload it exactly."""

    def __init__(self, *, atomic_store: _AtomicSourceNormalizationStore) -> None:
        self._atomic_store = atomic_store

    def publish_and_reload(
        self, request: SourceNormalizationAtomicWriteRequest | BootstrapSourceNormalizationAtomicWriteRequestV3,
    ) -> SourceNormalizationResult | BootstrapSourceNormalizationResultV3:
        """Commit and re-read one exact generation; never rebuild from memory."""
        try:
            request_type = (
                BootstrapSourceNormalizationAtomicWriteRequestV3
                if isinstance(request, BootstrapSourceNormalizationAtomicWriteRequestV3)
                else SourceNormalizationAtomicWriteRequest
            )
            validated = request_type.model_validate(
                request.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("source normalization request is invalid") from exc
        try:
            published = self._atomic_store.checkpoint_source_progress(validated)
            control = self._atomic_store.get_operation(validated.operation_fence_binding)
            reloaded = self._atomic_store.generation_members(
                validated.operation_fence_binding, control.generation
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("source normalization publication is unavailable") from exc
        if published != validated.members or reloaded != validated.members:
            raise ValueError("source normalization generation is partial or substituted")
        if isinstance(validated, BootstrapSourceNormalizationAtomicWriteRequestV3):
            self._validate_bootstrap_v3_member_closure(validated, reloaded)
            # V3 result bytes are carried by the V3 request/result closure,
            # not by the retired V2 result member.  Revalidating the sealed
            # response after reload prevents a V2 decoder from observing it.
            return BootstrapSourceNormalizationResultV3.model_validate(
                validated.source_normalization_result.model_dump(mode="python")
            )
        result_members = tuple(
            member for member in reloaded if member.kind == "source_normalization_result"
        )
        if len(result_members) != 1:
            raise ValueError("source normalization generation has no unique result")
        member = result_members[0]
        if member.payload_digest != sha256(member.canonical_payload).hexdigest():
            raise ValueError("source normalization result payload digest is invalid")
        try:
            result = decode_semantic_contract(
                member.canonical_payload, SourceNormalizationResult
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("source normalization result payload is invalid") from exc
        if (
            encode_semantic_contract(result) != member.canonical_payload
            or result != validated.source_normalization_result
            or result.result_digest != validated.source_normalization_result_digest
        ):
            raise ValueError("source normalization result is substituted")
        return SourceNormalizationResult.model_validate(result.model_dump(mode="python"))

    @staticmethod
    def _validate_bootstrap_v3_member_closure(
        request: BootstrapSourceNormalizationAtomicWriteRequestV3,
        members: tuple[AtomicGenerationMember, ...],
    ) -> None:
        """Strictly decode retained V3 bytes from the committed generation.

        This deliberately validates only bytes carried by the generation.  It
        does not consult a producer, route registry, or ambient artifact store;
        recovery is therefore deterministic after a lost acknowledgement.
        """
        lane_order = ("stanza", "spacy", "predicate_event_detection", "temporal_resolution")
        expected_lanes = tuple(
            (provenance.segment_id, lane)
            for provenance in request.source_normalization_request.bootstrap_analysis_provenance
            for lane in lane_order
        )
        ids = tuple(member.member_id for member in members)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError("bootstrap V3 generation member identity order is invalid")
        if any(member.payload_digest != sha256(member.canonical_payload).hexdigest() for member in members):
            raise ValueError("bootstrap V3 generation member digest is invalid")

        def one(kind: str) -> AtomicGenerationMember:
            matches = tuple(member for member in members if member.kind == kind)
            if len(matches) != 1:
                raise ValueError(f"bootstrap V3 requires exactly one {kind}")
            return matches[0]

        def decode_one(kind: str, model: type):
            member = one(kind)
            try:
                value = decode_semantic_contract(
                    member.canonical_payload,
                    model,
                    max_nodes=_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_NODES,
                    max_depth=_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_DEPTH,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"bootstrap V3 {kind} bytes are invalid") from exc
            if encode_semantic_contract(value) != member.canonical_payload:
                raise ValueError(f"bootstrap V3 {kind} bytes are noncanonical")
            return value

        proposal = decode_one("bootstrap_proposal_run_payload", BootstrapProposalRunPayloadV3)
        lane_members = tuple(member for member in members if member.kind == "bootstrap_analysis_lane_result")
        if len(lane_members) != len(expected_lanes):
            raise ValueError("bootstrap V3 lane cardinality is incomplete")
        try:
            lanes = tuple(
                decode_semantic_contract(
                    member.canonical_payload,
                    BootstrapAnalysisLaneResultV3,
                    max_nodes=_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_NODES,
                    max_depth=_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_DEPTH,
                )
                for member in lane_members
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("bootstrap V3 lane bytes are invalid") from exc
        if (
            tuple((lane.segment_id, lane.lane) for lane in lanes) != expected_lanes
            or tuple(encode_semantic_contract(lane) for lane in lanes)
            != tuple(member.canonical_payload for member in lane_members)
            or proposal != request.bootstrap_proposal_run_payload
            or lanes != request.bootstrap_analysis_lane_results
        ):
            raise ValueError("bootstrap V3 retained member closure is substituted")
        core = decode_one(
            "bootstrap_normalization_request_core", BootstrapNormalizationRequestCoreV3
        )
        reduction = decode_one(
            "bootstrap_semantic_reduction_authority",
            BootstrapSemanticReductionAuthorityMemberV3,
        )
        if (
            core.proposal_payload != proposal
            or core.lane_results != lanes
            or core.source_alignment
            != request.source_normalization_request.source_alignment
            or core.recovery_key != request.bootstrap_recovery_key
            or reduction.normalization_request_core != core
            or reduction.execution_policy
            != request.bootstrap_graph_normalization_authority.execution_policy
            or reduction.capability_registry
            != request.bootstrap_graph_normalization_authority.capability_registry
        ):
            raise ValueError("bootstrap V3 reduction authority is substituted")

    @staticmethod
    def validate_bootstrap_v3_reloaded_members(
        members: tuple[AtomicGenerationMember, ...],
    ) -> BootstrapSourceNormalizationResultV3:
        """Validate a V3 generation without a caller-owned request object."""
        v3_kinds = {
            "bootstrap_proposal_run_payload", "bootstrap_analysis_lane_result",
            "bootstrap_graph_free_interpretation_bundle", "bootstrap_source_proposal_alignment",
        }
        ids = tuple(member.member_id for member in members)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError("bootstrap V3 generation member identity order is invalid")
        if not any(member.kind in v3_kinds for member in members):
            # V2-only carrier tags are deliberately not a fallback decoder.
            raise ValueError("bootstrap V3 retained member bytes are invalid")
        if any(member.payload_digest != sha256(member.canonical_payload).hexdigest() for member in members):
            raise ValueError("bootstrap V3 generation member digest is invalid")

        def one(kind: str) -> AtomicGenerationMember:
            found = tuple(member for member in members if member.kind == kind)
            if len(found) != 1:
                raise ValueError(f"bootstrap V3 requires exactly one {kind}")
            return found[0]

        def decode_bounded(kind: str, model: type) -> object:
            return decode_semantic_contract(
                one(kind).canonical_payload,
                model,
                max_nodes=_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_NODES,
                max_depth=_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_DEPTH,
            )

        try:
            proposal = decode_bounded(
                "bootstrap_proposal_run_payload", BootstrapProposalRunPayloadV3
            )
            bundle = decode_bounded(
                "bootstrap_graph_free_interpretation_bundle",
                BootstrapGraphFreeInterpretationBundleV3,
            )
            alignment = decode_bounded(
                "bootstrap_source_proposal_alignment",
                BootstrapSourceProposalAlignmentV3,
            )
            result = decode_bounded(
                "bootstrap_source_normalization_result", BootstrapSourceNormalizationResultV3
            )
            request = decode_bounded(
                "bootstrap_source_normalization_request",
                BootstrapSourceNormalizationRequestV3,
            )
            manifest = decode_bounded(
                "bootstrap_source_normalization_evidence_manifest",
                BootstrapSourceNormalizationEvidenceManifestV3,
            )
            lanes = tuple(
                decode_semantic_contract(
                    member.canonical_payload,
                    BootstrapAnalysisLaneResultV3,
                    max_nodes=_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_NODES,
                    max_depth=_BOOTSTRAP_V3_RECOVERY_MAX_TYPED_DEPTH,
                )
                for member in members if member.kind == "bootstrap_analysis_lane_result"
            )
            core = decode_bounded(
                "bootstrap_normalization_request_core", BootstrapNormalizationRequestCoreV3
            )
            reduction = decode_bounded(
                "bootstrap_semantic_reduction_authority",
                BootstrapSemanticReductionAuthorityMemberV3,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("bootstrap V3 retained member bytes are invalid") from exc
        lane_order = ("stanza", "spacy", "predicate_event_detection", "temporal_resolution")
        provenance = proposal.bootstrap_analysis_provenances
        expected_lanes = tuple((item.segment_id, lane) for item in provenance for lane in lane_order)
        if (
            not provenance
            or proposal.bootstrap_analysis_provenances != provenance
            or tuple((lane.segment_id, lane.lane) for lane in lanes) != expected_lanes
            or bundle.lane_result_digests != tuple(lane.result_digest for lane in lanes)
            or alignment.interpretation_bundle_digest != bundle.bundle_digest
            or alignment.bootstrap_analysis_provenances != provenance
            or result.interpretation_bundle_digest != bundle.bundle_digest
            or result.source_alignment_digest != alignment.alignment_digest
            or result.bootstrap_analysis_provenance != provenance
            or result.source_normalization_request_digest != request.request_digest
            or result.evidence_manifest != manifest
            or request.proposal_run.proposal_payload != proposal
            or request.interpretation_bundle != bundle
            or request.source_alignment != alignment
            or core.proposal_payload != proposal
            or core.lane_results != lanes
            or core.interpretation_bundle != bundle
            or core.source_alignment != alignment
            or reduction.normalization_request_core != core
        ):
            raise ValueError("bootstrap V3 reloaded member closure is substituted")
        if encode_semantic_contract(result) != one("bootstrap_source_normalization_result").canonical_payload:
            raise ValueError("bootstrap V3 result bytes are noncanonical")
        if (
            encode_semantic_contract(core)
            != one("bootstrap_normalization_request_core").canonical_payload
            or encode_semantic_contract(reduction)
            != one("bootstrap_semantic_reduction_authority").canonical_payload
        ):
            raise ValueError("bootstrap V3 reduction authority bytes are noncanonical")
        return BootstrapSourceNormalizationResultV3.model_validate(result.model_dump(mode="python"))

    def normalize(
        self, request: SourceNormalizationAtomicWriteRequest | BootstrapSourceNormalizationAtomicWriteRequestV3,
    ) -> SourceNormalizationResult | BootstrapSourceNormalizationResultV3:
        """Expose the repository as the concrete non-deriving stage owner."""
        return self.publish_and_reload(request)

    def recover(
        self,
        *,
        request: SourceNormalizationRecoveryRequest,
        context: SourceNormalizationRecoveryValidationContext,
    ) -> SourceNormalizationRecoveryResult:
        """Reload a committed normalization result without reconstruction.

        The execution owner supplies only scalar, already-validated recovery
        bindings.  This boundary validates every join before asking the store
        for an index entry, so a malformed retry has no persistence read.
        """
        try:
            request = SourceNormalizationRecoveryRequest.model_validate(
                request.model_dump(mode="python")
            )
            context = SourceNormalizationRecoveryValidationContext.model_validate(
                context.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError):
            raise ValueError("source normalization recovery request is invalid") from None
        if not self._recovery_context_matches(request, context):
            return self._unavailable(request, "context_mismatch")
        try:
            entry = self._atomic_store.recover_source_normalization(
                request_identity=request.request_identity
            )
            observed_operation, observed_artifact, snapshot_digest = (
                self._atomic_store.source_normalization_recovery_snapshot(
                    request_identity=request.request_identity
                )
            )
        except (AttributeError, TypeError, ValueError):
            return self._unavailable(request, "storage_unavailable")
        if entry is None:
            if (
                observed_operation != request.expected_operation_generation
                or observed_artifact != request.expected_artifact_generation
            ):
                return self._unavailable(request, "stale_generation")
            absence_body = {
                "request_identity": request.request_identity,
                "observed_operation_generation": observed_operation,
                "observed_artifact_generation": observed_artifact,
                "store_snapshot_digest": snapshot_digest,
            }
            body = {
                "kind": "absent", "request_identity": request.request_identity,
                "request_digest": request.request_digest,
                "expected_operation_generation": request.expected_operation_generation,
                "expected_artifact_generation": request.expected_artifact_generation,
                "observed_operation_generation": observed_operation,
                "observed_artifact_generation": observed_artifact,
                "store_snapshot_digest": snapshot_digest,
                "index_absence_digest": contract_digest(
                    b"memorii.semantic-ingestion.source-normalization-recovery-index-absence.v1", absence_body
                ),
            }
            return SourceNormalizationRecoveryAbsent(
                **body,
                response_digest=contract_digest(
                    b"memorii.semantic-ingestion.source-normalization-recovery-absent.v1", body
                ),
            )
        generation, atomic_request_digest, members = entry
        if generation < 1:
            return self._unavailable(request, "generation_corrupt")
        try:
            result = self._result_from_members(members)
        except ValueError:
            return self._unavailable(request, "generation_incomplete")
        index_body = {"request_identity": request.request_identity, "publication_generation": generation}
        body = {
            "kind": "found", "request_identity": request.request_identity,
            "request_digest": request.request_digest, "publication_generation": generation,
            "recovery_index_digest": contract_digest(
                b"memorii.semantic-ingestion.source-normalization-recovery-index.v1", index_body
            ),
            "atomic_request_digest": atomic_request_digest,
            "result_digest": result.result_digest, "result": result,
        }
        return SourceNormalizationRecoveryFound(
            **body,
            response_digest=contract_digest(
                b"memorii.semantic-ingestion.source-normalization-recovery-found.v1", body
            ),
        )

    @staticmethod
    def _recovery_context_matches(
        request: SourceNormalizationRecoveryRequest,
        context: SourceNormalizationRecoveryValidationContext,
    ) -> bool:
        return (
            request.source_id == context.invocation.source_id == context.handoff.source_id
            and request.source_digest == context.invocation.source_digest == context.handoff.source_digest
            and request.preparation_fingerprint == context.invocation.preparation_fingerprint
            # Bootstrap markers retain the fenced pending-operation identifier;
            # source-normalization requests retain the public operation ID.
            # The execution owner validates that fence join before this
            # repository receives the scalar recovery bindings.
            and request.operation_id == context.invocation.operation_id
            and request.operation_fence_digest == context.invocation.operation_fence_digest == context.handoff.operation_fence_digest
            and request.derivation_authority_digest == context.authority.derivation_authority_digest
            and request.publication_coordinate_digest == context.authority.publication_coordinate_digest
            and request.expected_operation_generation == context.authority.expected_operation_generation
            and request.expected_artifact_generation == context.authority.expected_artifact_generation
        )

    @staticmethod
    def _unavailable(
        request: SourceNormalizationRecoveryRequest, reason: str
    ) -> SourceNormalizationRecoveryUnavailable:
        reason_body = {
            "kind": "publication_unavailable", "request_identity": request.request_identity,
            "request_digest": request.request_digest, "reason": reason,
        }
        reason_digest = contract_digest(
            b"memorii.semantic-ingestion.source-normalization-recovery-unavailable.v1", reason_body
        )
        body = {**reason_body, "reason_digest": reason_digest}
        return SourceNormalizationRecoveryUnavailable(
            **body,
            response_digest=contract_digest(
                b"memorii.semantic-ingestion.source-normalization-recovery-unavailable-response.v1", body
            ),
        )

    @staticmethod
    def _result_from_members(members: tuple[AtomicGenerationMember, ...]) -> SourceNormalizationResult:
        result_members = tuple(member for member in members if member.kind == "source_normalization_result")
        if len(result_members) != 1:
            raise ValueError("source normalization generation has no unique result")
        member = result_members[0]
        if member.payload_digest != sha256(member.canonical_payload).hexdigest():
            raise ValueError("source normalization result payload digest is invalid")
        try:
            result = decode_semantic_contract(member.canonical_payload, SourceNormalizationResult)
        except (TypeError, ValueError) as exc:
            raise ValueError("source normalization result payload is invalid") from exc
        if encode_semantic_contract(result) != member.canonical_payload:
            raise ValueError("source normalization result is substituted")
        return SourceNormalizationResult.model_validate(result.model_dump(mode="python"))


class AtomicStoreBootstrapRecoveryClaimRepository:
    """Production recovery probe owner backed by the generation store's CAS."""

    def __init__(self, *, atomic_store: object) -> None:
        self._atomic_store = atomic_store

    def probe(self, *, probe: BootstrapRecoveryProbeV3, server_time: datetime,
              monotonic_tick: int) -> BootstrapRecoveryProbeResultV3:
        return self._atomic_store.probe_bootstrap_v3_recovery(
            probe=probe, server_time=server_time, monotonic_tick=monotonic_tick
        )

    def renew_or_abort(self, *, claim: BootstrapRecoveryClaimV3, server_time: datetime,
                       monotonic_tick: int):
        return self._atomic_store.renew_or_abort_bootstrap_v3_recovery(
            claim=claim, server_time=server_time, monotonic_tick=monotonic_tick
        )

    def reload_found(self, *, recovery_key_digest: str) -> BootstrapSourceNormalizationResultV3 | None:
        """Reload a committed V3 result; never reconstruct or re-run a lane."""
        try:
            recovered = self._atomic_store.recover_bootstrap_v3_source_normalization(
                recovery_key_digest=recovery_key_digest
            )
            if recovered is None:
                return None
            _generation, _request_digest, result_digest, members = recovered
            result = AtomicStoreSourceNormalizationRepository.validate_bootstrap_v3_reloaded_members(members)
            return result if result.result_digest == result_digest else None
        except (AttributeError, TypeError, ValueError):
            return None

    def reload_bootstrap_recovery_replay_v3(self, *, recovery_key_digest: str):
        """Return the exact retained V3 replay closure for graph coordination."""
        return self._atomic_store.reload_bootstrap_recovery_replay_v3(
            recovery_key_digest=recovery_key_digest
        )


__all__ = [
    "AtomicStoreSourceNormalizationRepository",
    "SourceNormalizationStage",
    "AtomicStoreBootstrapRecoveryClaimRepository",
]

"""Fenced semantic ingestion terminal publication through the canonical writer-safe preplanning atomic store."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from hashlib import sha256
from typing import Literal

from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationMember,
    AuthorizationReadSetPrecondition,
    CommittedGroupAtomicWriteRequest,
    NonCommittingGroupAtomicWriteRequest,
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
    SourceCheckpointAtomicWriteRequest,
    SourceFinalizationAtomicWriteRequest,
    generation_request_digest,
)
from memorii.core.memory_evolution.ingestion_contracts import OperationFenceBinding, encode_typed_value
from memorii.core.memory_evolution.writer_admission import SemanticWriterCommitBinding
from memorii.core.semantic_ingestion.authorization import (
    SemanticAuthorizationAuthorityError,
    SemanticAuthorizationAuthorityRepository,
)
from memorii.core.semantic_ingestion.contracts import (
    ClaimAssertion,
    SemanticArtifactClosure,
    SemanticAuthorizationReadSetVerifier,
    SemanticEffectGroupResult,
    SemanticExecutionRetryPlan,
    SemanticGraphDelta,
    SemanticLifecycleTransition,
    SemanticObservationDelta,
    SemanticRecoveryAuthorityBinding,
    SemanticRetryableProgress,
    SemanticTerminalOutcome,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.core.semantic_ingestion.event_replay import (
    SemanticMemoryEventBatch,
    encode_semantic_memory_event_batch,
    semantic_replay_dependency_digests,
)

_SemanticMemberKind = Literal[
    "progress",
    "group_result",
    "observation_delta",
    "graph_delta",
    "event_batch",
    "terminal_operation",
    "source_summary",
    "source_result",
    "lifecycle",
    "artifact_index",
    "artifact_closure",
    "plan",
    "planning_artifact",
    "independence_certificate",
    "planning_authorization",
    "authorization_read_set",
    "terminal_artifact",
    "recovery_authority_binding",
    "stage_artifact",
]
_SemanticLifecycleReason = Literal[
    "missing_language_declaration",
    "untrusted_language",
    "language_mismatch",
    "non_english_language",
    "mixed_residue",
    "unsupported_grammar",
    "extractor_abstained",
    "retry_budget_exhausted",
]


class SemanticAuthorizationReadSetError(PreplanningStoreError):
    """Mutable authorization changed after the terminal plan was sealed."""


class SemanticTerminalPersistenceService:
    """Publish exactly one terminal semantic ingestion closure and recover exact lost acks."""

    def __init__(
        self,
        *,
        atomic_store: SemanticIngestionAtomicStore,
        writer_binding_provider: Callable[[], SemanticWriterCommitBinding],
        authorization_repository: SemanticAuthorizationAuthorityRepository | None = None,
    ) -> None:
        self._store = atomic_store
        self._writer_binding_provider = writer_binding_provider
        self._authorization_repository = authorization_repository

    def open_lease_session(self, *, fence: OperationFenceBinding) -> SemanticIngestionLeaseSession:
        """Acquire the renewable owner used across proposal through finalization."""
        return SemanticIngestionLeaseSession(
            atomic_store=self._store,
            writer_binding_provider=self._writer_binding_provider,
            fence=fence,
        )

    def recover_terminal_artifact(
        self,
        *,
        fence: OperationFenceBinding,
    ) -> SemanticTerminalOutcome | None:
        """Reload the newest complete terminal artifact without learned-stage replay."""
        control = self._store.get_operation(fence)
        for generation in range(control.generation, 1, -1):
            members = self._store.generation_members(fence, generation)
            artifacts = tuple(member for member in members if member.kind == "terminal_artifact")
            if not artifacts:
                continue
            if len(artifacts) != 1:
                raise ValueError("semantic ingestion generation has duplicate terminal artifacts")
            terminal = decode_semantic_contract(
                artifacts[0].canonical_payload,
                SemanticTerminalOutcome,
            )
            if terminal.operation_id != fence.operation_id:
                raise ValueError("semantic ingestion terminal artifact operation binding is invalid")
            return terminal
        return None

    def recover_execution_plan(
        self,
        *,
        fence: OperationFenceBinding,
    ) -> SemanticExecutionRetryPlan | None:
        """Reload the unique authenticated plan used for no-redelivery recovery."""

        control = self._store.get_operation(fence)
        recovered: SemanticExecutionRetryPlan | None = None
        for generation in range(2, control.generation + 1):
            plans = tuple(
                member
                for member in self._store.generation_members(fence, generation)
                if member.kind == "execution_plan"
            )
            if not plans:
                continue
            if len(plans) != 1 or recovered is not None:
                raise ValueError("semantic ingestion operation has no unique execution retry plan")
            recovered = decode_semantic_contract(plans[0].canonical_payload, SemanticExecutionRetryPlan)
            recovered.validate_for_fence(fence)
        return recovered

    def recover_recovery_authority_binding(
        self,
        *,
        fence: OperationFenceBinding,
    ) -> SemanticRecoveryAuthorityBinding | None:
        control = self._store.get_operation(fence)
        recovered: SemanticRecoveryAuthorityBinding | None = None
        for generation in range(2, control.generation + 1):
            bindings = tuple(
                member
                for member in self._store.generation_members(fence, generation)
                if member.kind == "recovery_authority_binding"
            )
            if not bindings:
                continue
            if len(bindings) != 1 or recovered is not None:
                raise ValueError("semantic ingestion operation has no unique recovery authority binding")
            recovered = decode_semantic_contract(bindings[0].canonical_payload, SemanticRecoveryAuthorityBinding)
            if recovered.operation_id != fence.operation_id:
                raise ValueError("semantic ingestion recovery authority binding operation is invalid")
        return recovered

    def persist(
        self,
        *,
        fence: OperationFenceBinding,
        terminal: SemanticTerminalOutcome,
        authorization_verifier: SemanticAuthorizationReadSetVerifier | None = None,
    ) -> None:
        SemanticTerminalOutcome.model_validate(terminal.model_dump(mode="python"))
        if terminal.operation_id != fence.operation_id:
            raise ValueError("semantic ingestion terminal does not bind the admitted source operation")
        if any(
            analysis.source_id != fence.source_id or analysis.source_digest != fence.source_digest
            for analysis in terminal.source_analyses
        ):
            raise ValueError("semantic analysis does not bind the admitted source")
        source_authority_evidence = (
            *(
                analysis.source_authority_evidence
                for analysis in terminal.source_analyses
                if analysis.source_authority_evidence is not None
            ),
            *(
                operation.source_authority_evidence
                for operation in terminal.sealed_operations
                if operation.source_authority_evidence is not None
            ),
            *(
                carrier.source_authority_evidence
                for carrier in terminal.accepted_carriers
                if isinstance(carrier, ClaimAssertion) and carrier.source_authority_evidence is not None
            ),
        )
        if any(
            evidence.source_id != fence.source_id or evidence.source_digest != fence.source_digest
            for evidence in source_authority_evidence
        ):
            raise ValueError("semantic source authority does not bind the admitted source")
        control = self._store.get_operation(fence)
        if control.state == "terminal":
            self._verify_completed_terminal(fence=fence, terminal=terminal, generation=control.generation)
            return
        writer = self._writer_binding_provider()
        if control.writer_binding != writer:
            raise ValueError("semantic ingestion terminal writer does not match the admitted source")
        if control.lease is not None and (
            control.lease.owner_id != "semantic-ingestion-pipeline"
            or control.lease.execution_token != f"semantic-ingestion:{fence.operation_fence_id}"
        ):
            raise ValueError("semantic ingestion terminal operation is leased by a different execution")
        # Host conflict authority must be valid before this call obtains a
        # lease or records the planned checkpoint.  The store rederives and
        # CAS-validates this exact input in the final terminal transaction.
        if not control.group_result_digests:
            self._store.preflight_terminal_conflict_authority(
                operation_fence=fence,
                terminal=terminal,
                writer_binding=writer,
            )
        # Acquisition is deliberately unconditional. The store returns a live
        # matching lease idempotently and performs fenced stale-owner recovery,
        # including an expired lease held by this same logical owner.
        control = self._store.acquire_lease(
            operation_fence=fence,
            writer_binding=writer,
            execution_token=f"semantic-ingestion:{fence.operation_fence_id}",
            owner_id="semantic-ingestion-pipeline",
            duration=timedelta(seconds=30),
        )
        if control.state == "terminal":
            self._verify_completed_terminal(fence=fence, terminal=terminal, generation=control.generation)
            return
        if control.state == "lease_recovery_exhausted":
            raise ValueError("semantic ingestion lease recovery exhausted")
        lease = self._store.lease_binding(control)
        artifact_closure = SemanticArtifactClosure.create(terminal)
        self._verify_commit_authorization(
            terminal=terminal,
            authorization_verifier=authorization_verifier,
        )
        authorization_precondition = self._authorization_precondition(
            fence=fence,
            terminal=terminal,
            authorization_verifier=authorization_verifier,
        )
        if control.state == "preplanning":
            for _ in range(4):
                control = self._store.get_operation(fence)
                if control.state == "terminal":
                    self._verify_completed_terminal(fence=fence, terminal=terminal, generation=control.generation)
                    return
                if control.state == "planned":
                    self._verify_planned_closure(
                        fence=fence,
                        terminal=terminal,
                        closure=artifact_closure,
                        generation=control.generation,
                    )
                    break
                control = self._store.acquire_lease(
                    operation_fence=fence,
                    writer_binding=writer,
                    execution_token=f"semantic-ingestion:{fence.operation_fence_id}",
                    owner_id="semantic-ingestion-pipeline",
                    duration=timedelta(seconds=30),
                )
                lease = self._store.lease_binding(control)
                checkpoint = SourceCheckpointAtomicWriteRequest(
                    operation_fence_binding=fence,
                    operation_lease_binding=lease,
                    writer_commit_binding=writer,
                    expected_operation_generation=control.generation,
                    expected_artifact_generation=control.generation,
                    members=self._checkpoint_members(terminal, artifact_closure, writer),
                    required_artifact_digests=(),
                    request_digest="0" * 64,
                    progress_state="planned",
                )
                try:
                    self._store.checkpoint_source_progress(self._seal(checkpoint))
                except PreplanningStoreError:
                    continue
            else:
                raise PreplanningStoreError("semantic ingestion planned checkpoint retry budget exhausted")
            control = self._store.get_operation(fence)
            if control.state == "terminal":
                self._verify_completed_terminal(fence=fence, terminal=terminal, generation=control.generation)
                return
            control = self._store.acquire_lease(
                operation_fence=fence,
                writer_binding=writer,
                execution_token=f"semantic-ingestion:{fence.operation_fence_id}",
                owner_id="semantic-ingestion-pipeline",
                duration=timedelta(seconds=30),
            )
            lease = self._store.lease_binding(control)
        group_result = SemanticEffectGroupResult.create(terminal=terminal, artifact_closure=artifact_closure)
        if not control.group_result_digests:
            unmaterialized_graph_delta = (
                SemanticGraphDelta.create(terminal)
                if terminal.status == "accepted"
                else None
            )
            committed_at = self._store.authoritative_commit_timestamp()
            last_group_error: PreplanningStoreError | None = None
            for _ in range(4):
                control = self._store.get_operation(fence)
                if control.state == "terminal":
                    self._verify_completed_terminal(fence=fence, terminal=terminal, generation=control.generation)
                    return
                if control.group_result_digests:
                    self._verify_group_result(fence=fence, terminal=terminal, generation=control.generation)
                    break
                if control.state != "planned":
                    raise PreplanningStoreError("semantic ingestion terminal group requires planned progress")
                # Rebuild against this exact control snapshot.  A raced
                # publication must never reuse authority from an older read.
                semantic_conflict_authority = self._store.preflight_terminal_conflict_authority(
                    operation_fence=fence,
                    terminal=terminal,
                    writer_binding=writer,
                )
                control = self._store.acquire_lease(
                    operation_fence=fence,
                    writer_binding=writer,
                    execution_token=f"semantic-ingestion:{fence.operation_fence_id}",
                    owner_id="semantic-ingestion-pipeline",
                    duration=timedelta(seconds=30),
                )
                lease = self._store.lease_binding(control)
                common = {
                    "operation_fence_binding": fence,
                    "operation_lease_binding": lease,
                    "writer_commit_binding": writer,
                    "expected_operation_generation": control.generation,
                    "expected_artifact_generation": control.generation,
                    "required_artifact_digests": (),
                    "request_digest": "0" * 64,
                    "expected_observation_revision": control.observation_revision,
                    "observation_revision_after": self._next_revision(
                        b"memorii.semantic-ingestion.observation-revision.v1",
                        control.observation_revision,
                        terminal.terminal_digest,
                    ),
                }
                if unmaterialized_graph_delta is not None:
                    graph_delta = self._store.enrich_identity_graph_delta(
                        unmaterialized_graph_delta,
                        terminal,
                        operation_fence_id=fence.operation_fence_id,
                        graph_revision_before=control.graph_revision,
                        graph_revision_after=control.graph_revision,
                        committed_at=committed_at,
                    )
                    graph_revision_after = self._next_revision(
                        b"memorii.semantic-ingestion.graph-revision.v1",
                        control.graph_revision,
                        graph_delta.delta_digest,
                    )
                    graph_delta = self._store.enrich_identity_graph_delta(
                        unmaterialized_graph_delta,
                        terminal,
                        operation_fence_id=fence.operation_fence_id,
                        graph_revision_before=control.graph_revision,
                        graph_revision_after=graph_revision_after,
                        committed_at=committed_at,
                    )
                    observation = SemanticObservationDelta.create(
                        terminal=terminal,
                        graph_delta=graph_delta,
                    )
                    event_batch = self._store.prepare_semantic_event_batch(
                        graph_delta=graph_delta,
                        operation_fence=fence,
                        writer_binding=writer,
                        graph_revision_before=control.graph_revision,
                        graph_revision_after=graph_revision_after,
                        committed_at=committed_at,
                    )
                    request = CommittedGroupAtomicWriteRequest(
                        **common,
                        members=self._committed_group_members(
                            terminal,
                            artifact_closure,
                            group_result,
                            graph_delta,
                            event_batch,
                            observation,
                        ),
                        expected_graph_revision=control.graph_revision,
                        expected_effective_read_set_digest=control.effective_read_set_digest,
                        graph_revision_after=graph_revision_after,
                        authorization_precondition=authorization_precondition,
                        semantic_conflict_authority=semantic_conflict_authority,
                    )
                else:
                    observation = SemanticObservationDelta.create(
                        terminal=terminal,
                        graph_delta=None,
                    )
                    request = NonCommittingGroupAtomicWriteRequest(
                        **common,
                        members=self._noncommitting_group_members(
                            terminal, artifact_closure, group_result, observation
                        ),
                        authorization_precondition=authorization_precondition,
                    )
                if unmaterialized_graph_delta is not None:
                    self._verify_commit_authorization(
                        terminal=terminal,
                        authorization_verifier=authorization_verifier,
                    )
                try:
                    self._store.persist_terminal_group(self._seal(request))
                except PreplanningStoreError as exc:
                    last_group_error = exc
                    continue
            else:
                raise PreplanningStoreError(
                    "semantic ingestion terminal-group retry budget exhausted"
                ) from last_group_error
            control = self._store.get_operation(fence)
            if control.state == "terminal":
                self._verify_completed_terminal(fence=fence, terminal=terminal, generation=control.generation)
                return
            control = self._store.acquire_lease(
                operation_fence=fence,
                writer_binding=writer,
                execution_token=f"semantic-ingestion:{fence.operation_fence_id}",
                owner_id="semantic-ingestion-pipeline",
                duration=timedelta(seconds=30),
            )
            lease = self._store.lease_binding(control)
        else:
            self._verify_group_result(fence=fence, terminal=terminal, generation=control.generation)
        committed_graph_delta = self._recover_committed_graph_delta(
            fence=fence,
            generation=control.generation,
        )
        final = SourceFinalizationAtomicWriteRequest(
            operation_fence_binding=fence,
            operation_lease_binding=lease,
            writer_commit_binding=writer,
            expected_operation_generation=control.generation,
            expected_artifact_generation=control.generation,
            members=self._final_members(
                terminal,
                artifact_closure,
                graph_delta=committed_graph_delta,
            ),
            required_artifact_digests=(),
            request_digest="0" * 64,
            source_summary_kind="graph_bound",
            expected_group_result_digests=control.group_result_digests,
        )
        self._store.finalize_source(self._seal(final))

    @staticmethod
    def _verify_commit_authorization(
        *,
        terminal: SemanticTerminalOutcome,
        authorization_verifier: SemanticAuthorizationReadSetVerifier | None,
    ) -> None:
        read_set = terminal.authorization_read_set
        if read_set is None:
            if terminal.status == "accepted":
                raise SemanticAuthorizationReadSetError("accepted terminal has no authorization read set")
            return
        if authorization_verifier is None or not authorization_verifier.verify_current(
            read_set, use_point="pre_commit"
        ):
            raise SemanticAuthorizationReadSetError("semantic ingestion authorization read set is stale at commit")

    def _authorization_precondition(
        self,
        *,
        fence: OperationFenceBinding,
        terminal: SemanticTerminalOutcome,
        authorization_verifier: SemanticAuthorizationReadSetVerifier | None,
    ) -> AuthorizationReadSetPrecondition | None:
        read_set = terminal.authorization_read_set
        if read_set is None:
            return None
        if self._authorization_repository is None:
            raise SemanticAuthorizationReadSetError(
                "semantic ingestion same-store authorization repository is unavailable"
            )
        take_snapshot = getattr(authorization_verifier, "take_precommit_snapshot", None)
        if callable(take_snapshot):
            snapshot = take_snapshot(read_set)
            if snapshot is None:
                raise SemanticAuthorizationReadSetError(
                    "semantic ingestion precommit authorization snapshot is unavailable"
                )
            return AuthorizationReadSetPrecondition(
                authority_record_id=snapshot.authority_record_id,
                expected_authority_revision=snapshot.authority_revision,
                expected_coordinates_digest=snapshot.authority_coordinates_digest,
                expected_record_digest=snapshot.authority_record_digest,
            )
        scope_id = self._authorization_repository.scope_id(source_id=fence.source_id, source_digest=fence.source_digest)
        try:
            return self._authorization_repository.require_current(
                authority_scope_id=scope_id,
                read_set=read_set,
            )
        except SemanticAuthorizationAuthorityError as exc:
            raise SemanticAuthorizationReadSetError(str(exc)) from exc

    def _verify_completed_terminal(
        self, *, fence: OperationFenceBinding, terminal: SemanticTerminalOutcome, generation: int
    ) -> None:
        members = self._store.generation_members(fence, generation)
        source_results = tuple(value for value in members if value.kind == "source_result")
        if len(source_results) != 1:
            raise ValueError("completed semantic ingestion source has no unique source result")
        recovered = decode_semantic_contract(source_results[0].canonical_payload, SemanticTerminalOutcome)
        if recovered != terminal:
            raise ValueError("completed semantic ingestion source result differs from retry terminal")

    def _verify_group_result(
        self, *, fence: OperationFenceBinding, terminal: SemanticTerminalOutcome, generation: int
    ) -> None:
        results = tuple(
            value
            for candidate_generation in range(2, generation + 1)
            for value in self._store.generation_members(fence, candidate_generation)
            if value.kind == "group_result"
        )
        if len(results) != 1:
            raise ValueError("planned semantic ingestion source has no unique group result")
        recovered = decode_semantic_contract(results[0].canonical_payload, SemanticEffectGroupResult)
        if recovered.terminal != terminal:
            raise ValueError("planned semantic ingestion group result differs from retry terminal")

    def _recover_committed_graph_delta(
        self,
        *,
        fence: OperationFenceBinding,
        generation: int,
    ) -> SemanticGraphDelta | None:
        members = tuple(
            member
            for candidate_generation in range(2, generation + 1)
            for member in self._store.generation_members(
                fence, candidate_generation
            )
            if member.kind == "graph_delta"
        )
        if not members:
            return None
        if len(members) != 1:
            raise ValueError("semantic ingestion source has duplicate graph deltas")
        return decode_semantic_contract(
            members[0].canonical_payload,
            SemanticGraphDelta,
        )

    def _verify_planned_closure(
        self,
        *,
        fence: OperationFenceBinding,
        terminal: SemanticTerminalOutcome,
        closure: SemanticArtifactClosure,
        generation: int,
    ) -> None:
        planning_generations = tuple(
            self._store.generation_members(fence, candidate_generation)
            for candidate_generation in range(2, generation + 1)
            if any(member.kind == "plan" for member in self._store.generation_members(fence, candidate_generation))
        )
        if len(planning_generations) != 1:
            raise ValueError("planned semantic ingestion source has no unique planning generation")
        members = planning_generations[0]
        closures = tuple(value for value in members if value.kind == "artifact_closure")
        if len(closures) != 1:
            raise ValueError("planned semantic ingestion source has no unique artifact closure")
        recovered = decode_semantic_contract(closures[0].canonical_payload, SemanticArtifactClosure)
        if recovered != closure:
            raise ValueError("planned semantic ingestion artifact closure differs from retry terminal")
        terminal_artifacts = tuple(value for value in members if value.kind == "terminal_artifact")
        if len(terminal_artifacts) != 1 or terminal_artifacts[0].canonical_payload != encode_semantic_contract(
            terminal
        ):
            raise ValueError("planned semantic ingestion terminal artifact differs from retry terminal")
        read_sets = tuple(value for value in members if value.kind == "authorization_read_set")
        expected_read_set = (
            encode_semantic_contract(terminal.authorization_read_set)
            if terminal.authorization_read_set is not None
            else encode_typed_value(None)
        )
        if len(read_sets) != 1 or read_sets[0].canonical_payload != expected_read_set:
            raise ValueError("planned semantic ingestion authorization read set differs from retry terminal")

    @staticmethod
    def _checkpoint_members(
        terminal: SemanticTerminalOutcome,
        closure: SemanticArtifactClosure,
        writer: SemanticWriterCommitBinding,
    ) -> tuple[AtomicGenerationMember, ...]:
        lifecycle = (
            SemanticLifecycleTransition.accepted_candidate(
                operation_id=terminal.operation_id,
                candidate_digest=terminal.candidates[0].candidate_digest,
            )
            if terminal.status == "accepted"
            else None
        )
        items: list[tuple[_SemanticMemberKind, bytes]] = [
            ("artifact_closure", encode_semantic_contract(closure)),
            (
                "artifact_index",
                encode_typed_value({"terminal": terminal.terminal_digest, "closure": closure.closure_digest}),
            ),
            (
                "authorization_read_set",
                (
                    encode_semantic_contract(terminal.authorization_read_set)
                    if terminal.authorization_read_set is not None
                    else encode_typed_value(None)
                ),
            ),
            (
                "independence_certificate",
                encode_typed_value(
                    {"sealed_operations": tuple(value.sealed_operation_digest for value in terminal.sealed_operations)}
                ),
            ),
            (
                "plan",
                encode_typed_value(
                    {
                        "kind": "semantic_terminal_committed"
                        if terminal.status == "accepted"
                        else "semantic_terminal_non_committing"
                    }
                ),
            ),
            (
                "planning_artifact",
                encode_typed_value(
                    {
                        "operation_id": terminal.operation_id,
                        "terminal_digest": terminal.terminal_digest,
                        "execution_lineage": (
                            terminal.execution_lineage.model_dump(mode="python")
                            if terminal.execution_lineage is not None
                            else None
                        ),
                    }
                ),
            ),
            (
                "planning_authorization",
                encode_typed_value(
                    {
                        "writer_admission_digest": writer.admission_digest,
                        "policy_bundle_digest": (
                            terminal.arbitration_policy_bundle.bundle_digest
                            if terminal.arbitration_policy_bundle is not None
                            else None
                        ),
                        "execution_lineage_digest": (
                            terminal.execution_lineage.lineage_digest
                            if terminal.execution_lineage is not None
                            else None
                        ),
                    }
                ),
            ),
            ("progress", encode_typed_value({"state": "planned", "terminal_digest": terminal.terminal_digest})),
            ("terminal_artifact", encode_semantic_contract(terminal)),
        ]
        if lifecycle is not None:
            items.append(("lifecycle", encode_semantic_contract(lifecycle)))
        return SemanticTerminalPersistenceService._members(*items)

    @staticmethod
    def _committed_group_members(
        terminal: SemanticTerminalOutcome,
        closure: SemanticArtifactClosure,
        result: SemanticEffectGroupResult,
        graph_delta: SemanticGraphDelta,
        event_batch: SemanticMemoryEventBatch,
        observation: SemanticObservationDelta,
    ) -> tuple[AtomicGenerationMember, ...]:
        return SemanticTerminalPersistenceService._members(
            ("artifact_closure", encode_semantic_contract(closure)),
            (
                "artifact_index",
                encode_typed_value({"terminal": terminal.terminal_digest, "closure": closure.closure_digest}),
            ),
            ("event_batch", encode_semantic_memory_event_batch(event_batch)),
            ("graph_delta", encode_semantic_contract(graph_delta)),
            ("group_result", encode_semantic_contract(result)),
            ("observation_delta", encode_semantic_contract(observation)),
        )

    @staticmethod
    def _noncommitting_group_members(
        terminal: SemanticTerminalOutcome,
        closure: SemanticArtifactClosure,
        result: SemanticEffectGroupResult,
        observation: SemanticObservationDelta,
    ) -> tuple[AtomicGenerationMember, ...]:
        return SemanticTerminalPersistenceService._members(
            ("artifact_closure", encode_semantic_contract(closure)),
            (
                "artifact_index",
                encode_typed_value({"terminal": terminal.terminal_digest, "closure": closure.closure_digest}),
            ),
            ("group_result", encode_semantic_contract(result)),
            ("observation_delta", encode_semantic_contract(observation)),
        )

    def _final_members(
        self,
        terminal: SemanticTerminalOutcome,
        closure: SemanticArtifactClosure,
        *,
        graph_delta: SemanticGraphDelta | None,
    ) -> tuple[AtomicGenerationMember, ...]:
        observation = SemanticObservationDelta.create(
            terminal=terminal,
            graph_delta=graph_delta,
        )
        accepted_transition = (
            SemanticLifecycleTransition.accepted_candidate(
                operation_id=terminal.operation_id,
                candidate_digest=terminal.candidates[0].candidate_digest,
            )
            if terminal.status == "accepted"
            else None
        )
        if accepted_transition is not None:
            terminal_transition = SemanticLifecycleTransition.committed_terminal(
                terminal=terminal,
                accepted_transition=accepted_transition,
            )
        else:
            unsupported_reasons = {
                "missing_language_declaration",
                "untrusted_language",
                "language_mismatch",
                "non_english_language",
                "mixed_residue",
                "unsupported_grammar",
            }
            raw_reason = terminal.reason_codes[0] if terminal.reason_codes else "extractor_abstained"
            reason_code: _SemanticLifecycleReason
            if raw_reason == "missing_language_declaration":
                reason_code = "missing_language_declaration"
            elif raw_reason == "untrusted_language":
                reason_code = "untrusted_language"
            elif raw_reason == "language_mismatch":
                reason_code = "language_mismatch"
            elif raw_reason == "non_english_language":
                reason_code = "non_english_language"
            elif raw_reason == "mixed_residue":
                reason_code = "mixed_residue"
            elif raw_reason == "unsupported_grammar":
                reason_code = "unsupported_grammar"
            elif raw_reason == "retry_budget_exhausted":
                reason_code = "retry_budget_exhausted"
            else:
                reason_code = "extractor_abstained"
            terminal_transition = SemanticLifecycleTransition.nonpromoting_terminal(
                terminal=terminal,
                to_kind="unsupported_input" if reason_code in unsupported_reasons else "abstained",
                reason_code=reason_code,
            )
        return SemanticTerminalPersistenceService._members(
            ("artifact_closure", encode_semantic_contract(closure)),
            ("lifecycle", encode_semantic_contract(terminal_transition)),
            ("observation_delta", encode_semantic_contract(observation)),
            ("source_result", encode_semantic_contract(terminal)),
            (
                "source_summary",
                encode_typed_value(
                    {"terminal_digest": terminal.terminal_digest, "artifact_closure_digest": closure.closure_digest}
                ),
            ),
            (
                "terminal_operation",
                encode_typed_value({"operation_id": terminal.operation_id, "status": terminal.status}),
            ),
        )

    @staticmethod
    def _members(
        *items: tuple[
            _SemanticMemberKind,
            bytes,
        ],
    ) -> tuple[AtomicGenerationMember, ...]:
        ordered = sorted(items, key=lambda item: item[0])
        return tuple(
            AtomicGenerationMember(
                member_id=f"semantic-ingestion-{index:02d}-{kind}",
                kind=kind,
                canonical_payload=payload,
                payload_digest=sha256(payload).hexdigest(),
            )
            for index, (kind, payload) in enumerate(ordered)
        )

    @staticmethod
    def _seal(request):
        return request.model_copy(update={"request_digest": generation_request_digest(request)})

    @staticmethod
    def _next_revision(domain: bytes, current: str, effect_digest: str) -> str:
        return sha256(domain + b"\0" + current.encode() + b"\0" + effect_digest.encode()).hexdigest()


class SemanticIngestionLeaseSession:
    """Store-owned lease heartbeat and preplanning stage-progress publisher."""

    _DURATION = timedelta(seconds=30)

    def __init__(
        self,
        *,
        atomic_store: SemanticIngestionAtomicStore,
        writer_binding_provider: Callable[[], SemanticWriterCommitBinding],
        fence: OperationFenceBinding,
    ) -> None:
        self._store = atomic_store
        self._writer_binding_provider = writer_binding_provider
        self._fence = fence
        self._writer = writer_binding_provider()
        current = self._store.get_operation(fence)
        self._retry_count = self._recover_retry_count(current.generation)
        if current.state in {"terminal", "lease_recovery_exhausted"}:
            self._control = current
            return
        self._control = self._store.acquire_lease(
            operation_fence=fence,
            writer_binding=self._writer,
            execution_token=f"semantic-ingestion:{fence.operation_fence_id}",
            owner_id="semantic-ingestion-pipeline",
            duration=self._DURATION,
        )

    def _recover_retry_count(self, current_generation: int) -> int:
        recovered = 0
        for generation in range(2, current_generation + 1):
            for member in self._store.generation_members(self._fence, generation):
                if member.kind != "progress":
                    continue
                try:
                    progress = decode_semantic_contract(member.canonical_payload, SemanticRetryableProgress)
                except (ValueError, TypeError):
                    continue
                recovered = max(recovered, progress.attempt_count)
        return recovered

    @property
    def exhausted(self) -> bool:
        return self._control.state == "lease_recovery_exhausted"

    @property
    def closed(self) -> bool:
        return self._control.state in {"terminal", "lease_recovery_exhausted"}

    def checkpoint_execution_plan(self, plan: SemanticExecutionRetryPlan) -> None:
        plan.validate_for_fence(self._fence)
        existing = SemanticTerminalPersistenceService(
            atomic_store=self._store,
            writer_binding_provider=self._writer_binding_provider,
            authorization_repository=None,
        ).recover_execution_plan(fence=self._fence)
        if existing is not None:
            if existing != plan:
                raise ValueError("semantic ingestion redelivery execution plan differs from persisted plan")
            return
        self.heartbeat()
        plan_bytes = encode_semantic_contract(plan)
        progress_bytes = encode_typed_value(
            {"stage": "execution_plan", "artifact_digest": sha256(plan_bytes).hexdigest()}
        )
        members = (
            AtomicGenerationMember(
                member_id="semantic-ingestion-00-execution-plan",
                kind="execution_plan",
                canonical_payload=plan_bytes,
                payload_digest=sha256(plan_bytes).hexdigest(),
            ),
            AtomicGenerationMember(
                member_id="semantic-ingestion-01-progress",
                kind="progress",
                canonical_payload=progress_bytes,
                payload_digest=sha256(progress_bytes).hexdigest(),
            ),
        )
        request = SourceCheckpointAtomicWriteRequest(
            operation_fence_binding=self._fence,
            operation_lease_binding=self._store.lease_binding(self._control),
            writer_commit_binding=self._writer,
            expected_operation_generation=self._control.generation,
            expected_artifact_generation=self._control.generation,
            members=members,
            required_artifact_digests=(),
            request_digest="0" * 64,
            progress_state="preplanning",
        )
        self._store.checkpoint_source_progress(SemanticTerminalPersistenceService._seal(request))
        self._control = self._store.get_operation(self._fence)

    def checkpoint_recovery_authority_binding(
        self,
        binding: SemanticRecoveryAuthorityBinding,
    ) -> None:
        service = SemanticTerminalPersistenceService(
            atomic_store=self._store,
            writer_binding_provider=self._writer_binding_provider,
            authorization_repository=None,
        )
        existing = service.recover_recovery_authority_binding(fence=self._fence)
        if existing is not None:
            if existing != binding:
                raise ValueError("semantic ingestion recovery authority binding changed")
            return
        self.heartbeat()
        payload = encode_semantic_contract(binding)
        member = AtomicGenerationMember(
            member_id="semantic-ingestion-00-recovery-authority-binding",
            kind="recovery_authority_binding",
            canonical_payload=payload,
            payload_digest=sha256(payload).hexdigest(),
        )
        progress_payload = encode_typed_value(
            {
                "stage": "recovery_authority_bound",
                "artifact_digest": binding.binding_digest,
            }
        )
        progress = AtomicGenerationMember(
            member_id="semantic-ingestion-01-progress",
            kind="progress",
            canonical_payload=progress_payload,
            payload_digest=sha256(progress_payload).hexdigest(),
        )
        request = SourceCheckpointAtomicWriteRequest(
            operation_fence_binding=self._fence,
            operation_lease_binding=self._store.lease_binding(self._control),
            writer_commit_binding=self._writer,
            expected_operation_generation=self._control.generation,
            expected_artifact_generation=self._control.generation,
            members=(member, progress),
            required_artifact_digests=(),
            request_digest="0" * 64,
            progress_state="preplanning",
        )
        self._store.checkpoint_source_progress(SemanticTerminalPersistenceService._seal(request))
        self._control = self._store.get_operation(self._fence)

    def heartbeat(self) -> None:
        if self.closed:
            raise ValueError("semantic ingestion lease session is terminal")
        lease = self._control.lease
        if lease is None:
            raise ValueError("semantic ingestion lease session has no active lease")
        self._control = self._store.renew_lease(
            operation_fence=self._fence,
            writer_binding=self._writer,
            lease=lease,
            duration=self._DURATION,
        )

    def checkpoint(
        self,
        stage: str,
        artifact_digest: str,
        canonical_artifact_payload: bytes,
    ) -> None:
        if not stage or len(artifact_digest) != 64:
            raise ValueError("semantic ingestion stage progress must be content addressed")
        if artifact_digest not in semantic_replay_dependency_digests("stage_artifact", canonical_artifact_payload):
            raise ValueError("semantic ingestion stage progress does not bind its typed artifact")
        self.heartbeat()
        if self._control.state != "preplanning":
            raise ValueError("semantic ingestion learned-stage progress cannot be written after planning")
        payload = encode_typed_value({"stage": stage, "artifact_digest": artifact_digest})
        artifact = AtomicGenerationMember(
            member_id="semantic-ingestion-00-stage-artifact",
            kind="stage_artifact",
            canonical_payload=canonical_artifact_payload,
            payload_digest=sha256(canonical_artifact_payload).hexdigest(),
        )
        progress = AtomicGenerationMember(
            member_id="semantic-ingestion-01-progress",
            kind="progress",
            canonical_payload=payload,
            payload_digest=sha256(payload).hexdigest(),
        )
        request = SourceCheckpointAtomicWriteRequest(
            operation_fence_binding=self._fence,
            operation_lease_binding=self._store.lease_binding(self._control),
            writer_commit_binding=self._writer,
            expected_operation_generation=self._control.generation,
            expected_artifact_generation=self._control.generation,
            members=(artifact, progress),
            required_artifact_digests=(),
            request_digest="0" * 64,
            progress_state="preplanning",
        )
        self._store.checkpoint_source_progress(SemanticTerminalPersistenceService._seal(request))
        self._control = self._store.get_operation(self._fence)

    def checkpoint_retryable(
        self,
        *,
        stage: Literal["policy_read", "proposal", "analysis", "planning", "group", "finalization"],
        failure_kind: Literal["policy_outage", "transport_outage", "store_outage"],
        terminal: SemanticTerminalOutcome | None = None,
    ) -> None:
        self._control = self._store.get_operation(self._fence)
        if self.closed:
            return
        if self._control.state == "planned" and stage in {"policy_read", "proposal", "analysis"}:
            raise ValueError("planned semantic ingestion operation cannot regress to a learned stage")
        self._retry_count += 1
        if self._retry_count > 3:
            exhausted_terminal = SemanticTerminalOutcome.create(
                operation_id=self._fence.operation_id,
                status="evidence_only",
                reason_codes=("retry_budget_exhausted",),
                candidates=(),
                temporal_closures=(),
                attempt_count=2,
            )
            SemanticTerminalPersistenceService(
                atomic_store=self._store,
                writer_binding_provider=self._writer_binding_provider,
                authorization_repository=None,
            ).persist(fence=self._fence, terminal=exhausted_terminal)
            self._control = self._store.get_operation(self._fence)
            return
        self._control = self._store.acquire_lease(
            operation_fence=self._fence,
            writer_binding=self._writer,
            execution_token=f"semantic-ingestion:{self._fence.operation_fence_id}",
            owner_id="semantic-ingestion-pipeline",
            duration=self._DURATION,
        )
        self.heartbeat()
        terminal_bytes = encode_semantic_contract(terminal) if terminal is not None else None
        progress = SemanticRetryableProgress.create(
            operation_id=self._fence.operation_id,
            stage=stage,
            failure_kind=failure_kind,
            attempt_count=self._retry_count,
            terminal_artifact_digest=(
                sha256(terminal_bytes).hexdigest()
                if terminal_bytes is not None and self._control.state == "planned"
                else None
            ),
        )
        progress_bytes = encode_semantic_contract(progress)
        members = [
            AtomicGenerationMember(
                member_id="semantic-ingestion-00-progress",
                kind="progress",
                canonical_payload=progress_bytes,
                payload_digest=sha256(progress_bytes).hexdigest(),
            )
        ]
        request = SourceCheckpointAtomicWriteRequest(
            operation_fence_binding=self._fence,
            operation_lease_binding=self._store.lease_binding(self._control),
            writer_commit_binding=self._writer,
            expected_operation_generation=self._control.generation,
            expected_artifact_generation=self._control.generation,
            members=tuple(members),
            required_artifact_digests=(),
            request_digest="0" * 64,
            progress_state=("planned" if self._control.state == "planned" else "preplanning"),
        )
        self._store.checkpoint_source_progress(SemanticTerminalPersistenceService._seal(request))
        self._control = self._store.get_operation(self._fence)


__all__ = [
    "SemanticAuthorizationReadSetError",
    "SemanticIngestionLeaseSession",
    "SemanticTerminalPersistenceService",
]

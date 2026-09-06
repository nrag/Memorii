from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from memorii.core.memory_evolution.admission import (
    source_admission_source_bytes,
)
from memorii.core.memory_evolution.conflict_attention import (
    AgentClarificationProposal,
    AuthorizedUserEventProof,
    ClarificationFailureClass,
    ClarificationSubmissionOutcome,
    ConflictAccessContext,
    ConflictAttention,
    ConflictAudience,
    ConflictClarificationProcessingReceipt,
    ConflictKind,
    ConflictListRequest,
    ConflictResolutionAction,
    ConflictResolutionOption,
    ConflictResolutionRequest,
    ConflictStatus,
    UserConfirmationReceipt,
    UserConfirmationVerificationContext,
    VerifiedUserConfirmation,
    build_agent_clarification_proposal,
    conflict_resolution_request_digest,
)
from memorii.core.memory_evolution.conflict_attention_repository import (
    ClarificationPipelineError,
    ConflictClarificationError,
    ConflictClarificationProcessor,
    ConflictCursorKey,
    FileConflictAttentionRepository,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.integrations.hermes_provider import HermesMemoryProvider


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 2, tzinfo=UTC)


def _repository(path: Path, clock: _Clock) -> FileConflictAttentionRepository:
    return FileConflictAttentionRepository(
        path,
        keys=(
            ConflictCursorKey(
                key_id="key",
                key_epoch=1,
                secret=b"k" * 32,
                valid_from=clock.now - timedelta(days=1),
                expires_at=clock.now + timedelta(days=1),
                signing=True,
            ),
        ),
        now_provider=lambda: clock.now,
        repository_id="repository",
        policy_fingerprint=_digest("policy"),
    )


def _attention(*, conflict_id: str = "conflict", coordinate: int = 1, integrity: bool = False) -> ConflictAttention:
    return ConflictAttention(
        conflict_id=conflict_id,
        conflict_revision=_digest("revision"),
        kind=ConflictKind.STORAGE_INTEGRITY if integrity else ConflictKind.SEMANTIC_DISAGREEMENT,
        audience=ConflictAudience.OPERATOR if integrity else ConflictAudience.USER,
        status=ConflictStatus.OPEN,
        question=(
            "Memory integrity incident requires operator action."
            if integrity
            else "Which employer is current?"
        ),
        options=()
        if integrity
        else (
            ConflictResolutionOption(
                candidate_id="globex",
                label="Globex",
                statement="Alice works at Globex.",
                candidate_digest=_digest("globex"),
            ),
            ConflictResolutionOption(
                candidate_id="initech",
                label="Initech",
                statement="Alice works at Initech.",
                candidate_digest=_digest("initech"),
            ),
        ),
        created_at=datetime(2026, 8, 2, tzinfo=UTC),
        creation_coordinate=coordinate,
        scope_digest=_digest("scope"),
    )


def _access() -> ConflictAccessContext:
    return ConflictAccessContext(
        tenant_id="tenant",
        principal_id="principal",
        principal_binding_digest=_digest("binding"),
        authorized_scope_ids=("scope",),
        scope_digest=_digest("authorized-scopes"),
        authorization_snapshot_digest=_digest("authorization"),
    )


def _request(
    *,
    conflict_id: str = "conflict",
    conflict_revision: str | None = None,
    source_user_event_id: str = "user-event",
    operation_id: str = "operation",
    candidate_id: str = "globex",
    receipt: str | None = None,
) -> ConflictResolutionRequest:
    return ConflictResolutionRequest(
        conflict_id=conflict_id,
        expected_conflict_revision=(
            conflict_revision if conflict_revision is not None else _digest("revision")
        ),
        operation_id=operation_id,
        action=ConflictResolutionAction.SELECT,
        selected_candidate_ids=(candidate_id,),
        validity_intervals=(),
        source_user_event_id=source_user_event_id,
        user_confirmation_receipt=None if receipt is None else UserConfirmationReceipt(token=receipt),
    )


def _proposal(request: ConflictResolutionRequest) -> AgentClarificationProposal:
    return build_agent_clarification_proposal(
        request,
        source_user_event_digest=_digest("user-event"),
        agent_principal_id="principal",
        scope_digest=_digest("scope"),
    )


def _confirmation(request: ConflictResolutionRequest, *, nonce: str) -> VerifiedUserConfirmation:
    return VerifiedUserConfirmation(
        issuer_id="issuer",
        key_id="key",
        trust_snapshot_digest=_digest("trust"),
        revocation_snapshot_digest=_digest("revocation"),
        principal_id="principal",
        scope_digest=_digest("scope"),
        conflict_id=request.conflict_id,
        conflict_revision=request.expected_conflict_revision,
        action=request.action,
        request_digest=conflict_resolution_request_digest(request),
        source_user_event_id=request.source_user_event_id,
        source_user_event_digest=_digest("user-event"),
        issued_at=datetime(2026, 8, 2, tzinfo=UTC) - timedelta(seconds=1),
        expires_at=datetime(2026, 8, 2, tzinfo=UTC) + timedelta(minutes=1),
        nonce=nonce,
    )


def _submit(repository: FileConflictAttentionRepository, request: ConflictResolutionRequest | None = None) -> None:
    actual = request or _request()
    result = repository.submit_clarification(
        _access(),
        actual,
        conflict_resolution_request_digest(actual),
        _proposal(actual),
        None,
    )
    assert result.outcome == ClarificationSubmissionOutcome.SUBMITTED


class _Pipeline:
    def __init__(
        self,
        *,
        failures: int = 0,
        crash_after_commit: bool = False,
        receipt_path: Path | None = None,
        canonical_commit=None,
    ) -> None:
        self.failures = failures
        self.crash_after_commit = crash_after_commit
        self.receipt_path = receipt_path
        # Optional bridge to the real canonical commit transaction; when
        # present, the pipeline's receipt IS the store's retained receipt.
        self.canonical_commit = canonical_commit
        self.calls = 0
        self.receipts: dict[str, ConflictClarificationProcessingReceipt] = {}
        self.claim = None

    def resolve_processing_receipt(self, processing_operation_id: str) -> ConflictClarificationProcessingReceipt | None:
        if self.receipt_path is not None and self.receipt_path.exists():
            receipt = ConflictClarificationProcessingReceipt.model_validate_json(
                self.receipt_path.read_bytes()
            )
            if receipt.processing_operation_id == processing_operation_id:
                return receipt
        return self.receipts.get(processing_operation_id)

    def process_clarification(
        self,
        proposal: AgentClarificationProposal,
        *,
        processing_operation_id: str,
        policy_fingerprint: str,
        current_claim,
    ) -> ConflictClarificationProcessingReceipt:
        self.calls += 1
        if self.calls <= self.failures:
            raise ClarificationPipelineError(ClarificationFailureClass.RETRYABLE)
        if self.canonical_commit is not None:
            receipt = self.canonical_commit(
                proposal,
                processing_operation_id=processing_operation_id,
                policy_fingerprint=policy_fingerprint,
                current_claim=current_claim(),
            )
            self.receipts[processing_operation_id] = receipt
            if self.crash_after_commit:
                raise RuntimeError("crash after semantic commit")
            return receipt
        receipt = ConflictClarificationProcessingReceipt.create(
            processing_operation_id=processing_operation_id,
            conflict_id=proposal.conflict_id,
            conflict_revision=current_claim().work.conflict_revision,
            proposal_digest=proposal.proposal_digest,
            policy_fingerprint=policy_fingerprint,
            semantic_transaction_id="semantic-transaction",
            semantic_transaction_digest=_digest("semantic-transaction"),
            semantic_result_digest=_digest("semantic-result"),
            committed_outcome="accepted",
            committed_at=datetime(2026, 8, 2, tzinfo=UTC),
        )
        self.receipts[processing_operation_id] = receipt
        if self.receipt_path is not None:
            with self.receipt_path.open("wb") as handle:
                handle.write(receipt.model_dump_json().encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
        if self.crash_after_commit:
            raise RuntimeError("crash after semantic commit")
        return receipt


def test_atomic_submission_is_idempotent_and_restart_reconstructs_submitted_state(tmp_path: Path) -> None:
    clock = _Clock()
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path, clock)
    repository.append_open(_attention(), scope_ids=("scope",))
    request = _request()
    _submit(repository, request)
    assert repository.list_conflicts(_access(), request=ConflictListRequest()).total_pending == 0
    committed = path.read_bytes()

    retry = _repository(path, clock).preflight_clarification(
        _access(), request, conflict_resolution_request_digest(request)
    )
    assert retry is not None and retry.outcome == ClarificationSubmissionOutcome.IDEMPOTENT
    assert path.read_bytes() == committed
    with pytest.raises(ConflictClarificationError, match="conflict_operation_mismatch"):
        repository.preflight_clarification(_access(), request, _digest("different"))


def test_expired_claim_is_reclaimed_and_exact_durable_receipt_is_adopted_without_reinvocation(tmp_path: Path) -> None:
    clock = _Clock()
    repository = _repository(tmp_path / "conflicts.jsonl", clock)
    repository.append_open(_attention(), scope_ids=("scope",))
    _submit(repository)
    first = repository.claim_next_clarification(lease_duration=timedelta(seconds=5))
    assert first is not None
    receipt_path = tmp_path / "semantic-receipt.json"
    pipeline = _Pipeline(receipt_path=receipt_path)
    pipeline.claim = first
    durable = pipeline.process_clarification(
        first.proposal,
        processing_operation_id=first.work.processing_operation_id,
        policy_fingerprint=first.work.policy_fingerprint,
        current_claim=lambda: first,
    )
    calls = pipeline.calls

    clock.now += timedelta(seconds=6)
    reopened_pipeline = _Pipeline(receipt_path=receipt_path)
    assert ConflictClarificationProcessor(
        _repository(repository._path, clock),
        reopened_pipeline,
        lease_duration=timedelta(seconds=5),
    ).process_next()
    assert pipeline.calls == calls
    assert reopened_pipeline.calls == 0
    lines = [json.loads(line) for line in repository._path.read_text(encoding="utf-8").splitlines()]
    outcomes = [
        result["outcome"]
        for line in lines
        for result in line.get("attempt_results", [])
    ]
    assert outcomes == ["lease_expired", "accepted"]
    assert durable.receipt_digest in repository._path.read_text(encoding="utf-8")


def test_process_next_adopts_durable_commit_receipt_after_pipeline_raises_exactly_once(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    path = tmp_path / "conflicts.jsonl"
    receipt_path = tmp_path / "semantic-receipt.json"
    repository = _repository(path, clock)
    repository.append_open(_attention(), scope_ids=("scope",))
    _submit(repository)
    crashing_pipeline = _Pipeline(
        crash_after_commit=True,
        receipt_path=receipt_path,
    )

    assert ConflictClarificationProcessor(repository, crashing_pipeline).process_next()
    assert crashing_pipeline.calls == 1

    reopened_pipeline = _Pipeline(receipt_path=receipt_path)
    assert not ConflictClarificationProcessor(
        _repository(path, clock), reopened_pipeline
    ).process_next()
    assert reopened_pipeline.calls == 0
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    outcomes = [
        result["outcome"]
        for line in lines
        for result in line.get("attempt_results", [])
    ]
    assert outcomes == ["accepted"]
    durable = ConflictClarificationProcessingReceipt.model_validate_json(
        receipt_path.read_bytes()
    )
    replay = repository._replay(repository._read_all())
    work = next(iter(replay.works.values()))
    assert work.downstream_receipt_digest == durable.receipt_digest


def test_processor_renews_claim_while_semantic_pipeline_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    repository = _repository(tmp_path / "conflicts.jsonl", clock)
    repository.append_open(_attention(), scope_ids=("scope",))
    _submit(repository)
    pipeline = _Pipeline()
    entered = Event()
    renewed = Event()
    release = Event()
    renewed_claim = []
    original_renew = repository.renew_clarification_claim
    original_process = pipeline.process_clarification

    def observed_renew(claim, *, lease_duration):
        result = original_renew(claim, lease_duration=lease_duration)
        renewed_claim.append(result)
        renewed.set()
        return result

    def blocked_process(proposal, **kwargs):
        clock.now += timedelta(milliseconds=250)
        entered.set()
        assert release.wait(timeout=5)
        # The processor exposes the heartbeat's successor work image to the
        # pipeline; a CAS built from the initial claim would now be stale.
        assert kwargs["current_claim"]() == renewed_claim[-1]
        return original_process(proposal, **kwargs)

    monkeypatch.setattr(repository, "renew_clarification_claim", observed_renew)
    monkeypatch.setattr(pipeline, "process_clarification", blocked_process)
    processor = ConflictClarificationProcessor(
        repository, pipeline, lease_duration=timedelta(milliseconds=300)
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        processing = executor.submit(processor.process_next)
        assert entered.wait(timeout=5)
        assert renewed.wait(timeout=5)
        clock.now += timedelta(milliseconds=200)
        assert repository.claim_next_clarification(
            lease_duration=timedelta(milliseconds=300)
        ) is None
        release.set()
        assert processing.result(timeout=5) is True


def test_process_next_reclaims_expired_lease_and_fences_concurrent_stale_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path, clock)
    repository.append_open(_attention(), scope_ids=("scope",))
    _submit(repository)
    stale = repository.claim_next_clarification(lease_duration=timedelta(seconds=5))
    assert stale is not None
    clock.now += timedelta(seconds=6)
    pipeline = _Pipeline()
    entered = Event()
    release = Event()
    original_process = pipeline.process_clarification

    def blocked_process(proposal, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original_process(proposal, **kwargs)

    monkeypatch.setattr(pipeline, "process_clarification", blocked_process)
    processor = ConflictClarificationProcessor(
        repository,
        pipeline,
        lease_duration=timedelta(seconds=5),
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        processing = executor.submit(processor.process_next)
        assert entered.wait(timeout=5)
        state = repository._replay(repository._read_all())
        current = state.works[stale.work.processing_operation_id]
        assert current.ownership_epoch == stale.work.ownership_epoch + 1
        before = path.read_bytes()
        with pytest.raises(
            ConflictClarificationError,
            match="stale_clarification_owner",
        ):
            repository.fail_clarification_claim(
                stale,
                ClarificationFailureClass.RETRYABLE,
            )
        assert path.read_bytes() == before
        release.set()
        assert processing.result(timeout=5) is True

    outcomes = [
        result["outcome"]
        for line in (
            json.loads(raw)
            for raw in path.read_text(encoding="utf-8").splitlines()
        )
        for result in line.get("attempt_results", [])
    ]
    assert outcomes == ["lease_expired", "accepted"]


def test_two_operations_racing_one_confirmation_nonce_commit_at_most_once(tmp_path: Path) -> None:
    clock = _Clock()
    path = tmp_path / "conflicts.jsonl"
    repository = _repository(path, clock)
    repository.append_open(_attention(conflict_id="conflict-a", coordinate=1), scope_ids=("scope",))
    repository.append_open(_attention(conflict_id="conflict-b", coordinate=2), scope_ids=("scope",))
    requests = (
        _request(conflict_id="conflict-a", operation_id="operation-a", receipt="receipt"),
        _request(conflict_id="conflict-b", operation_id="operation-b", receipt="receipt"),
    )

    def submit(request: ConflictResolutionRequest) -> str:
        try:
            result = repository.submit_clarification(
                _access(),
                request,
                conflict_resolution_request_digest(request),
                _proposal(request),
                _confirmation(request, nonce="shared-nonce"),
            )
            return result.outcome.value
        except ConflictClarificationError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, requests))
    assert sorted(outcomes) == ["invalid_user_confirmation_receipt", "submitted"]
    assert path.read_text(encoding="utf-8").count('"nonce":"shared-nonce"') == 1


def test_retryable_failures_one_and_two_reclaim_then_third_reopens_new_revision(tmp_path: Path) -> None:
    clock = _Clock()
    repository = _repository(tmp_path / "conflicts.jsonl", clock)
    repository.append_open(_attention(), scope_ids=("scope",))
    _submit(repository)
    pipeline = _Pipeline(failures=3)
    processor = ConflictClarificationProcessor(repository, pipeline)
    for expected in (1, 2, 3):
        assert processor.process_next() is True
        records = repository._read_all()
        replay = repository._replay(records)
        assert len(replay.works) == 1
        work = next(iter(replay.works.values()))
        assert work.attempt_count == expected
        assert work.owner_token is None
        assert work.lease_expires_at is None
        page = repository.list_conflicts(_access(), ConflictListRequest())
        assert page.total_pending == (1 if expected == 3 else 0)
    assert processor.process_next() is False
    assert pipeline.calls == 3
    page = repository.list_conflicts(
        _access(),
        ConflictListRequest(),
    )
    assert page.total_pending == 1
    assert page.items[0].conflict_revision != _digest("revision")


class _Resolver:
    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedIngressContext:
        del host_ingress, server_time
        binding = DeliveryPrincipalBinding.create(
            principal_subject_id="principal",
            tenant_partition_id="tenant",
            provider_identity="hermes",
        )
        scopes = RequiredOutcomeScopeSet.create(tenant_partition_id="tenant", scopes=("user:user",))
        return AuthenticatedIngressContext(
            delivery_principal_binding=binding,
            required_outcome_scopes=scopes,
            current_authorized_scopes=scopes,
            semantic_egress_governance=AuthenticatedSemanticEgressGovernance(
                classification="internal",
                provider="hermes",
                model="fixture",
                region="local",
                retention_mode="session",
                training_use=False,
            ),
            semantic_source_authority=AuthenticatedSemanticSourceAuthority(
                authority_class="official",
                authenticated_provenance_class="host",
                governing_principal_id="principal",
                policy_revision="trust-r1",
                provenance_digest="a" * 64,
            ),
        )


class _SourceVerifier:
    def __init__(self) -> None:
        self.calls = 0
        self.canonical_source_bytes: bytes | None = None
        self.canonical_source_digest: str | None = None

    def bind(
        self, service: ProviderMemoryService, *, memory_id: str = "tx:user-event"
    ) -> None:
        record = service._memory_plane.get_record(memory_id)
        if record is None:
            records = tuple(
                value
                for value in service._memory_plane.list_records()
                if value.source_kind == "semantic_ingestion_source"
            )
            assert len(records) == 1
            record = records[0]
        self.canonical_source_bytes = source_admission_source_bytes(record)

    def verify_user_event(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        scope_digest: str,
        source_user_event_id: str,
    ) -> AuthorizedUserEventProof:
        self.calls += 1
        if self.canonical_source_bytes is None:
            raise ValueError("source verifier is not bound to retained bytes")
        return AuthorizedUserEventProof(
            tenant_id=tenant_id,
            principal_id=principal_id,
            scope_digest=scope_digest,
            source_user_event_id=source_user_event_id,
            source_user_event_digest=hashlib.sha256(
                self.canonical_source_bytes
            ).hexdigest(),
            canonical_source_bytes=self.canonical_source_bytes,
        )


class _ReceiptVerifier:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = True

    def verify(
        self,
        receipt: UserConfirmationReceipt,
        *,
        expected: UserConfirmationVerificationContext,
        server_time: datetime,
    ) -> VerifiedUserConfirmation:
        del receipt
        self.calls += 1
        if self.fail:
            raise ValueError("bad receipt")
        return VerifiedUserConfirmation(
            issuer_id="issuer",
            key_id="key",
            trust_snapshot_digest=_digest("trust"),
            revocation_snapshot_digest=_digest("revocation"),
            principal_id=expected.principal_id,
            scope_digest=expected.scope_digest,
            conflict_id=expected.conflict_id,
            conflict_revision=expected.conflict_revision,
            action=expected.action,
            request_digest=expected.request_digest,
            source_user_event_id=expected.source_user_event_id,
            source_user_event_digest=expected.source_user_event_digest,
            issued_at=server_time - timedelta(seconds=1),
            expires_at=server_time + timedelta(minutes=1),
            nonce="nonce",
        )


class _SeededConflict:
    """A canonical OPEN conflict created through the real contest lifecycle."""

    def __init__(self, conflict_id, conflict_revision, source_event_id, candidate_ids):
        self.conflict_id = conflict_id
        self.conflict_revision = conflict_revision
        self.source_event_id = source_event_id
        self.candidate_ids = candidate_ids


def _seed_canonical_conflict(
    service: ProviderMemoryService,
    now: datetime,
    *,
    scope_ids: frozenset[str] = frozenset({"user:user"}),
) -> _SeededConflict:
    """Create one real OPEN canonical conflict on the service's own plane.

    The canonical resolution door reads conflict state from the plane's
    conflict-authority records, so the clarification fixtures must seed a
    genuine contest there (two contested terminals through the standard
    handoff/persist machinery) with the ingress resolver's scope
    vocabulary, and bind the submission source to the seeded handoff's
    admitted user event.
    """
    import sys as _sys

    from memorii.core.memory_evolution.delivery_coordinate_migration import (
        activate_migration,
        build_migration_plan,
        certify_migration,
    )
    from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
    from memorii.core.memory_evolution.writer_admission import (
        SemanticWriterAdmissionError,
    )
    from memorii.core.semantic_ingestion.authorization import (
        SemanticAuthorizationAuthorityRepository,
    )
    from memorii.core.semantic_ingestion.capability import (
        build_authorized_local_semantic_runtime,
    )
    from memorii.core.semantic_ingestion.persistence import (
        SemanticTerminalPersistenceService,
    )

    _support_dir = str(Path(__file__).parent / "semantic_ingestion")
    if _support_dir not in _sys.path:
        _sys.path.insert(0, _support_dir)
    from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import (  # noqa: E402
        TestSemanticConflictAuthorityResolver,
        accepted_terminal,
        handoff,
    )
    from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
        _AuthorizationVerifier,
        _PolicyProvider,
    )
    from tests.unit.core.semantic_ingestion.test_semantic_terminal_persistence import (
        AUTHORIZATION as PERSIST_AUTHORIZATION,
    )
    from tests.unit.core.semantic_ingestion.test_semantic_terminal_persistence import (
        _activate,
    )

    plane = service._memory_plane
    writers = service._semantic_writer_admission
    store = service._semantic_atomic_store
    try:
        current = writers.current()
    except SemanticWriterAdmissionError:
        current = writers.create_initial_evidence_only(
            admission_id="clarification-tests",
            writer_implementation_fingerprint="writer",
            graph_schema_fingerprint="schema",
        )
    binding = writers.commit_binding(current)
    if current.active_runtime_mode != "verified_semantic":
        plan = build_migration_plan(
            migration_plan_id="clarification-tests:verified",
            source_writer_epoch=current.writer_epoch,
            legacy_snapshot_token=hashlib.sha256(encode_typed_value(())).hexdigest(),
            entries=(),
        )
        checkpoint_values = {
            "migration_plan_id": plan.migration_plan_id,
            "plan_digest": plan.plan_digest,
            "completed_entry_digests": (),
            "target_generation": current.writer_epoch,
        }
        from memorii.core.memory_evolution.delivery_coordinate_migration import (
            DeliveryCoordinateMigrationCheckpoint,
        )
        checkpoint = DeliveryCoordinateMigrationCheckpoint(
            **checkpoint_values,
            checkpoint_digest=hashlib.sha256(
                encode_typed_value(checkpoint_values)
            ).hexdigest(),
        )
        certificate = certify_migration(
            plan, checkpoint, independent_verifier_fingerprint="clarification-tests"
        )
        writers.transition(
            expected=binding,
            admission_id="clarification-tests:verified",
            runtime_mode="verified_semantic",
            writer_implementation_fingerprint="writer:verified",
            graph_schema_fingerprint="schema",
            migration_activation=activate_migration(plan, certificate),
            migration_plan=plan,
            migration_checkpoint=checkpoint,
            migration_certificate=certificate,
            target_records=(),
        )
    binding = writers.commit_binding(writers.current())
    # The service's construction already installed the governed write policy
    # over this plane, so the admission handoff must go through the atomic
    # store like every later write.
    admission, _admission_fence = handoff(
        plane,
        coordinate="clarification-canonical-admission",
        scope_ids=scope_ids,
        atomic_store=store,
        writer_binding=binding,
    )
    store._publish_preplanning(admission=admission, writer_binding=binding)

    resolver = TestSemanticConflictAuthorityResolver(plane)
    # The bare service's store was built before any runtime existed, so its
    # projection history has no conflict resolver; the host composition the
    # fixtures emulate installs one before any contest can publish.
    store._projection_history._semantic_conflict_authority_resolver = resolver
    runtime = service._provider_ingestion._semantic_runtime
    if runtime is None:
        runtime = build_authorized_local_semantic_runtime(
            authorization_bytes=b"clarification-tests-authorization",
            authorization_verifier=_AuthorizationVerifier(),
            policy_provider=_PolicyProvider("works_for"),
            writer_admission=writers,
            atomic_store=store,
            bootstrap_profile=None,
        )
        administration_grant = writers._claim_conflict_authority_administration(
            owner=runtime
        )
    else:
        administration_grant = runtime.conflict_authority_administration_grant()
    resolver.install(writers, administration_grant)
    repository = SemanticAuthorizationAuthorityRepository(
        atomic_store=store,
        writer_binding_provider=lambda: binding,
        now_provider=lambda: now,
    )
    persistence = SemanticTerminalPersistenceService(
        atomic_store=store,
        writer_binding_provider=lambda: binding,
        authorization_repository=repository,
    )
    from datetime import timedelta as _timedelta

    _, first_fence = handoff(
        plane,
        coordinate="clarification-canonical-first",
        scope_ids=scope_ids,
        atomic_store=store,
        writer_binding=binding,
    )
    first = accepted_terminal(
        operation_id=first_fence.operation_id,
        valid_start=now,
        valid_end=now + _timedelta(days=2),
    )
    _activate(repository, first_fence, first)
    persistence.persist(
        fence=first_fence,
        terminal=first,
        authorization_verifier=PERSIST_AUTHORIZATION,
    )
    _, contested_fence = handoff(
        plane,
        coordinate="clarification-canonical-contest",
        scope_ids=scope_ids,
        atomic_store=store,
        writer_binding=binding,
    )
    contested = accepted_terminal(
        operation_id=contested_fence.operation_id,
        object_logical_entity_id="entity:initech",
        object_entity_revision_id="entity-revision:initech:v1",
        valid_start=now,
        valid_end=now + _timedelta(days=2),
    )
    _activate(repository, contested_fence, contested)
    persistence.persist(
        fence=contested_fence,
        terminal=contested,
        authorization_verifier=PERSIST_AUTHORIZATION,
    )
    conflicts = store._projection_history._current_semantic_conflicts()
    assert len(conflicts) == 1
    conflict_id, entry = next(iter(conflicts.items()))
    source = plane.get_record("tx:clarification-canonical-contest")
    assert source is not None
    candidate_ids = tuple(
        sorted(
            candidate.candidate_id
            for candidate in entry[0].display.options
        )
    )
    return _SeededConflict(
        conflict_id=conflict_id,
        conflict_revision=entry[2].current_conflict_revision,
        source_event_id=source.memory_id,
        candidate_ids=candidate_ids,
    )


def _sync_and_bind_user_source(
    service: ProviderMemoryService,
    verifier: _SourceVerifier,
    host: AuthenticatedHostIngress,
) -> None:
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="I choose Globex.",
        operation_id="user-event",
        role="user",
        task_id="task",
        user_id="user",
        authenticated_host_ingress=host,
    )
    verifier.bind(service)


def _exercise_public_accepted_clarification_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
) -> dict[str, object]:
    """A real clarification winner forces one typed V3 successor, not reingestion."""
    race_timeout_seconds = 300
    import importlib as _importlib
    import sys as _sys

    from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
    from memorii.core.semantic_ingestion.contracts import (
        BootstrapGraphPlanAtomicWriteRequestV3,
        ProviderEntityObject,
        ProviderFact,
        ProviderMention,
        ProviderSemanticProposal,
        decode_bootstrap_graph_atomic_member_payload_v3,
    )
    from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
        provider_service,
    )
    from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
        TEST_NOW,
        DeterministicTestHostBootstrapMaterialVerifier,
        _built_in_local_capability,
        _host_ingress,
        _v3_normalization_host_builder,
    )

    support_dir = str(Path(__file__).parent / "semantic_ingestion")
    if support_dir not in _sys.path:
        _sys.path.insert(0, support_dir)
    commit_claimed = _importlib.import_module(
        "test_semantic_terminal_persistence"
    )._commit_claimed_accepted_clarification

    assertion = "Atlas owner is Bob."
    proposal = ProviderSemanticProposal(
        mentions=(
            ProviderMention(
                local_id="atlas",
                mention_quote="Atlas",
                mention_context_quote=assertion,
            ),
            ProviderMention(
                local_id="bob",
                mention_quote="Bob",
                mention_context_quote=assertion,
            ),
        ),
        facts=(
            ProviderFact(
                local_id="owner",
                predicate_id="owner_is",
                subject_entity_ref="atlas",
                object=ProviderEntityObject(entity_ref="bob"),
                assertion_quote=assertion,
                predicate_anchor_quote="owner",
                polarity="positive",
                commitment="asserted",
            ),
        ),
        abstained=False,
    )
    normalization, normalization_calls = _v3_normalization_host_builder(
        proposal=proposal
    )
    plane_path = tmp_path / "plane"
    plane = (
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(plane_path))
        if backend == "jsonl"
        else MemoryPlaneService()
    )
    clock = _Clock()
    clock.now = TEST_NOW
    repository = _repository(tmp_path / f"conflicts-{backend}.jsonl", clock)
    source = _SourceVerifier()
    captured_request = []
    accepted_receipts = []

    def canonical_commit(
        proposal, *, processing_operation_id, policy_fingerprint, current_claim
    ):
        del proposal, processing_operation_id, policy_fingerprint
        assert len(captured_request) == 1
        intents = tuple(
            intent
            for operation in captured_request[0].ordered_operation_inputs
            for intent in operation.reduction.effect_materialization.record_intents
            if intent.record_kind == "entity_revision"
        )
        assert len(intents) == 2, tuple(
            {
                "status": operation.reduction.native_terminal.status,
                "reasons": operation.reduction.native_terminal.reason_codes,
                "targets": tuple(
                    (target.record_kind, target.record_id)
                    for target in operation.reduction.native_compilation.resolved_graph_targets
                ),
                "intents": tuple(
                    (intent.record_kind, intent.record_id)
                    for intent in operation.reduction.effect_materialization.record_intents
                ),
            }
            for operation in captured_request[0].ordered_operation_inputs
        )
        entities = tuple(
            intent.canonical_after_record.planning_record for intent in intents
        )
        receipt, _, _ = commit_claimed(
            service._semantic_atomic_store,
            current_claim,
            service._semantic_atomic_store.build_conflict_clarification_cas_input(
                current_claim
            ),
            terminal_kwargs={
                "subject_logical_entity_id": entities[0]["logical_entity_id"],
                "subject_entity_revision_id": entities[0]["entity_revision_id"],
                "object_logical_entity_id": entities[1]["logical_entity_id"],
                "object_entity_revision_id": entities[1]["entity_revision_id"],
                "valid_start": clock.now,
                "valid_end": clock.now + timedelta(days=30),
            },
        )
        accepted_receipts.append(receipt)
        return receipt

    service = provider_service(
        memory_plane=plane,
        conflict_attention_repository=repository,
        conflict_attention_enabled=True,
        source_user_event_verifier=source,
        conflict_clarification_pipeline=_Pipeline(canonical_commit=canonical_commit),
        now_provider=lambda: clock.now,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=(
            DeterministicTestHostBootstrapMaterialVerifier()
        ),
        source_normalization_host_bundle_builder=normalization,
    )
    host = _host_ingress()
    bootstrap_source = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="unstructured",
        operation_id="clarification-user-event",
        role="user",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=host,
    )
    assert bootstrap_source.blocked_reasons["semantic_ingestion"] == "source_only"
    seeded = _seed_canonical_conflict(
        service,
        clock.now,
        scope_ids=frozenset({"task:task:one", "user:user:alice"}),
    )
    clarification_sources = tuple(
        record
        for record in plane.list_records(source_kind="semantic_ingestion_source")
        if not record.memory_id.startswith("tx:clarification-canonical-")
    )
    assert len(clarification_sources) == 1
    source.bind(service, memory_id=clarification_sources[0].memory_id)
    atomic = service._semantic_atomic_store
    atomic._semantic_integrity_linearization = None
    real_group_commit = atomic.commit_or_reload_bootstrap_graph_group_v3

    def capture_group_commit(*, request):
        if request.source_operation_id == "clarification-race-source":
            captured_request.append(request)
        return real_group_commit(request=request)

    monkeypatch.setattr(
        atomic, "commit_or_reload_bootstrap_graph_group_v3", capture_group_commit
    )
    entered_group_cas = Event()
    release_group_cas = Event()
    conditional_attempts = []
    real_conditional_write = plane.conditionally_write_records

    def pause_first_group_cas(records, *, preconditions, authorization, **kwargs):
        primary = next(
            (
                record
                for record in records
                if record.source_kind
                == "semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
            ),
            None,
        )
        if primary is not None:
            conditional_attempts.append(primary.memory_id)
            if len(conditional_attempts) == 1:
                entered_group_cas.set()
                assert release_group_cas.wait(timeout=race_timeout_seconds)
        return real_conditional_write(
            records,
            preconditions=preconditions,
            authorization=authorization,
            **kwargs,
        )

    monkeypatch.setattr(plane, "conditionally_write_records", pause_first_group_cas)
    admissions_before = len(
        plane.list_records(source_kind="semantic_ingestion_admission_index")
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        ingestion = executor.submit(
            service.sync_event,
            operation=ProviderOperation.CHAT_USER_TURN,
            content=assertion,
            operation_id="clarification-race-source",
            role="user",
            task_id="task:race",
            user_id="user:alice",
            authenticated_host_ingress=host,
        )
        if not entered_group_cas.wait(timeout=race_timeout_seconds):
            early = ingestion.result(timeout=race_timeout_seconds)
            raise AssertionError(
                "ingestion did not reach the group CAS: "
                f"blocked={early.blocked_reasons!r}, "
                f"normalization_calls={normalization_calls!r}, "
                f"group_primaries={len(plane.list_records(source_kind='semantic_ingestion_bootstrap_graph_v3_group_commit_primary'))}"
            )
        assert len(captured_request) == 1
        proposal_calls_at_stale_cas = normalization_calls["proposal"]
        try:
            resolved = service.handle_tool_call_with_attention(
                "memorii_resolve_conflict",
                {
                    "conflict_id": seeded.conflict_id,
                    "expected_conflict_revision": seeded.conflict_revision,
                    "operation_id": "clarification-winner",
                    "action": "select",
                    "selected_candidate_ids": [seeded.candidate_ids[0]],
                    "validity_intervals": [],
                    "source_user_event_id": "clarification-user-event",
                },
                authenticated_host_ingress=host,
            )
        finally:
            release_group_cas.set()
        assert resolved.legacy_result.ok is True
        assert resolved.legacy_result.result["outcome"] == "submitted"
        assert len(accepted_receipts) == 1
        result = ingestion.result(timeout=race_timeout_seconds)

    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert normalization_calls["proposal"] == proposal_calls_at_stale_cas
    assert len(conditional_attempts) == 2
    assert len(
        plane.list_records(source_kind="semantic_ingestion_admission_index")
    ) == admissions_before + 1

    evidence_plane = (
        MemoryPlaneService(record_store=JsonlMemoryPlaneStore(plane_path))
        if backend == "jsonl"
        else plane
    )
    progress = []
    for record in evidence_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_manifest"
    ):
        if "request" not in record.content:
            continue
        request = BootstrapGraphPlanAtomicWriteRequestV3.model_validate_json(
            json.dumps(record.content.get("request"))
        )
        member = next(
            (item for item in request.members if item.member_id == "source-progress"),
            None,
        )
        if member is None:
            continue
        decoded = decode_bootstrap_graph_atomic_member_payload_v3(
            kind=member.kind, raw=member.canonical_payload
        )
        if decoded["operation_id"] == "clarification-race-source":
            progress.append(decoded)
    assert tuple(item["kind"] for item in progress) == (
        "plan_published",
        "attempt_published",
        "planned",
        "plan_published",
        "attempt_published",
        "planned",
    )
    assert len({item["operation_fence_binding_digest"] for item in progress}) == 1
    assert all(item["predecessor_progress_reference"] is None for item in progress[:3])
    assert all(item["predecessor_progress_reference"] is not None for item in progress[3:])
    assert all(item["replan_closure_reference"] is not None for item in progress[3:])
    from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_process_runner import (
        _persisted_progress_evidence,
    )

    complete_progress = _persisted_progress_evidence(
        evidence_plane, operation_id="clarification-race-source"
    )
    assert len(complete_progress) == 6
    return {"progress": complete_progress}


def test_public_accepted_clarification_stales_planned_v3_source_on_original_fence_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _exercise_public_accepted_clarification_race(tmp_path, monkeypatch, "memory")


def test_public_accepted_clarification_race_reopens_byte_identically_in_fresh_process(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "clarification-process"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "memorii"
    outputs = []
    for phase in ("first", "reopen"):
        output = tmp_path / f"clarification-{phase}.json"
        subprocess.run(
            (
                sys.executable,
                "-m",
                "tests.fixtures.semantic_ingestion.clarification_race_process_runner",
                str(storage_root),
                phase,
                str(output),
            ),
            cwd=Path(__file__).resolve().parents[4],
            env=environment,
            check=True,
            timeout=600,
        )
        outputs.append(json.loads(output.read_text(encoding="utf-8")))
    first, reopened = outputs
    assert reopened == first
    progress = first["progress"]
    assert len(progress) == 6
    assert len({item["operation_fence_binding_digest"] for item in progress}) == 1
    assert len({item["request_digest"] for item in progress}) == 1
    assert len({item["control_epoch_digest"] for item in progress}) == 1
    assert len({item["operation_lease_binding_digest"] for item in progress}) == 1
    assert len({item["writer_commit_binding_digest"] for item in progress}) == 1
    assert len({item["source_id"] for item in progress}) == 1
    assert len({item["source_digest"] for item in progress}) == 1
    assert len({item["preparation_fingerprint"] for item in progress}) == 1
    assert len({
        item["checkpoint_authority"]["delivery_principal_binding_digest"]
        for item in progress
    }) == 1
    assert len({
        item["checkpoint_authority"]["required_scope_set_digest"]
        for item in progress
    }) == 1
    assert all(item["predecessor_progress_reference"] is None for item in progress[:3])
    assert all(item["predecessor_progress_reference"] is not None for item in progress[3:])
    assert all(item["replan_closure_reference"] is not None for item in progress[3:])
    assert all(
        item["predecessor_progress_reference"]["artifact_digest"]
        == progress[2]["progress_digest"]
        and item["predecessor_progress_reference"]["member_payload_digest"]
        == progress[2]["canonical_payload_sha256"]
        for item in progress[3:]
    )


def test_failed_receipt_writes_nothing_corrected_retry_commits_and_exact_retry_skips_verifiers(tmp_path: Path) -> None:
    import importlib as _importlib
    import sys as _sys

    _support_dir = str(Path(__file__).parent / "semantic_ingestion")
    if _support_dir not in _sys.path:
        _sys.path.insert(0, _support_dir)
    _commit_claimed = _importlib.import_module("test_semantic_terminal_persistence")._commit_claimed_accepted_clarification

    def _canonical_commit(
        proposal, *, processing_operation_id, policy_fingerprint, current_claim
    ):
        # Decision (b): the claimed proposal already carries the contest
        # predecessor as its source, so the accepted terminal supersedes the
        # proposal's source assertion at record version 2.  The superset valid
        # window (30d over the contest's 2d) makes the projection split into a
        # re-contest plus a residual pass instead of resolving the clarified
        # conflict alongside the lifecycle closure's own pointer.
        return _commit_claimed(
            service._semantic_atomic_store,
            current_claim,
            service._semantic_atomic_store.build_conflict_clarification_cas_input(
                current_claim
            ),
            terminal_kwargs={
                "valid_start": clock.now,
                "valid_end": clock.now + timedelta(days=30),
            },
        )[0]

    clock = _Clock()
    repository = _repository(tmp_path / "conflicts.jsonl", clock)
    repository.append_open(_attention(), scope_ids=("scope",))
    source = _SourceVerifier()
    receipts = _ReceiptVerifier()
    service = ProviderMemoryService(
        conflict_attention_repository=repository,
        conflict_attention_enabled=True,
        authenticated_ingress_resolver=_Resolver(),
        source_user_event_verifier=source,
        user_confirmation_receipt_verifier=receipts,
        conflict_clarification_pipeline=_Pipeline(
            canonical_commit=_canonical_commit
        ),
        now_provider=lambda: clock.now,
    )
    host = AuthenticatedHostIngress(
        provider_identity="hermes",
        principal_handle=object(),
        session_handle=object(),
        received_at=clock.now,
    )
    _sync_and_bind_user_source(service, source, host)
    seeded = _seed_canonical_conflict(service, clock.now)
    arguments = {
        "conflict_id": seeded.conflict_id,
        "expected_conflict_revision": seeded.conflict_revision,
        "operation_id": "operation",
        "action": "select",
        "selected_candidate_ids": [seeded.candidate_ids[0]],
        "validity_intervals": [],
        "source_user_event_id": "user-event",
        "user_confirmation_receipt": "receipt",
    }
    before = repository._path.read_bytes()
    failed = service.handle_tool_call_with_attention(
        "memorii_resolve_conflict", arguments, authenticated_host_ingress=host
    )
    assert failed.legacy_result.error == "invalid_user_confirmation_receipt"
    assert repository._path.read_bytes() == before

    receipts.fail = False
    submitted = service.handle_tool_call_with_attention(
        "memorii_resolve_conflict", arguments, authenticated_host_ingress=host
    )
    assert submitted.legacy_result.ok is True
    assert submitted.legacy_result.result["outcome"] == "submitted"
    committed = repository._path.read_bytes()
    counts = (source.calls, receipts.calls)
    retried = service.handle_tool_call_with_attention(
        "memorii_resolve_conflict", arguments, authenticated_host_ingress=host
    )
    assert retried.legacy_result.result["outcome"] == "idempotent"
    assert (source.calls, receipts.calls) == counts
    assert repository._path.read_bytes() == committed

    divergent = dict(arguments)
    divergent["selected_candidate_ids"] = ["initech"]
    rejected = service.handle_tool_call_with_attention(
        "memorii_resolve_conflict", divergent, authenticated_host_ingress=host
    )
    assert rejected.legacy_result.error == "conflict_operation_mismatch"
    assert (source.calls, receipts.calls) == counts
    assert repository._path.read_bytes() == committed

    stale_arguments = dict(arguments)
    stale_arguments["operation_id"] = "operation-stale"
    stale = HermesMemoryProvider(service).handle_tool_call_with_attention(
        "memorii_resolve_conflict", stale_arguments, authenticated_host_ingress=host
    )
    assert stale.legacy_result.ok is True
    assert stale.legacy_result.result["outcome"] == "stale_revision"
    # The canonical lifecycle is the single authority: once the clarification
    # has committed, a stale retry observes the conflict RESOLVED (the
    # projection's re-contest opens as its own conflict), not the file
    # ledger's intermediate clarification_submitted display state.
    assert stale.legacy_result.result["attention"]["status"] == "resolved"
    assert (source.calls, receipts.calls) == counts
    assert repository._path.read_bytes() == committed


@pytest.mark.parametrize(
    "mutation",
    (
        "cross_tenant",
        "cross_principal",
        "cross_scope",
        "source_id",
        "source_digest",
        "source_bytes",
    ),
)
def test_resolution_rejects_detached_source_proof_with_zero_durable_effects(
    tmp_path: Path,
    mutation: str,
) -> None:
    clock = _Clock()
    repository = _repository(tmp_path / f"detached-{mutation}.jsonl", clock)
    repository.append_open(_attention(), scope_ids=("scope",))
    bound = _SourceVerifier()

    class DetachedVerifier:
        def verify_user_event(self, **kwargs) -> AuthorizedUserEventProof:
            proof = bound.verify_user_event(**kwargs)
            values = proof.model_dump(mode="python")
            if mutation == "cross_tenant":
                values["tenant_id"] = "other-tenant"
            elif mutation == "cross_principal":
                values["principal_id"] = "other-principal"
            elif mutation == "cross_scope":
                values["scope_digest"] = _digest("other-scope")
            elif mutation == "source_id":
                values["source_user_event_id"] = "other-event"
            elif mutation == "source_digest":
                values["canonical_source_bytes"] = b"detached-source"
                values["source_user_event_digest"] = hashlib.sha256(
                    values["canonical_source_bytes"]
                ).hexdigest()
            else:
                values["canonical_source_bytes"] = b"substituted-source"
            return AuthorizedUserEventProof.model_validate(values)

    service = ProviderMemoryService(
        conflict_attention_repository=repository,
        conflict_attention_enabled=True,
        authenticated_ingress_resolver=_Resolver(),
        source_user_event_verifier=DetachedVerifier(),
        conflict_clarification_pipeline=_Pipeline(),
        now_provider=lambda: clock.now,
    )
    host = AuthenticatedHostIngress(
        provider_identity="hermes",
        principal_handle=object(),
        session_handle=object(),
        received_at=clock.now,
    )
    _sync_and_bind_user_source(service, bound, host)
    seeded = _seed_canonical_conflict(service, clock.now)
    before_ledger = repository._path.read_bytes()
    before_contexts = tuple(
        record
        for record in service._memory_plane.list_records()
        if record.source_kind.startswith(
            "semantic_ingestion_conflict_clarification_"
        )
    )
    request = _request(
        conflict_id=seeded.conflict_id,
        conflict_revision=seeded.conflict_revision,
        candidate_id=seeded.candidate_ids[0],
    )
    result = HermesMemoryProvider(service).handle_tool_call_with_attention(
        "memorii_resolve_conflict",
        request.model_dump(mode="json", exclude={"user_confirmation_receipt"}),
        authenticated_host_ingress=host,
    )

    assert result.legacy_result.error == "invalid_source_user_event"
    assert repository._path.read_bytes() == before_ledger
    assert tuple(
        record
        for record in service._memory_plane.list_records()
        if record.source_kind.startswith(
            "semantic_ingestion_conflict_clarification_"
        )
    ) == before_contexts


@pytest.mark.parametrize("mutation", ("expired", "revoked", "mismatched"))
def test_resolution_rejects_invalid_confirmation_with_zero_durable_effects(
    tmp_path: Path,
    mutation: str,
) -> None:
    clock = _Clock()
    repository = _repository(tmp_path / f"receipt-{mutation}.jsonl", clock)
    repository.append_open(_attention(), scope_ids=("scope",))
    source = _SourceVerifier()

    class ReceiptVerifier:
        def verify(self, receipt, *, expected, server_time):
            del receipt
            if mutation == "revoked":
                raise ValueError("receipt key is revoked")
            valid = VerifiedUserConfirmation(
                issuer_id="issuer",
                key_id="key",
                trust_snapshot_digest=_digest("trust"),
                revocation_snapshot_digest=_digest("revocation"),
                principal_id=expected.principal_id,
                scope_digest=expected.scope_digest,
                conflict_id=expected.conflict_id,
                conflict_revision=expected.conflict_revision,
                action=expected.action,
                request_digest=expected.request_digest,
                source_user_event_id=expected.source_user_event_id,
                source_user_event_digest=expected.source_user_event_digest,
                issued_at=server_time - timedelta(seconds=1),
                expires_at=server_time + timedelta(minutes=1),
                nonce="receipt-nonce",
            )
            if mutation == "expired":
                return valid.model_copy(update={"expires_at": server_time})
            return valid.model_copy(update={"principal_id": "other-principal"})

    service = ProviderMemoryService(
        conflict_attention_repository=repository,
        conflict_attention_enabled=True,
        authenticated_ingress_resolver=_Resolver(),
        source_user_event_verifier=source,
        user_confirmation_receipt_verifier=ReceiptVerifier(),
        conflict_clarification_pipeline=_Pipeline(),
        now_provider=lambda: clock.now,
    )
    host = AuthenticatedHostIngress(
        provider_identity="hermes",
        principal_handle=object(),
        session_handle=object(),
        received_at=clock.now,
    )
    _sync_and_bind_user_source(service, source, host)
    seeded = _seed_canonical_conflict(service, clock.now)
    before_ledger = repository._path.read_bytes()
    request = _request(
        conflict_id=seeded.conflict_id,
        conflict_revision=seeded.conflict_revision,
        candidate_id=seeded.candidate_ids[0],
        receipt="receipt",
    )
    arguments = request.model_dump(
        mode="json", exclude={"user_confirmation_receipt"}
    )
    arguments["user_confirmation_receipt"] = "receipt"
    result = HermesMemoryProvider(service).handle_tool_call_with_attention(
        "memorii_resolve_conflict",
        arguments,
        authenticated_host_ingress=host,
    )

    assert result.legacy_result.error == "invalid_user_confirmation_receipt"
    assert repository._path.read_bytes() == before_ledger
    assert not tuple(
        record
        for record in service._memory_plane.list_records()
        if record.source_kind.startswith(
            "semantic_ingestion_conflict_clarification_"
        )
    )

def test_default_provider_adapter_does_not_treat_file_submission_as_canonical_work(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    repository = _repository(tmp_path / "default-adapter.jsonl", clock)
    # The ingress resolver authorizes the user:user vocabulary; the file-only
    # conflict must live in that vocabulary for the door's attention-ledger
    # fallback to authorize it.
    repository.append_open(_attention(), scope_ids=("user:user",))
    source = _SourceVerifier()
    service = ProviderMemoryService(
        conflict_attention_repository=repository,
        conflict_attention_enabled=True,
        authenticated_ingress_resolver=_Resolver(),
        source_user_event_verifier=source,
        now_provider=lambda: clock.now,
    )
    host = AuthenticatedHostIngress(
        provider_identity="hermes",
        principal_handle=object(),
        session_handle=object(),
        received_at=clock.now,
    )
    _sync_and_bind_user_source(service, source, host)
    request = _request()
    result = HermesMemoryProvider(service).handle_tool_call_with_attention(
        "memorii_resolve_conflict",
        request.model_dump(mode="json", exclude={"user_confirmation_receipt"}),
        authenticated_host_ingress=host,
    )

    assert result.legacy_result.ok, result.legacy_result.error
    assert result.legacy_result.result["outcome"] == "submitted"
    receipts = tuple(
        record
        for record in service._memory_plane.list_records()
        if record.source_kind == "semantic_ingestion_conflict_clarification_receipt"
    )
    assert receipts == ()
    assert repository._replay(repository._read_all()).current["conflict"].status == (
        ConflictStatus.CLARIFICATION_SUBMITTED
    )








def test_unsure_action_is_rejected_before_source_verification_or_append(tmp_path: Path) -> None:
    clock = _Clock()
    repository = _repository(tmp_path / "conflicts.jsonl", clock)
    repository.append_open(_attention(), scope_ids=("scope",))
    source = _SourceVerifier()
    service = ProviderMemoryService(
        conflict_attention_repository=repository,
        conflict_attention_enabled=True,
        authenticated_ingress_resolver=_Resolver(),
        source_user_event_verifier=source,
        now_provider=lambda: clock.now,
    )
    host = AuthenticatedHostIngress(
        provider_identity="hermes",
        principal_handle=object(),
        session_handle=object(),
        received_at=clock.now,
    )
    before = repository._path.read_bytes()
    result = service.handle_tool_call_with_attention(
        "memorii_resolve_conflict",
        {
            "conflict_id": "conflict",
            "expected_conflict_revision": _digest("revision"),
            "operation_id": "operation",
            "action": "unsure",
            "selected_candidate_ids": [],
            "validity_intervals": [],
            "source_user_event_id": "user-event",
        },
        authenticated_host_ingress=host,
    )
    assert result.legacy_result.error == "invalid_conflict_resolution"
    assert source.calls == 0
    assert repository._path.read_bytes() == before


def test_integrity_resolution_rejects_before_source_or_ledger_mutation(tmp_path: Path) -> None:
    clock = _Clock()
    repository = _repository(tmp_path / "conflicts.jsonl", clock)
    # The ingress resolver authorizes the user:user vocabulary, so the
    # integrity incident must be recorded in that vocabulary for the door's
    # attention pre-check to authorize and classify it.
    repository.append_open(_attention(integrity=True), scope_ids=("user:user",))
    source = _SourceVerifier()
    service = ProviderMemoryService(
        conflict_attention_repository=repository,
        conflict_attention_enabled=True,
        authenticated_ingress_resolver=_Resolver(),
        source_user_event_verifier=source,
        now_provider=lambda: clock.now,
    )
    host = AuthenticatedHostIngress(
        provider_identity="hermes",
        principal_handle=object(),
        session_handle=object(),
        received_at=clock.now,
    )
    before = repository._path.read_bytes()
    result = service.handle_tool_call_with_attention(
        "memorii_resolve_conflict",
        {
            "conflict_id": "conflict",
            "expected_conflict_revision": _digest("revision"),
            "operation_id": "operation",
            "action": "neither",
            "selected_candidate_ids": [],
            "validity_intervals": [],
            "source_user_event_id": "user-event",
        },
        authenticated_host_ingress=host,
    )
    assert result.legacy_result.error == "operator_action_required"
    assert source.calls == 0
    assert repository._path.read_bytes() == before

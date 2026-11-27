"""Storage administration owner: initialization, signed publication, verification.

Implements the recoverable two-owner publication protocol between the
owner-only control database and the shared application-data partition.
Data verification — never a committed flag — determines recovery: a prepared
intent with exact-old data aborts, with exact-new data finalizes, and any
third state quarantines. Fresh installation is an explicit owner operation
on a verified empty root, and the intent candidate always equals the tuple
recorded in the data generation.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

from pydantic import ValidationError

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.memory_plane.store import (
    MemoryPlanePrecondition,
    MemoryPlaneWriteAuthorization,
)
from memorii.core.persistence.contracts import (
    RUNTIME_CONTROL_JOURNAL_SIGNATURE_PURPOSE,
    RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
    BatchPosition,
    GenesisPosition,
    InstallationControlJournalEntry,
    InstallationControlState,
    InstallationGenerationChangeIntent,
    PartitionRevisionVector,
    RuntimeMaterializationManifest,
    RuntimePublicationIntent,
    RuntimePublicationState,
    TrustRegistryEntry,
    canonical_json_digest,
    empty_chain_commitment,
    empty_pointer_set_digest,
)
from memorii.core.persistence.key_owner import (
    OPERATION_ORIGIN_SIGNATURE_PURPOSE,
    PARTITION_GENERATION_SIGNATURE_PURPOSE,
    LocalSigningKeyOwner,
)
from memorii.core.persistence.runtime_contracts import OperationOrigin, OperationOriginCoordinate
from memorii.core.persistence.runtime_journal import RuntimeJournalError, verify_runtime_history
from memorii.core.storage_administration.generation_selection import (
    PartitionGenerationSelector,
    read_partition_generation_selector,
    selected_partition_path,
)
from memorii.stores.sqlite.control import ControlDatabase, ControlJournalChainError
from memorii.stores.sqlite.partition import PartitionDataRepository, VerificationCookie

_CONTROL_FORMAT_VERSION = 1
DEFAULT_SIGNER_KEY_ID = "installation-control"
_UNINITIALIZED = "uninitialized"
_KNOWN_LAYOUT = frozenset(
    {"control", "partition", ".init.lock", ".publication.lock"}
)


class StorageAdministrationError(RuntimeError):
    """Installation administration operation failed."""


class InstallationQuarantinedError(StorageAdministrationError):
    """The installation is quarantined and refuses data operations."""


class InstallationIntegrityError(StorageAdministrationError):
    """Verification failed; no task-derived output may be released."""


class _RecoveryPublicationMismatch(InstallationIntegrityError):
    """The selected partition disagrees with the exact intent under recovery."""

    def __init__(self, message: str, tuple_digest: str | None) -> None:
        super().__init__(message)
        self.tuple_digest = tuple_digest


class InitializationNotPossibleError(StorageAdministrationError):
    """The root is not absent or safely empty; refusing to initialize."""


@dataclass(frozen=True)
class InitializationReceipt:
    installation_id: str
    repository_id: str
    data_generation_id: str
    receipt_digest: str


@dataclass(frozen=True)
class PublicationOutcome:
    ordinal: int
    write_revision: int
    data_revision: int
    tuple_digest: str


@dataclass(frozen=True)
class PartitionVerificationSnapshot:
    """A Tier-verified view of the partition for released reads."""

    tuple_digest: str
    ordinal: int
    manifest_digest: str
    vector: PartitionRevisionVector


@dataclass(frozen=True)
class Resolution:
    disposition: str  # clean | aborted | aborted_initialization | finalized | quarantined
    tuple_digest: str | None


class StorageAdministrationService:
    """Own installation initialization, publication and verification."""

    def __init__(
        self,
        installation_root: str | Path,
        *,
        signer_key_id: str = DEFAULT_SIGNER_KEY_ID,
        writer_enrollment=None,
    ) -> None:
        self._root = Path(installation_root)
        self._signer_key_id = signer_key_id
        self._writer_enrollment = writer_enrollment
        self._signing = LocalSigningKeyOwner(self._root / "control" / "keys")
        self._control = ControlDatabase(
            self._root / "control" / "control.sqlite3",
            journal_verifier=self._verify_journal_signature,
        )
        try:
            self._control.validate_journal()
        except ControlJournalChainError as exc:
            raise StorageAdministrationError(
                f"control journal validation failed: {exc}"
            ) from exc
        self._partition: PartitionDataRepository | None = None
        self._partition_recovery = threading.local()
        self._verified_tuples: dict[str, VerificationCookie] = {}
        # Wired by the governance enforcement entry: re-emits one journal
        # entry's revocation directive. Until wired, pending enforcements
        # are reported (never silently dropped) by the drain.
        self._forget_enforcement_emitter = None

    def set_forget_enforcement_emitter(self, emitter) -> None:
        """Wire the governance enforcement entry used by the drains.

        The emitter publishes one journal entry's revocation directive;
        the mode-resume and boot drains call it per pending entry with
        retry. Composition roots call this once the semantic runtime and
        its store exist.
        """

        if not callable(emitter):
            raise StorageAdministrationError(
                "invalid_request: enforcement emitter must be callable"
            )
        self._forget_enforcement_emitter = emitter

    # --- layout --------------------------------------------------------

    def pending_forget_enforcements(self) -> tuple[object, ...]:
        """Journal entries whose enforcement publication has not landed."""

        from memorii.core.storage_administration.suppression_journal import (
            read_suppression_records,
        )

        records = read_suppression_records(self._root / "control")
        if not records:
            return ()
        present: list[object] = []
        pending: list[object] = []
        for record in records:
            (
                present if self._forget_enforcement_present(record.suppression_id)
                else pending
            ).append(record)
        return tuple(pending)

    def _forget_enforcement_present(self, suppression_id: str) -> bool:
        """The directive index record the governance publication writes."""

        with self.partition().transaction(write=False) as connection:
            row = connection.execute(
                "SELECT 1 FROM memory_current_records WHERE memory_id = ?",
                (f"semantic_ingestion:revocation:{suppression_id}",),
            ).fetchone()
        return row is not None

    def drain_pending_forget_enforcement(self) -> int:
        """Drain pending forget enforcements; returns the still-pending count.

        Leaving the read-only barrier and boot call this; the emitter (the
        governance enforcement entry) is retried per entry until quiescent.
        """

        pending = self.pending_forget_enforcements()
        if not pending:
            return 0
        emitter = self._forget_enforcement_emitter
        if emitter is None:
            return len(pending)
        remaining = 0
        for record in pending:
            try:
                emitter(record)
            except Exception:
                remaining += 1
        return remaining

    @property
    def installation_root(self) -> Path:
        return self._root

    def control_path(self) -> Path:
        return self._root / "control" / "control.sqlite3"

    def partition_path(self) -> Path:
        path, _ = self._active_partition_selection()
        return path

    def partition(self) -> PartitionDataRepository:
        if self._partition is None:
            path, selected = self._active_partition_selection()
            identity = self._partition_file_identity(path) if path.exists() else None

            def reject_publication(repository_id: str, row: sqlite3.Row | None, message: str) -> NoReturn:
                recovering = getattr(self._partition_recovery, "intent", None)
                if recovering is not None and recovering == self._control.read_pending_intent(repository_id):
                    digest = None if row is None else str(row["tuple_digest"])
                    raise _RecoveryPublicationMismatch(message, digest)
                raise InstallationIntegrityError(message)

            def require_current_generation(connection: sqlite3.Connection) -> None:
                active_path, active = self._active_partition_selection()
                if path != active_path or self._partition_file_identity(path) != identity:
                    raise StorageAdministrationError("unavailable: partition selection changed; reopen the installation")
                named_selection = active is not None
                if active is None:
                    state = self._control.read_control_state()
                    if state is None:
                        return
                    active = self._control.read_publication_state(f"{state.installation_id}:default-partition")
                if active is None:
                    return
                row = partition.read_publication_row(connection)
                if row is None or row["generation_id"] != active.data_generation_id:
                    reject_publication(
                        active.repository_id, row, "partition generation does not match finalized control authority",
                    )
                active_digest = active.payload_digest()
                correct_tuple = row["tuple_digest"] == active_digest
                if named_selection or not correct_tuple:
                    pending = self._control.read_pending_intent(active.repository_id)
                    if pending is not None and pending != getattr(self._partition_recovery, "intent", None):
                        raise InstallationIntegrityError("selected partition requires pending publication recovery")
                else:
                    pending = None
                if not correct_tuple or (named_selection and not self._matches_signed_publication(row, active)):
                    if (
                        pending is None
                        or pending.expected_old_discriminator != active_digest
                        or row["tuple_digest"] != pending.candidate_state.payload_digest()
                        or not self._matches_signed_publication(row, pending.candidate_state)
                    ):
                        reject_publication(
                            active.repository_id, row, "selected partition does not match the finalized publication",
                        )
                    return
                if not named_selection:
                    return
                cookie = partition.verification_cookie(connection)
                if self._verified_tuples.get(active_digest) != cookie:
                    if not self._matches_materialization(connection, active, partition=partition, cookie=cookie):
                        reject_publication(
                            active.repository_id, row, "selected partition materializations are not verified",
                        )
                    self._verified_tuples = {active_digest: cookie}

            partition = PartitionDataRepository(
                path, require_existing=selected is not None, transaction_guard=require_current_generation,
                protected_storage_root=self._root / "partition",
            )
            try:
                if identity is None:
                    identity = self._partition_file_identity(path)
            except StorageAdministrationError:
                partition.close()
                raise
            self._partition = partition
        return self._partition

    def _active_partition_selection(self) -> tuple[Path, RuntimePublicationState | None]:
        """Resolve only a selector signed for the currently finalized generation."""
        partition_root = self._root / "partition"
        try:
            current = self._control.read_control_state()
            if current is not None:
                change = self._control.read_generation_change(f"{current.installation_id}:default-partition")
                if change is not None and change.phase == "prepared":
                    raise InstallationIntegrityError("partition generation change requires recovery")
            selector = read_partition_generation_selector(self._root / "control")
            if selector is None:
                return partition_root / "partition.sqlite3", None
            state = self._require_operational()
            repository_id = f"{state.installation_id}:default-partition"
            finalized = self._control.read_publication_state(repository_id)
            if (
                finalized is None
                or finalized.installation_id != state.installation_id
                or finalized.repository_id != repository_id
                or finalized.eligibility_epoch != state.eligibility_epoch
                or not self._selector_matches(selector, finalized)
                or not self._signing.verify(
                    self._signer_key_id, RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
                    finalized.payload_digest(), finalized.signature,
                )
            ):
                raise InstallationIntegrityError("partition selector does not match finalized control authority")
            return selected_partition_path(partition_root, selector.generation_id), finalized
        except (OSError, ValueError) as exc:
            raise InstallationIntegrityError("partition generation selection is unavailable") from exc

    def _selector_matches(self, selector: PartitionGenerationSelector, publication: RuntimePublicationState) -> bool:
        return (
            selector.installation_id == publication.installation_id
            and selector.repository_id == publication.repository_id
            and selector.generation_id == publication.data_generation_id
            and self._signing.verify(
                self._signer_key_id, PARTITION_GENERATION_SIGNATURE_PURPOSE,
                selector.unsigned_digest(), selector.signature,
            )
        )

    @staticmethod
    def _partition_file_identity(path: Path) -> tuple[int, int]:
        try:
            info = path.stat()
        except OSError as exc:
            raise StorageAdministrationError("unavailable: partition database identity cannot be read") from exc
        return info.st_dev, info.st_ino

    def memory_plane_store(self) -> SqliteMemoryPlaneStore:
        return SqliteMemoryPlaneStore(self.partition())

    def close(self) -> None:
        if self._partition is not None:
            self._partition.close()
            self._partition = None
        self._control.close()

    def __enter__(self) -> StorageAdministrationService:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # --- identities ----------------------------------------------------

    def _control_state(self) -> InstallationControlState:
        state = self._control.read_control_state()
        if state is None:
            raise StorageAdministrationError("installation is not initialized")
        return state

    def _require_operational(self) -> InstallationControlState:
        state = self._control_state()
        if state.quarantined_reason is not None:
            raise InstallationQuarantinedError(state.quarantined_reason)
        return state

    def _repository_id(self) -> str:
        return f"{self._control_state().installation_id}:default-partition"

    # --- initialization ------------------------------------------------

    _CANONICAL_WRITERS = (
        "memory_plane_batch",
        "runtime_change",
        "migrate",
        *(f"runtime_command:{kind}" for kind in (
            "start_task", "resume_task", "record_observation",
            "propose_state_change", "record_action_dispatch",
            "record_action_result", "checkpoint_task", "replan_task",
            "complete_task", "pause_task", "abort_task",
        )),
    )

    def _enroll_canonical_writers(self) -> None:
        """Enroll the installation's own production writers at genesis.

        The runtime command service and the memory-plane publication path
        are the composition roots this installation ships; registering them
        here keeps the all-writer barrier honest without self-authorizing
        foreign bindings (those still fail closed until enrolled).
        """
        from memorii.core.storage_administration.writer_enrollment import (
            WriterEnrollmentRegistry,
        )

        registry = WriterEnrollmentRegistry(self._root / "control" / "writers")
        for writer_id in self._CANONICAL_WRITERS:
            registry.enroll(writer_id, kind="builtin")

    def initialize(self) -> InitializationReceipt:
        """Owner-authorized fresh installation on an absent or safe root."""
        if self._root.exists():
            self._reject_foreign_root_content()
        else:
            self._root.mkdir(parents=True)
        with locked_file(self._root / ".init.lock", exclusive=True):
            existing_state = self._control.read_control_state()
            if existing_state is not None:
                return self._resume_or_conflict(existing_state)
            if self._partition_holds_data():
                raise InitializationNotPossibleError(
                    "partition data exists without control authority"
                )
            installation_id = uuid.uuid4().hex
            repository_id = f"{installation_id}:default-partition"
            generation_id = uuid.uuid4().hex
            self._stage_initial_intent(
                installation_id=installation_id,
                repository_id=repository_id,
                generation_id=generation_id,
            )
            self._stage_initial_data()
            return self.finalize_installation()

    @staticmethod
    def _effective_epoch(state: InstallationControlState) -> int:
        """The epoch a new tuple signs: base plus unconsumed pending increments."""

        return state.eligibility_epoch + state.pending_epoch_increments

    def _complete_pending_epoch_advance(self) -> bool:
        """Boot completion rule for a crash between tuple and control writes.

        If the finalized tuple already carries base+pending while control
        state still holds the pending counter (a legacy or interrupted
        cut), advance idempotently and journal it. Returns whether an
        advance happened. Callers hold the publication fence: this method
        never takes it (same-descriptor flock would self-deadlock).
        """

        state = self._control_state()
        if state.pending_epoch_increments <= 0:
            return False
        finalized = self._control.read_publication_state(self._repository_id())
        if finalized is None:
            return False
        consumed = finalized.eligibility_epoch - state.eligibility_epoch
        if consumed <= 0 or consumed > state.pending_epoch_increments:
            return False
        self._control.write_control_state(
            state.model_copy(
                update={
                    "control_revision": state.control_revision + 1,
                    "eligibility_epoch": finalized.eligibility_epoch,
                    "pending_epoch_increments": (
                        state.pending_epoch_increments - consumed
                    ),
                }
            ),
            self._journal_entry(
                operation="publication_finalized",
                after_digest=canonical_json_digest(
                    {
                        "epoch": finalized.eligibility_epoch,
                        "pending": state.pending_epoch_increments - consumed,
                    }
                ),
            ),
        )
        return True

    def _resume_or_conflict(
        self, state: InstallationControlState
    ) -> InitializationReceipt:
        # Resolve and resume under the publication fence so a duplicate init
        # cannot abort a live publisher's intent.
        with self._publication_fence():
            resolution = self.resolve_pending_publication()
            finalized = self._control.read_publication_state(self._repository_id())
            if finalized is None and state.quarantined_reason is None:
                if resolution.disposition not in ("clean", "aborted", "aborted_initialization"):
                    raise StorageAdministrationError(
                        "initialization is incomplete and could not be resumed"
                    )
                # Interrupted bootstrap with no committed generation: the
                # owner-authorized retry the design mandates.
                self._retry_interrupted_initialization(state)
                finalized = self._control.read_publication_state(self._repository_id())
            if finalized is not None and state.initialization_receipt_digest is None:
                # Crash between finalize and the receipt write: complete it.
                self._record_initialization_receipt(finalized)
                state = self._control_state()
            self._complete_pending_epoch_advance()
            state = self._control_state()
        # Outside the fence: the enforcement emitter publishes under its own
        # fence, and in read_only it reports instead of force-publishing.
        self.drain_pending_forget_enforcement()
        if finalized is None:
            raise StorageAdministrationError(
                "initialization is incomplete and could not be resumed"
            )
        if state.initialization_receipt_digest is None:
            raise StorageAdministrationError(
                "initialization identity conflicts with this root"
            )
        return InitializationReceipt(
            installation_id=state.installation_id,
            repository_id=self._repository_id(),
            data_generation_id=finalized.data_generation_id,
            receipt_digest=state.initialization_receipt_digest,
        )

    def _retry_interrupted_initialization(
        self, state: InstallationControlState
    ) -> None:
        """Re-stage and complete an interrupted bootstrap from control state."""
        with self._partition_read() as connection:
            row = self.partition().read_publication_row(connection)
            batches = self.partition().read_batch_rows(connection)
        if row is not None or batches:
            raise StorageAdministrationError(
                "partition holds data without a finalized generation; refusing retry"
            )
        self._stage_initial_intent(
            installation_id=state.installation_id,
            repository_id=self._repository_id(),
            generation_id=uuid.uuid4().hex,
            resume=True,
        )
        self._stage_initial_data()
        return self.finalize_installation()

    @contextmanager
    def _partition_read(self):
        with self.partition().transaction(write=False) as connection:
            yield connection

    def _reject_foreign_root_content(self) -> None:
        for entry in self._root.iterdir():
            if entry.name not in _KNOWN_LAYOUT:
                raise InitializationNotPossibleError(
                    f"installation root holds foreign content: {entry.name}"
                )
            if entry.is_symlink():
                raise InitializationNotPossibleError(
                    f"installation root entry is a symlink: {entry.name}"
                )
        # Known-layout interior paths must be real directories/files too:
        # a symlinked control database, key directory or partition redirects
        # authority and is rejected before any state is trusted.
        for interior in (
            self._root / "control",
            self._root / "control" / "control.sqlite3",
            self._root / "control" / "keys",
            self._root / "partition",
            self._root / "partition" / "partition.sqlite3",
        ):
            if interior.is_symlink():
                raise InitializationNotPossibleError(
                    f"installation state is a symlink: {interior.name}"
                )

    def _stage_initial_intent(
        self,
        *,
        installation_id: str,
        repository_id: str,
        generation_id: str,
        resume: bool = False,
    ) -> RuntimePublicationState:
        """First control transaction: state, trust, journal, prepared intent.

        With ``resume`` set, control state already exists from an interrupted
        bootstrap and only a fresh prepared intent is written.
        """
        fingerprint = self._ensure_signing_key()
        trust_entry = TrustRegistryEntry(
            key_id=self._signer_key_id,
            public_key_fingerprint=fingerprint,
            purpose=RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
            sequence_interval_start=1,
        )
        partition = self.partition()
        with partition.transaction(write=False) as connection:
            entries = partition.compute_materialization_manifest(connection)
        manifest = RuntimeMaterializationManifest(catalogs=entries)
        unsigned = RuntimePublicationState(
            installation_id=installation_id,
            repository_id=repository_id,
            data_generation_id=generation_id,
            position=GenesisPosition(),
            manifest_digest=manifest.digest(),
            trust_registry_digest=canonical_json_digest(
                {"entries": [trust_entry.model_dump_json()]}
            ),
            eligibility_epoch=1,
            vector=PartitionRevisionVector.genesis(),
            signature="0" * 64,
        )
        candidate = self._sign_state(unsigned)
        state = InstallationControlState(
            installation_id=installation_id,
            format_version=_CONTROL_FORMAT_VERSION,
            control_revision=1,
            eligibility_epoch=1,
            mode="active",
        )
        intent = RuntimePublicationIntent(
            intent_id=uuid.uuid4().hex,
            repository_id=repository_id,
            expected_old_discriminator=_UNINITIALIZED,
            candidate_state=candidate,
            operation_binding="initialize",
            authority_epoch=1,
            fence_token=1,
        )
        journal = self._journal_entry(
            operation="initialize",
            after_digest=canonical_json_digest(
                {"installation_id": installation_id, "intent_id": intent.intent_id}
            ),
        )
        if resume:
            self._control.write_intent(
                intent,
                self._journal_entry(
                    operation="initialize",
                    after_digest=canonical_json_digest(
                        {"intent_id": intent.intent_id, "resumed": True}
                    ),
                ),
            )
        else:
            self._control.initialize_installation(state, trust_entry, intent, journal)
        return candidate

    def _stage_initial_data(self) -> None:
        """Publish the empty data generation from the pending init intent."""
        repository_id = self._repository_id()
        intent = self._control.read_pending_intent(repository_id)
        if intent is None:
            raise StorageAdministrationError("initialization intent is missing")
        candidate = intent.candidate_state
        partition = self.partition()
        with partition.manual_write_transaction() as handle:
            connection = handle.connection
            existing = partition.read_publication_row(connection)
            if existing is not None and str(existing["tuple_digest"]) != (
                candidate.payload_digest()
            ):
                raise StorageAdministrationError(
                    "existing data generation conflicts with initialization"
                )
            if existing is None:
                partition.write_publication_row(
                    connection,
                    ordinal=0,
                    position_kind="genesis",
                    position_sequence=None,
                    position_digest=empty_chain_commitment(),
                    tuple_digest=candidate.payload_digest(),
                    generation_id=candidate.data_generation_id,
                    vector_json=candidate.vector.model_dump_json(),
                    manifest_digest=candidate.manifest_digest,
                )
            handle.commit()

    def finalize_installation(self) -> InitializationReceipt:
        """Finalize the genesis tuple and record the initialization receipt."""
        repository_id = self._repository_id()
        intent = self._control.read_pending_intent(repository_id)
        if intent is None:
            raise StorageAdministrationError("initialization intent is missing")
        candidate = intent.candidate_state
        self._finalize_publication(candidate)
        self._control.write_intent(
            intent.model_copy(update={"phase": "finalized"}),
            self._journal_entry(
                operation="publication_finalized",
                after_digest=candidate.payload_digest(),
            ),
        )
        self._enroll_canonical_writers()
        return self._record_initialization_receipt(candidate)

    def _record_initialization_receipt(
        self, candidate: RuntimePublicationState
    ) -> InitializationReceipt:
        repository_id = self._repository_id()
        receipt_digest = hashlib.sha256(
            ":".join(
                (
                    candidate.installation_id,
                    repository_id,
                    candidate.data_generation_id,
                    candidate.payload_digest(),
                )
            ).encode("ascii")
        ).hexdigest()
        state = self._control_state()
        self._control.write_control_state(
            state.model_copy(
                update={
                    "control_revision": state.control_revision + 1,
                    "initialization_receipt_digest": receipt_digest,
                }
            ),
            self._journal_entry(
                operation="initialize",
                before_digest=canonical_json_digest(
                    {"state": state.model_dump(mode="json")}
                ),
                after_digest=canonical_json_digest({"receipt": receipt_digest}),
            ),
        )
        return InitializationReceipt(
            installation_id=candidate.installation_id,
            repository_id=repository_id,
            data_generation_id=candidate.data_generation_id,
            receipt_digest=receipt_digest,
        )

    def _partition_holds_data(self) -> bool:
        if not self.partition_path().exists():
            return False
        with self._partition_read() as connection:
            row = self.partition().read_publication_row(connection)
            batches = self.partition().read_batch_rows(connection)
        return row is not None or bool(batches)

    # --- publication ---------------------------------------------------

    def publish_memory_plane_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        store: SqliteMemoryPlaneStore | None = None,
        expected_revision: int | None = None,
        expected_write_revision: int | None = None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
        authorization: MemoryPlaneWriteAuthorization | None = None,
        transaction_precondition: Callable[[], None] | None = None,
        operation_binding: str = "memory_plane_batch",
        derived_semantic_index: object | None = None,
        derived_ontology_index: object | None = None,
    ) -> PublicationOutcome:
        """Commit one memory-plane batch and its signed publication atomically.

        ``derived_semantic_index`` and ``derived_ontology_index`` are optional
        :class:`~memorii.core.memory_evolution.semantic_index.SemanticIndexProjection`
        / :class:`~memorii.core.semantic_ingestion.ontology_index.OntologyIndexProjection`
        supplied by their owners from replay authority for the post-batch
        state; each replaces its derived index generation inside the same
        publication transaction so the signed manifest covers the records
        and the derived rows together.
        """
        state = self._require_operational()
        if state.mode == "read_only" and operation_binding != "migrate":
            raise InstallationQuarantinedError(
                "installation is read_only; data publication is denied"
            )
        if self._writer_enrollment is not None:
            # All-writer barrier: an unregistered writer fails closed before
            # any active service, never as best-effort consistency.
            self._writer_enrollment.require_enrolled(operation_binding)
        memory_store = store if store is not None else self.memory_plane_store()
        with self._publication_fence():
            # Mode re-checked under the fence: a writer that passed the
            # entry check before an owner flipped read_only cannot commit
            # across the barrier.
            fenced_state = self._require_operational()
            if fenced_state.mode == "read_only" and operation_binding != "migrate":
                raise InstallationQuarantinedError(
                    "installation is read_only; data publication is denied"
                )
            resolution = self.resolve_pending_publication()
            if resolution.disposition == "quarantined":
                raise InstallationQuarantinedError("pending publication quarantined")
            finalized = self._control.read_publication_state(self._repository_id())
            if finalized is None:
                raise StorageAdministrationError("installation is not initialized")
            # Anchor the publisher on verified state: publication extends the
            # last signed tuple, never unverified rows (anti-laundering rule).
            self._verified_snapshot_locked()
            state = self._require_operational()
            partition = self.partition()
            with partition.manual_write_transaction() as handle:
                connection = handle.connection
                self._require_materialization_base(connection, finalized)
                with partition.capture_materialization(connection, finalized.manifest_digest) as capture:
                    memory_store.apply_batch_in_transaction(
                        connection,
                        records,
                        expected_revision=expected_revision,
                        expected_write_revision=expected_write_revision,
                        preconditions=preconditions,
                        authorization=authorization,
                        transaction_precondition=transaction_precondition,
                        verified_partition=True,
                    )
                    if derived_semantic_index is not None:
                        index_write_revision, index_data_revision = (
                            partition.read_revision_state(connection)
                        )
                        partition.replace_derived_semantic_index(
                            connection,
                            derived_semantic_index,
                            write_revision=index_write_revision,
                            data_revision=index_data_revision,
                        )
                    if derived_ontology_index is not None:
                        partition.replace_derived_ontology_index(
                            connection, derived_ontology_index
                        )
                forest = None if capture is None else capture.result
                candidate = self._candidate_from_transaction(
                    connection,
                    generation_id=finalized.data_generation_id,
                    epoch=self._effective_epoch(state),
                    manifest=None if forest is None else forest.manifest,
                )
                partition.write_publication_row(
                    connection,
                    ordinal=candidate.vector.partition_ordinal,
                    position_kind="batch",
                    position_sequence=_position_sequence(candidate),
                    position_digest=_position_digest(candidate),
                    tuple_digest=candidate.payload_digest(),
                    generation_id=finalized.data_generation_id,
                    vector_json=candidate.vector.model_dump_json(),
                    manifest_digest=candidate.manifest_digest,
                )
                intent = RuntimePublicationIntent(
                    intent_id=uuid.uuid4().hex,
                    repository_id=self._repository_id(),
                    expected_old_discriminator=finalized.payload_digest(),
                    candidate_state=candidate,
                    operation_binding=operation_binding,
                    authority_epoch=self._effective_epoch(state),
                    fence_token=finalized.vector.partition_ordinal + 1,
                )
                self._control.write_intent(
                    intent,
                    self._journal_entry(
                        operation="publication_prepared",
                        before_digest=finalized.payload_digest(),
                        after_digest=candidate.payload_digest(),
                    ),
                )
                cookie = partition.verification_cookie(connection)
                handle.commit()
                # Partition readers must wait for the matching control state and terminal intent.
                self._finalize_publication(candidate)
                self._control.write_intent(
                    intent.model_copy(update={"phase": "finalized"}),
                    self._journal_entry(
                        operation="publication_finalized",
                        before_digest=finalized.payload_digest(),
                        after_digest=candidate.payload_digest(),
                    ),
                )
                if forest is not None:
                    partition.cache_manifest_accumulator(cookie, forest)
                self._verified_tuples = {candidate.payload_digest(): cookie}
            return PublicationOutcome(
                ordinal=candidate.vector.partition_ordinal,
                write_revision=candidate.vector.memory_write_revision,
                data_revision=candidate.vector.memory_data_revision,
                tuple_digest=candidate.payload_digest(),
            )

    def resolve_pending_publication(self) -> Resolution:
        """Recover a prepared intent: exact-old aborts, exact-new finalizes."""
        repository_id = self._repository_id()
        change = self._control.read_generation_change(repository_id)
        if change is not None and change.phase == "prepared":
            return self._recover_generation_change(change)
        intent = self._control.read_pending_intent(repository_id)
        if intent is None:
            return Resolution(disposition="clean", tuple_digest=None)
        partition = self.partition()
        candidate_digest = intent.candidate_state.payload_digest()
        self._partition_recovery.intent = intent
        try:
            with partition.transaction(write=False) as connection:
                row = partition.read_publication_row(connection)
                data_digest = None if row is None else str(row["tuple_digest"])
                if data_digest in (
                    candidate_digest, intent.expected_old_discriminator,
                ) and partition.supports_runtime_history(connection):
                    expected = (
                        intent.candidate_state if data_digest == candidate_digest
                        else self._control.read_publication_state(repository_id)
                    )
                    if (
                        row is None or expected is None
                        or expected.payload_digest() != data_digest
                        or not self._matches_signed_publication(row, expected)
                        or not self._matches_materialization(connection, expected)
                    ):
                        self._quarantine(intent)
                        return Resolution(disposition="quarantined", tuple_digest=data_digest)
        except _RecoveryPublicationMismatch as exc:
            self._quarantine(intent)
            return Resolution(disposition="quarantined", tuple_digest=exc.tuple_digest)
        finally:
            self._partition_recovery.intent = None
        if intent.operation_binding == "migrate" and data_digest is None:
            # Exact legacy state: adoption recorded, no tuple published.
            # Abort the marker intent and retain migration-only control so
            # the owner plan can resume; never quarantine this cut.
            self._abort_intent(intent)
            return Resolution(
                disposition="aborted_initialization", tuple_digest=None
            )
        if intent.expected_old_discriminator == _UNINITIALIZED:
            if data_digest is None:
                self._abort_intent(intent)
                return Resolution(
                    disposition="aborted_initialization", tuple_digest=None
                )
            if data_digest == candidate_digest:
                self._finalize_publication(intent.candidate_state)
                self._control.write_intent(
                    intent.model_copy(update={"phase": "finalized"}),
                    self._journal_entry(
                        operation="publication_finalized",
                        after_digest=candidate_digest,
                    ),
                )
                return Resolution(disposition="finalized", tuple_digest=candidate_digest)
        else:
            if data_digest == intent.expected_old_discriminator:
                self._abort_intent(intent)
                return Resolution(disposition="aborted", tuple_digest=data_digest)
            if data_digest == candidate_digest:
                self._finalize_publication(intent.candidate_state)
                self._control.write_intent(
                    intent.model_copy(update={"phase": "finalized"}),
                    self._journal_entry(
                        operation="publication_finalized",
                        after_digest=candidate_digest,
                    ),
                )
                return Resolution(disposition="finalized", tuple_digest=candidate_digest)
        self._quarantine(intent)
        return Resolution(disposition="quarantined", tuple_digest=data_digest)

    def _recover_generation_change(self, intent: InstallationGenerationChangeIntent) -> Resolution:
        """Resolve the cutover from its authenticated physical selector and exact SQLite tuple."""
        partition_root = self._root / "partition"
        old, new = intent.old_publication, intent.candidate_publication
        publication = None
        phase: Literal["aborted", "finalized", "quarantined"] = "quarantined"
        try:
            selector = read_partition_generation_selector(self._root / "control")
            if selector is None and not intent.old_named_selector:
                default_path = partition_root / "partition.sqlite3"
                if not partition_root.is_symlink() and not default_path.is_symlink():
                    publication, path = old, default_path
            elif selector is not None:
                if self._selector_matches(selector, new):
                    publication = new
                elif intent.old_named_selector and self._selector_matches(selector, old):
                    publication = old
                if publication is not None:
                    path = selected_partition_path(partition_root, publication.data_generation_id)
            if publication is not None:
                with PartitionDataRepository(path, require_existing=True) as partition, partition.transaction(
                    write=False,
                ) as connection:
                    row = partition.read_publication_row(connection)
                    if (
                        row is not None and row["tuple_digest"] == publication.payload_digest()
                        and self._matches_signed_publication(row, publication)
                        and self._matches_materialization(connection, publication, partition=partition)
                    ):
                        phase = "aborted" if publication == old else "finalized"
        except (OSError, ValueError, sqlite3.DatabaseError):
            # The selector or its chosen bytes did not authenticate either state.
            publication = None
        terminal = intent.model_copy(update={"phase": phase})
        self._control.write_generation_change(
            terminal,
            self._journal_entry(
                operation=f"generation_change_{phase}",
                before_digest=intent.binding_digest(),
                after_digest=terminal.binding_digest(),
            ),
        )
        selected_digest = None if publication is None or phase == "quarantined" else publication.payload_digest()
        return Resolution(disposition=phase, tuple_digest=selected_digest)

    def acquire_verified_snapshot(self) -> PartitionVerificationSnapshot:
        """Tier A plus Tier B verification of the released partition state.

        The whole verification (recovery resolution, control read, data read,
        manifest comparison) is linearized under the publication fence, so a
        concurrent publisher can never produce a torn old-control/new-data
        view; readers see one coherent finalized tuple.
        """
        with self._publication_fence():
            return self._verified_snapshot_locked()

    @contextmanager
    def verified_operation_context(
        self,
    ) -> Iterator[tuple[InstallationControlState, RuntimePublicationState]]:
        """Hold the publication fence through origin preparation or receipt release."""
        with self._publication_fence():
            self.resolve_pending_publication()
            state = self._require_operational()
            snapshot = self._verified_snapshot_locked()
            finalized = self._control.read_publication_state(self._repository_id())
            if finalized is None or finalized.payload_digest() != snapshot.tuple_digest:
                raise InstallationIntegrityError("verified operation tuple is missing")
            yield state, finalized

    def current_publication_in_fence(self) -> tuple[InstallationControlState, RuntimePublicationState]:
        """Read authority coordinates from a publication fence already held by the caller."""
        state = self._require_operational()
        finalized = self._control.read_publication_state(self._repository_id())
        if finalized is None:
            raise InstallationIntegrityError("current publication tuple is missing")
        return state, finalized

    def sign_operation_origin(self, coordinate: OperationOriginCoordinate) -> OperationOrigin:
        """Sign a resolved operation coordinate using the installation key owner."""
        return OperationOrigin(
            coordinate=coordinate,
            signature=self._signing.sign(
                self._signer_key_id,
                OPERATION_ORIGIN_SIGNATURE_PURPOSE,
                coordinate.signing_digest(),
            ),
        )

    def verify_operation_origin(self, proof: OperationOrigin) -> bool:
        """Authenticate origin with the configured installation key and purpose."""
        try:
            return self._signing.verify(
                self._signer_key_id,
                OPERATION_ORIGIN_SIGNATURE_PURPOSE,
                proof.coordinate.signing_digest(),
                proof.signature,
            )
        except (PermissionError, ValueError):
            return False

    def _verified_snapshot_locked(self) -> PartitionVerificationSnapshot:
        repository_id = self._repository_id()
        resolution = self.resolve_pending_publication()
        if resolution.disposition == "quarantined":
            raise InstallationQuarantinedError("pending publication quarantined")
        state = self._require_operational()
        finalized = self._control.read_publication_state(repository_id)
        if finalized is None:
            raise StorageAdministrationError("installation is not initialized")
        if finalized.eligibility_epoch != state.eligibility_epoch:
            raise InstallationIntegrityError(
                "finalized tuple epoch does not match control state"
            )
        partition = self.partition()
        manifest_mismatch = False
        with partition.transaction(write=False) as connection:
            cookie = partition.verification_cookie(connection)
            row = partition.read_publication_row(connection)
            if row is None or str(row["tuple_digest"]) != finalized.payload_digest():
                raise InstallationIntegrityError(
                    "partition data does not match the finalized control tuple"
                )
            if partition.supports_runtime_history(connection) and not self._matches_signed_publication(
                row, finalized,
            ):
                raise InstallationIntegrityError("partition metadata does not match the signed publication")
            if self._verified_tuples.get(finalized.payload_digest()) != cookie:
                manifest_mismatch = not self._matches_materialization(connection, finalized, cookie=cookie)
        if manifest_mismatch:
            self._quarantine_manifest_mismatch(finalized)
            raise InstallationIntegrityError(
                "materialization manifest does not match the signed tuple"
            )
        self._verified_tuples = {finalized.payload_digest(): cookie}
        return PartitionVerificationSnapshot(
            tuple_digest=finalized.payload_digest(),
            ordinal=finalized.vector.partition_ordinal,
            manifest_digest=finalized.manifest_digest,
            vector=finalized.vector,
        )

    def _matches_signed_publication(self, row: sqlite3.Row, finalized: RuntimePublicationState) -> bool:
        try:
            return (
                row["generation_id"] == finalized.data_generation_id
                and row["position_kind"] == finalized.position.kind
                and row["position_sequence"] == _position_sequence(finalized)
                and row["position_digest"] == _position_digest(finalized)
                and row["ordinal"] == finalized.vector.partition_ordinal
                and row["manifest_digest"] == finalized.manifest_digest
                and PartitionRevisionVector.model_validate_json(row["vector_json"]) == finalized.vector
                and self._signing.verify(
                    self._signer_key_id, RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
                    finalized.payload_digest(), finalized.signature,
                )
            )
        except (PermissionError, ValidationError):
            return False

    def _matches_materialization(
        self, connection: sqlite3.Connection, finalized: RuntimePublicationState,
        *, partition: PartitionDataRepository | None = None, cookie: VerificationCookie | None = None,
    ) -> bool:
        try:
            if partition is None:
                partition = self.partition()
            if partition.supports_runtime_history(connection) and partition.read_revision_state(connection) != (
                finalized.vector.memory_write_revision, finalized.vector.memory_data_revision,
            ):
                return False
            forest = partition.rebuild_manifest_accumulator(connection)
            manifest = (
                forest.manifest if forest is not None else RuntimeMaterializationManifest(
                    catalogs=partition.compute_materialization_manifest(connection),
                )
            )
            if manifest.digest() != finalized.manifest_digest:
                return False
            verify_runtime_history(
                connection,
                finalized=finalized,
                verify=lambda purpose, digest, signature: self._signing.verify(
                    self._signer_key_id, purpose, digest, signature,
                ),
                checkpoint_signer_key_id=self._signer_key_id,
                checkpoint_signer_fingerprint=(
                    self._signing.public_key_fingerprint(self._signer_key_id)
                    if finalized.checkpoint_digest is not None else None
                ),
            )
            if cookie is not None:
                if cookie != partition.verification_cookie(connection):
                    return False
                if forest is not None:
                    partition.cache_manifest_accumulator(cookie, forest)
        except (PermissionError, RuntimeJournalError, ValueError, sqlite3.DatabaseError):
            return False
        return True

    def _require_materialization_base(
        self, connection: sqlite3.Connection, finalized: RuntimePublicationState,
    ) -> None:
        """Bind the protected write-side cache inside the SQLite write lock."""
        partition = self.partition()
        row = partition.read_publication_row(connection)
        if (
            row is None or row["tuple_digest"] != finalized.payload_digest()
            or (partition.supports_runtime_history(connection) and not self._matches_signed_publication(row, finalized))
        ):
            raise InstallationIntegrityError("partition pre-state does not match the finalized control tuple")
        cookie = partition.verification_cookie(connection)
        cache_matches = (
            self._verified_tuples.get(finalized.payload_digest()) == cookie
            and partition.has_verified_manifest_base(connection, finalized.manifest_digest)
        )
        if not cache_matches and not self._matches_materialization(connection, finalized, cookie=cookie):
            raise InstallationIntegrityError("materialization base changed before publication")

    # --- internal ------------------------------------------------------

    @contextmanager
    def _publication_fence(self):
        with locked_file(self._root / ".publication.lock", exclusive=True):
            yield

    def _ensure_signing_key(self) -> str:
        if not self._signing.has_key(self._signer_key_id):
            self._signing.create_key(self._signer_key_id)
        return self._signing.public_key_fingerprint(self._signer_key_id)

    def _sign_state(self, unsigned: RuntimePublicationState) -> RuntimePublicationState:
        signature = self._signing.sign(
            self._signer_key_id,
            RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
            unsigned.payload_digest(),
        )
        return unsigned.model_copy(update={"signature": signature})

    def _candidate_from_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        generation_id: str,
        epoch: int,
        manifest: RuntimeMaterializationManifest | None = None,
    ) -> RuntimePublicationState:
        partition = self.partition()
        row = partition.read_publication_row(connection)
        prior_ordinal = 0 if row is None else int(row["ordinal"])
        if manifest is None:
            manifest = RuntimeMaterializationManifest(catalogs=partition.compute_materialization_manifest(connection))
        write_revision, data_revision = partition.read_revision_state(connection)
        state = self._control_state()
        previous = self._control.read_publication_state(self._repository_id()) if row is not None else None
        vector = PartitionRevisionVector(
            partition_ordinal=prior_ordinal + 1,
            runtime_position=GenesisPosition() if previous is None else previous.vector.runtime_position,
            memory_write_revision=write_revision,
            memory_data_revision=data_revision,
            semantic_position=GenesisPosition() if previous is None else previous.vector.semantic_position,
            ontology_pointer_digest=(
                empty_pointer_set_digest() if previous is None else previous.vector.ontology_pointer_digest
            ),
        )
        trust_digest = self._trust_registry_digest()
        unsigned = RuntimePublicationState(
            installation_id=state.installation_id,
            repository_id=self._repository_id(),
            data_generation_id=generation_id,
            position=BatchPosition(
                sequence=prior_ordinal + 1, digest=manifest.digest()
            ),
            manifest_digest=manifest.digest(),
            trust_registry_digest=trust_digest,
            eligibility_epoch=epoch,
            vector=vector,
            runtime_history_ancestry=() if previous is None else previous.runtime_history_ancestry,
            checkpoint_digest=(
                previous.checkpoint_digest if previous is not None and previous.trust_registry_digest == trust_digest else None
            ),
            signature="0" * 64,
        )
        return self._sign_state(unsigned)

    def _finalize_publication(self, candidate: RuntimePublicationState) -> None:
        state = self._control_state()
        consumed = candidate.eligibility_epoch - state.eligibility_epoch
        if consumed > 0:
            # The tuple rode pending epoch increments (a barrier-gated
            # revocation): advance the base epoch and decrement the pending
            # counter in the SAME control transaction that writes the tuple,
            # so Tier A equality between tuple and control state never
            # diverges — including across a crash at this exact cut.
            if consumed > state.pending_epoch_increments:
                raise InstallationIntegrityError(
                    "finalized tuple epoch exceeds the recorded pending increments"
                )
            self._control.write_finalized_publication(
                self._repository_id(),
                candidate,
                state.model_copy(
                    update={
                        "control_revision": state.control_revision + 1,
                        "eligibility_epoch": candidate.eligibility_epoch,
                        "pending_epoch_increments": (
                            state.pending_epoch_increments - consumed
                        ),
                    }
                ),
                self._journal_entry(
                    operation="publication_finalized",
                    after_digest=candidate.payload_digest(),
                ),
            )
            return
        self._control.write_publication_state(
            self._repository_id(),
            candidate,
            self._journal_entry(
                operation="publication_finalized",
                after_digest=candidate.payload_digest(),
            ),
        )

    def _abort_intent(self, intent: RuntimePublicationIntent) -> None:
        before = (
            intent.expected_old_discriminator
            if intent.expected_old_discriminator != _UNINITIALIZED
            else None
        )
        self._control.write_intent(
            intent.model_copy(update={"phase": "aborted"}),
            self._journal_entry(
                operation="publication_aborted", before_digest=before
            ),
        )

    def _quarantine(self, intent: RuntimePublicationIntent) -> None:
        reason = "prepared publication intent does not match old or new data state"
        # Quarantine state first: if the process dies between the two control
        # writes, the installation is already fail-closed; the intent record
        # merely documents the decision.
        self._quarantine_state(reason)
        self._control.write_intent(
            intent.model_copy(update={"phase": "quarantined"}),
            self._journal_entry(operation="publication_quarantined"),
        )

    def _quarantine_manifest_mismatch(
        self, finalized: RuntimePublicationState
    ) -> None:
        reason = "partition rows do not match the signed materialization manifest"
        self._quarantine_state(reason, before_digest=finalized.payload_digest())

    def _quarantine_state(self, reason: str, *, before_digest: str | None = None) -> None:
        state = self._control_state()
        self._control.write_control_state(
            state.model_copy(
                update={
                    "control_revision": state.control_revision + 1,
                    "quarantined_reason": reason,
                }
            ),
            self._journal_entry(
                operation="publication_quarantined",
                before_digest=before_digest,
                after_digest=canonical_json_digest({"reason": reason}),
            ),
        )

    def _journal_entry(
        self,
        *,
        operation: str,
        before_digest: str | None = None,
        after_digest: str | None = None,
    ) -> InstallationControlJournalEntry:
        revision, prior_digest = self._control.next_journal_position()
        unsigned = InstallationControlJournalEntry(
            revision=revision,
            prior_digest=prior_digest,
            operation=operation,  # type: ignore[arg-type]
            before_digest=before_digest,
            after_digest=after_digest,
            entry_digest="0" * 64,
            signer_key_id=self._signer_key_id,
            signature="0",
        )
        entry_digest = canonical_json_digest(unsigned.unsigned_payload())
        signature = self._signing.sign(
            self._signer_key_id,
            RUNTIME_CONTROL_JOURNAL_SIGNATURE_PURPOSE,
            entry_digest,
        )
        return unsigned.model_copy(
            update={"entry_digest": entry_digest, "signature": signature}
        )

    def _trust_registry_digest(self) -> str:
        entries: Sequence[TrustRegistryEntry] = self._control.list_trust_entries()
        if not entries:
            return empty_pointer_set_digest()
        return canonical_json_digest(
            {"entries": [entry.model_dump_json() for entry in entries]}
        )

    def _verify_journal_signature(
        self, key_id: str, purpose: str, message: str, signature: str
    ) -> bool:
        try:
            return self._signing.verify(key_id, purpose, message, signature)
        except (PermissionError, ValueError):
            return False


def _position_sequence(candidate: RuntimePublicationState) -> int | None:
    if isinstance(candidate.position, BatchPosition):
        return candidate.position.sequence
    return None


def _position_digest(candidate: RuntimePublicationState) -> str:
    if isinstance(candidate.position, BatchPosition):
        return candidate.position.digest
    return empty_chain_commitment()


__all__ = [
    "InitializationNotPossibleError",
    "InitializationReceipt",
    "InstallationIntegrityError",
    "InstallationQuarantinedError",
    "PartitionVerificationSnapshot",
    "PublicationOutcome",
    "Resolution",
    "StorageAdministrationError",
    "StorageAdministrationService",
]

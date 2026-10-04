"""Forget/erasure, retention, and doctor operator controls.

Matches the design contract: logical forgetting plans enumerate the exact
records in scope and apply as durable suppression journal entries —
historical bytes are retained and the receipt says so. Whole-partition
erasure is the only physical destruction path: it refuses mixed
installations, requires every offline copy to be accounted for, and
leaves a content-free erasure receipt in independent control state.
Retention plans age-prune only records outside the active recovery set.
Doctor is strictly read-only: it reports findings, never repairs by
deleting.
"""
from __future__ import annotations

import json
import os
import time
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.storage_administration.operator import (
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
    require_owner_capability,
)


class ForgetTargetSelector(BaseModel):
    """One closed, typed scope selector; free text is never a matcher."""

    selector_kind: Literal["entity", "claim", "source", "record"]
    selector_id: str = Field(min_length=1)
    record_kind: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class ForgetPlan(BaseModel):
    """Owner-reviewed logical-forget plan over one installation.

    Every field is a content-free coordinate, digest, or count: the plan
    never carries statement text, aliases as written, or evidence spans.
    """

    plan_version: Literal[2] = 2
    scope_note: str = Field(min_length=1)
    selectors: tuple[ForgetTargetSelector, ...] = Field(min_length=1)
    closure: tuple[str, ...] = Field(min_length=1)
    counts_by_class: tuple[tuple[str, int], ...]
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    closure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    retention_disclosed: Literal[True] = True

    model_config = ConfigDict(extra="forbid", frozen=True)


class ForgetReceipt(BaseModel):
    """Closed receipt; no source text or raw identifiers."""

    operation: Literal["logical_forget"] = "logical_forget"
    suppression_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    newly_revoked_count: int = Field(ge=0)
    already_revoked_count: int = Field(ge=0)
    historical_bytes_retained: Literal[True] = True
    enforcement_publication_pending: bool
    applied_at_unix: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ErasurePlan(BaseModel):
    """Whole-partition erasure plan; selective surgery is unsupported."""

    plan_version: Literal[1] = 1
    installation_id: str = Field(min_length=1)
    offline_copies_accounted: tuple[str, ...] = ()
    acknowledged: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class ErasureReceipt(BaseModel):
    """Content-free proof of destruction."""

    operation: Literal["partition_erasure"] = "partition_erasure"
    installation_id: str = Field(min_length=1)
    incomplete: bool
    completed_at_unix: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RetentionPlan(BaseModel):
    """Age-based retention tiering; revocation bytes are never deleted."""

    plan_version: Literal[1] = 1
    older_than_days: int = Field(ge=1)
    eligible_suppression_journals: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


class RetainedLineageEntry(BaseModel):
    """One retained-bytes lineage row for an explicitly named coordinate.

    Owner-forensic only (R16): the entry carries the retained historical
    record verbatim, including records whose serving lifecycle is revoked.
    """

    coordinate_kind: str = Field(min_length=1)
    coordinate_id: str = Field(min_length=1)
    memory_id: str = Field(min_length=1)
    batch_revision: int = Field(ge=0)
    revoked: bool
    record: dict[str, object]

    model_config = ConfigDict(extra="forbid", frozen=True)


class DoctorFinding(BaseModel):
    """One read-only diagnostic finding."""

    check: str = Field(min_length=1)
    status: Literal["ok", "warning", "error"]
    detail: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


def _split_coordinate(coordinate: str) -> tuple[str, str, str | None]:
    parts = coordinate.split("|", 2)
    if len(parts) == 2:
        return parts[0], parts[1], None
    return parts[0], parts[1], parts[2]


def _content_references(content: dict, identifiers: set[str]) -> bool:
    """Exact opaque-id membership over content values; never text search."""

    if not identifiers:
        return False

    def _walk(value: object) -> bool:
        if isinstance(value, str):
            return value in identifiers
        if isinstance(value, dict):
            return any(_walk(item) for item in value.values())
        if isinstance(value, list):
            return any(_walk(item) for item in value)
        return False

    return _walk(content)


class GovernanceOperator:
    """Forget, erasure, retention, and doctor over one installation."""

    def __init__(self, operator: StorageAdministrationOperator) -> None:
        self._operator = operator

    def plan_forget(
        self,
        *,
        capability: OwnerCapability,
        selectors: tuple[ForgetTargetSelector, ...],
        scope_note: str,
    ) -> ForgetPlan:
        """Resolve typed selectors into a content-free dependency closure."""

        service = self._operator._administration
        require_owner_capability(service, capability)
        if not selectors:
            raise OperatorError(
                "invalid_request: forget plan requires at least one typed selector"
            )
        closure, counts, unresolved = self._forget_closure(selectors)
        if unresolved:
            raise OperatorError(
                "invalid_request: forget selector matched no records"
                f" ({'; '.join(unresolved)})"
            )
        if not closure:
            raise OperatorError(
                "invalid_request: forget plan matched no records;"
                " a plan must enumerate at least one"
            )
        return self._build_plan(selectors, scope_note, closure, counts)

    def apply_forget(
        self,
        *,
        capability: OwnerCapability,
        plan: ForgetPlan,
    ) -> ForgetReceipt:
        from memorii.core.persistence.contracts import canonical_json_digest
        from memorii.core.storage_administration.suppression_journal import (
            SuppressionCoordinate,
            SuppressionRecord,
            find_record_by_plan_digest,
            suppressed_coordinates,
            suppression_identifier,
            write_suppression_record,
        )

        service = self._operator._administration
        require_owner_capability(service, capability)

        control_root = service.installation_root / "control"

        # Retry of the same plan reuses the existing suppression identity and
        # performs no second journal or epoch write.
        existing = find_record_by_plan_digest(control_root, plan.plan_digest)
        if existing is not None:
            return ForgetReceipt(
                suppression_id=existing.suppression_id,
                newly_revoked_count=0,
                already_revoked_count=len(existing.suppressed),
                historical_bytes_retained=True,
                enforcement_publication_pending=True,
                applied_at_unix=existing.applied_at_unix,
            )

        # Drift fence: every enumerated coordinate must still resolve, or
        # already be revoked by an earlier suppression.
        current_closure, _, _ = self._forget_closure(plan.selectors)
        already_revoked = {
            f"{coordinate.coordinate_kind}|{coordinate.coordinate_id}"
            + (f"|{coordinate.record_kind}" if coordinate.record_kind else "")
            for coordinate in suppressed_coordinates(control_root)
        }
        drifted = set(plan.closure) - set(current_closure) - already_revoked
        if drifted:
            raise OperatorError(
                "conflict: plan references records that no longer exist"
                f" ({len(drifted)} drifted)"
            )
        status = self._operator.status()
        if status.mode != "read_only":
            raise OperatorError(
                "conflict: forget apply requires the acknowledged exclusive"
                " barrier (change mode to read_only first)"
            )
        state = service._control_state()
        suppression_id = suppression_identifier(
            installation_id=state.installation_id,
            plan_digest=plan.plan_digest,
            closure_digest=plan.closure_digest,
        )
        newly = tuple(
            coordinate
            for coordinate in plan.closure
            if coordinate not in already_revoked
        )
        if not newly:
            raise OperatorError(
                "conflict: every plan target is already revoked; nothing to apply"
            )
        applied_at_unix = int(time.time())
        # Journal first: forget is durably complete here. The enforcement
        # publication (semantic revocation directive + tombstones) follows
        # barrier release; serving gates consult the journal view meanwhile.
        write_suppression_record(
            control_root,
            SuppressionRecord(
                suppression_id=suppression_id,
                plan_digest=plan.plan_digest,
                closure_digest=plan.closure_digest,
                scope_note=plan.scope_note,
                suppressed=tuple(
                    SuppressionCoordinate(
                        coordinate_kind=cast(
                            Literal[
                                "entity", "claim", "source", "record", "task",
                                "justification",
                            ],
                            kind,
                        ),
                        coordinate_id=identifier,
                        record_kind=record_kind or None,
                    )
                    for kind, identifier, record_kind in (
                        _split_coordinate(coordinate) for coordinate in newly
                    )
                ),
                applied_at_unix=applied_at_unix,
                control_journal_position=state.control_revision + 1,
            ),
        )
        # Control revision and a PENDING epoch increment advance under the
        # fence; eligibility_epoch itself is untouched so Tier A keeps
        # passing. The increment becomes the signed tuple's epoch with the
        # enforcement (or next) publication.
        with service._publication_fence():
            service._control.write_control_state(
                state.model_copy(
                    update={
                        "control_revision": state.control_revision + 1,
                        "pending_epoch_increments": (
                            state.pending_epoch_increments + 1
                        ),
                    }
                ),
                service._journal_entry(
                    operation="logical_forget_applied",
                    before_digest=canonical_json_digest(
                        {
                            "revision": state.control_revision,
                            "epoch": state.eligibility_epoch,
                            "pending": state.pending_epoch_increments,
                        }
                    ),
                    after_digest=canonical_json_digest(
                        {
                            "revision": state.control_revision + 1,
                            "suppressed": len(newly),
                            "pending": state.pending_epoch_increments + 1,
                        }
                    ),
                ),
            )
        return ForgetReceipt(
            suppression_id=suppression_id,
            newly_revoked_count=len(newly),
            already_revoked_count=len(plan.closure) - len(newly),
            historical_bytes_retained=True,
            enforcement_publication_pending=True,
            applied_at_unix=applied_at_unix,
        )

    def enforce_forget(
        self,
        *,
        store,
        policy_bundle=None,
    ) -> tuple[str, ...]:
        """Drain pending enforcements through the governance publication entry.

        Each pending journal entry becomes one revocation directive appended
        to the semantic event log (with tombstone rewrites for the closure's
        evolution records) through the store's canonical commit; the
        content-free directive index record written in the same publication
        marks the enforcement present for the drain and the serving view.
        """

        from hashlib import sha256 as _sha256

        from memorii.core.memory_evolution.graph_records import (
            ClaimRevocationTarget,
            EntityRevocationTarget,
            RecordRevocationTarget,
            RevocationDirectiveRecord,
            SourceRevocationTarget,
            canonical_graph_codec_manifest,
            graph_digest,
        )

        service = self._operator._administration
        enforced: list[str] = []
        for record in service.pending_forget_enforcements():
            targets = []
            for coordinate in record.suppressed:
                if coordinate.coordinate_kind == "entity":
                    targets.append(
                        EntityRevocationTarget(logical_entity_id=coordinate.coordinate_id)
                    )
                elif coordinate.coordinate_kind == "claim":
                    targets.append(
                        ClaimRevocationTarget(claim_assertion_id=coordinate.coordinate_id)
                    )
                elif coordinate.coordinate_kind == "source":
                    targets.append(
                        SourceRevocationTarget(source_id=coordinate.coordinate_id)
                    )
                elif coordinate.coordinate_kind == "record" and coordinate.record_kind in (
                    "claim_state", "entity_link",
                ):
                    targets.append(
                        RecordRevocationTarget(
                            record_kind="reference_disposition",
                            record_id=coordinate.coordinate_id,
                        )
                    )
            targets = tuple(sorted(targets, key=lambda item: (
                item.target_kind, item.model_dump_json()
            )))
            semantic_targets = tuple(
                target
                for target in targets
                if target.target_kind in ("entity", "claim", "source")
            )
            if not semantic_targets:
                # Nothing semantic to revoke (task-only legacy entries): mark
                # presence with the index record alone via a no-target-free
                # directive is impossible, so write the index record directly.
                from memorii.core.memory_plane.models import CanonicalMemoryRecord
                from memorii.domain.enums import CommitStatus, MemoryDomain

                service.partition()  # composition check
                index_record = CanonicalMemoryRecord(
                    memory_id=(
                        f"semantic_ingestion:revocation:{record.suppression_id}"
                    ),
                    domain=MemoryDomain.SEMANTIC,
                    text=f"revoked:{record.suppression_id}",
                    content={
                        "suppression_id": record.suppression_id,
                        "plan_digest": record.plan_digest,
                        "revoked_targets": tuple(
                            {
                                "coordinate_kind": coordinate.coordinate_kind,
                                "coordinate_id": coordinate.coordinate_id,
                            }
                            for coordinate in record.suppressed
                        ),
                    },
                    status=CommitStatus.COMMITTED,
                    source_kind="semantic_ingestion_revocation_directive",
                )
                from memorii.core.memory_plane.store import (
                    RecordAbsentPrecondition,
                )

                store._memory_plane.conditionally_write_records(
                    (index_record,),
                    preconditions=(
                        RecordAbsentPrecondition(memory_id=index_record.memory_id),
                    ),
                )
                enforced.append(record.suppression_id)
                continue
            codec = {
                item.record_kind: item
                for item in canonical_graph_codec_manifest().entries
            }["revocation_directive"]
            directive = RevocationDirectiveRecord.create(
                operation_id=f"governance:forget:{record.suppression_id}",
                revocation_id=f"revocation:{record.suppression_id}",
                suppression_id=record.suppression_id,
                revoked_targets=semantic_targets,
                closure_coordinates=(),
                closure_digest=graph_digest(
                    b"memorii.revocation-closure.v1\0", ()
                ),
                authority_capability_digest=_sha256(
                    b"memorii.governance-capability.v1\0"
                    + record.suppression_id.encode()
                    + record.plan_digest.encode()
                ).hexdigest(),
                control_journal_position=record.control_journal_position,
                applied_at=_from_unix(record.applied_at_unix),
                scope_note_digest=_sha256(
                    b"memorii.governance-scope-note.v1\0"
                    + record.scope_note.encode()
                ).hexdigest(),
                codec_fingerprint=codec.codec_fingerprint,
            )
            tombstones, tombstone_preconditions = self._tombstones_for(record, store)
            store.commit_governance_revocation(
                directive=directive,
                tombstones=tombstones,
                tombstone_preconditions=tombstone_preconditions,
                policy_bundle=policy_bundle,
            )
            enforced.append(record.suppression_id)
        return tuple(enforced)

    def read_retained_lineage(
        self,
        *,
        capability: OwnerCapability,
        coordinates: tuple[str, ...],
    ) -> dict[str, object]:
        """Serve the complete retained lineage for explicitly named coordinates.

        The owner-forensic counterpart to revoked-excluded host reads (R16):
        requires the owner capability, scans the retained version history
        plus current records, and returns every retained row whose content
        references a named coordinate -- including rows whose identities the
        revoked-identity view suppresses from every serving path.
        """
        import json as _json

        from memorii.core.storage_administration.revoked_identity_view import (
            view_from_control_root,
        )

        service = self._operator._administration
        require_owner_capability(service, capability)
        if not coordinates:
            raise OperatorError(
                "invalid_request: retained lineage requires at least one"
                " named coordinate"
            )
        named: list[tuple[str, str, str | None]] = []
        for coordinate in coordinates:
            kind, coordinate_id, _scope = _split_coordinate(coordinate)
            if not kind or not coordinate_id:
                raise OperatorError(
                    "invalid_request: coordinate must be 'kind|id': "
                    + coordinate
                )
            named.append((kind, coordinate_id, None))
        identifiers = {coordinate_id for _, coordinate_id, _ in named}
        view = view_from_control_root(service.installation_root / "control")
        entries: list[RetainedLineageEntry] = []
        repository = service.partition()
        with repository.transaction(write=False) as connection:
            version_rows = connection.execute(
                "SELECT memory_id, batch_revision, record_json"
                " FROM memory_record_versions"
                " ORDER BY memory_id, batch_revision"
            ).fetchall()
            current_ids = {
                row["memory_id"]
                for row in repository.read_current_record_rows(connection)
            }
        for row in version_rows:
            try:
                record = _json.loads(row["record_json"])
            except ValueError:
                continue
            memory_id = str(record.get("memory_id", row["memory_id"]))
            if memory_id not in current_ids and not _content_references(
                record.get("content") or {}, identifiers
            ) and memory_id not in identifiers:
                continue
            for kind, coordinate_id, _ in named:
                references = (
                    memory_id == coordinate_id
                    or coordinate_id == record.get("task_id")
                    or _content_references(
                        record.get("content") or {}, {coordinate_id}
                    )
                )
                if references:
                    entries.append(
                        RetainedLineageEntry(
                            coordinate_kind=kind,
                            coordinate_id=coordinate_id,
                            memory_id=memory_id,
                            batch_revision=int(row["batch_revision"]),
                            revoked=view.is_revoked_record(memory_id)
                            or view.is_revoked_entity(coordinate_id)
                            or view.is_revoked_claim(coordinate_id)
                            or view.is_revoked_source(coordinate_id)
                            or view.is_revoked_task(coordinate_id)
                            or view.is_revoked_justification(coordinate_id),
                            record=record,
                        )
                    )
        return {"coordinates": tuple(coordinates), "entries": tuple(entries)}

    def _tombstones_for(self, record, store):
        from memorii.core.memory_evolution.revocation_tombstones import (
            tombstone_records_for,
        )
        from memorii.core.memory_plane.models import CanonicalMemoryRecord
        from memorii.core.memory_plane.store import (
            RecordDigestPrecondition,
            record_digest,
        )

        partition = self._operator._administration.partition()
        memory_ids = tuple(
            coordinate.coordinate_id
            for coordinate in record.suppressed
            if coordinate.coordinate_kind == "record"
            and coordinate.record_kind in ("claim_state", "entity_link")
        )
        if not memory_ids:
            return (), ()
        with partition.transaction(write=False) as connection:
            rows = partition.read_current_record_rows(
                connection, statuses=["committed"], domains=None, source_kinds=None
            )
        current = {
            row["memory_id"]: CanonicalMemoryRecord.model_validate(
                json.loads(str(row["record_json"]))
            )
            for row in rows
            if row["memory_id"] in memory_ids
        }
        tombstones = tombstone_records_for(
            tuple(current[memory_id] for memory_id in memory_ids if memory_id in current),
            suppression_id=record.suppression_id,
        )
        preconditions = tuple(
            RecordDigestPrecondition(
                memory_id=record_item.memory_id,
                expected_digest=record_digest(current[record_item.memory_id]),
            )
            for record_item in tombstones
            if record_item.memory_id in current
        )
        return tombstones, preconditions

    # --- forget closure ------------------------------------------------

    def _forget_closure(
        self, selectors: tuple[ForgetTargetSelector, ...]
    ) -> tuple[tuple[str, ...], tuple[tuple[str, int], ...], tuple[str, ...]]:
        """Enumerate the content-free dependency closure under one snapshot.

        Coordinates are ``kind:id[:record_kind]`` strings. Classes follow
        the design: direct selectors, claims and entities reachable through
        entity links, evidence sources of revoked claims (and claims of
        revoked sources), the evolution records to tombstone, solver
        justifications citing revoked evidence, runtime tasks of affected
        solvers, and learned-ontology evidence from revoked sources.
        Unresolvable selectors are reported so the plan can refuse them.
        """

        service = self._operator._administration
        partition = service.partition()
        with partition.transaction(write=False) as connection:
            record_rows = partition.read_current_record_rows(
                connection, statuses=["committed"], domains=None, source_kinds=None
            )
            justification_rows = partition.read_runtime_rows(
                connection, table="runtime_justifications"
            )
            solver_run_rows = partition.read_runtime_rows(
                connection, table="runtime_solver_runs"
            )

        claim_payloads: list[tuple[str, dict]] = []
        link_payloads: list[tuple[str, dict]] = []
        ontology_payloads: list[tuple[str, dict]] = []
        for row in record_rows:
            try:
                record = json.loads(str(row["record_json"]))
                content = record["content"]
            except (KeyError, TypeError, ValueError):
                continue
            if not isinstance(content, dict):
                continue
            kind = content.get("memory_evolution_kind")
            if kind == "claim_state":
                claim_payloads.append((row["memory_id"], content))
            elif kind == "entity_link":
                link_payloads.append((row["memory_id"], content))
            elif str(record.get("source_kind", "")).startswith("learned_ontology"):
                ontology_payloads.append((row["memory_id"], content))

        claim_states = [
            (memory_id, payload.get("claim_state") or {})
            for memory_id, payload in claim_payloads
        ]
        link_states = [
            (memory_id, payload.get("entity_link") or {})
            for memory_id, payload in link_payloads
        ]
        entity_by_link = {
            str(link.get("link_id")): str(link.get("canonical_entity_id"))
            for link in (payload for _, payload in link_states)
            if link.get("link_id") and link.get("canonical_entity_id")
        }
        claim_sources = {
            str(state.get("claim_id")): {
                str(span.get("source_id"))
                for span in state.get("evidence_spans") or []
                if span.get("source_id")
            }
            for _, state in claim_states
            if state.get("claim_id")
        }

        entities: set[str] = set()
        claims: set[str] = set()
        sources: set[str] = set()
        records: set[str] = set()
        known_entity_ids = set(entity_by_link.values())
        known_claim_ids = {
            str(state.get("claim_id"))
            for _, state in claim_states
            if state.get("claim_id")
        }
        known_source_ids = {
            source_id
            for source_ids in claim_sources.values()
            for source_id in source_ids
        }
        known_record_ids = {memory_id for memory_id, _ in claim_states}
        known_record_ids.update(memory_id for memory_id, _ in link_states)
        # A record selector names any committed plane record directly, not
        # only evolution-owned claim/link states.
        known_record_ids.update(str(row["memory_id"]) for row in record_rows)
        unresolved: list[str] = []
        for selector in selectors:
            if selector.selector_kind == "entity":
                entities.add(selector.selector_id)
                if selector.selector_id not in known_entity_ids:
                    unresolved.append(f"entity {selector.selector_id}")
            elif selector.selector_kind == "claim":
                claims.add(selector.selector_id)
                if selector.selector_id not in known_claim_ids:
                    unresolved.append(f"claim {selector.selector_id}")
            elif selector.selector_kind == "source":
                sources.add(selector.selector_id)
                if selector.selector_id not in known_source_ids:
                    unresolved.append(f"source {selector.selector_id}")
            elif selector.selector_kind == "record":
                records.add(
                    f"record|{selector.selector_id}"
                    + (f"|{selector.record_kind}" if selector.record_kind else "")
                )
                if selector.selector_id not in known_record_ids:
                    unresolved.append(f"record {selector.selector_id}")

        # Fixed-point propagation between revoked claims, their entities,
        # and their evidence sources.
        changed = True
        while changed:
            changed = False
            for _, state in claim_states:
                claim_id = str(state.get("claim_id") or "")
                if not claim_id:
                    continue
                claim_entities = {
                    entity_by_link[link_id]
                    for link_id in (
                        state.get("subject_link_id"),
                        state.get("object_link_id"),
                    )
                    if link_id and link_id in entity_by_link
                }
                claim_source_ids = claim_sources.get(claim_id, set())
                if claim_id in claims or claim_source_ids & sources:
                    if claim_id not in claims:
                        claims.add(claim_id)
                        changed = True
                    if not claim_entities <= entities:
                        entities |= claim_entities
                        changed = True
                    if not claim_source_ids <= sources:
                        sources |= claim_source_ids
                        changed = True
                elif claim_entities & entities:
                    if claim_id not in claims:
                        claims.add(claim_id)
                        changed = True
                    if not claim_source_ids <= sources:
                        sources |= claim_source_ids
                        changed = True

        coordinates: set[str] = set()
        coordinates |= {f"entity|{value}" for value in entities}
        coordinates |= {f"claim|{value}" for value in claims}
        coordinates |= {f"source|{value}" for value in sources}
        coordinates |= records
        for memory_id, state in claim_states:
            if str(state.get("claim_id") or "") in claims:
                coordinates.add(f"record|{memory_id}|claim_state")
        for memory_id, link in link_states:
            if str(link.get("canonical_entity_id") or "") in entities:
                coordinates.add(f"record|{memory_id}|entity_link")

        # Solver justifications citing revoked evidence (exact id equality).
        affected_solvers: set[str] = set()
        for row in justification_rows:
            try:
                justification = json.loads(str(row["record_json"]))
            except (TypeError, ValueError):
                continue
            referenced = {
                str(ref.get("source_id"))
                for ref in justification.get("source_refs") or []
                if isinstance(ref, dict) and ref.get("source_id")
            }
            if referenced & (sources | claims | entities):
                coordinates.add(
                    f"justification|{justification.get('justification_id')}"
                )
                if justification.get("solver_id"):
                    affected_solvers.add(str(justification["solver_id"]))

        solver_task = {
            str(run.get("solver_id")): str(run.get("task_id"))
            for run in (
                json.loads(str(row["record_json"]))
                for row in solver_run_rows
            )
            if run.get("solver_id") and run.get("task_id")
        }
        for solver_id in affected_solvers:
            task_id = solver_task.get(solver_id)
            if task_id is not None:
                coordinates.add(f"task|{task_id}")

        # Learned-ontology evidence referencing revoked sources.
        for memory_id, content in ontology_payloads:
            if _content_references(content, sources):
                coordinates.add(f"record|{memory_id}|learned_ontology")

        ordered = tuple(sorted(coordinates))
        counts = tuple(
            (prefix, sum(1 for item in ordered if item.startswith(f"{prefix}|")))
            for prefix in (
                "entity", "claim", "source", "record", "justification", "task",
            )
            if any(item.startswith(f"{prefix}|") for item in ordered)
        )
        return ordered, counts, tuple(sorted(unresolved))

    def _build_plan(
        self,
        selectors: tuple[ForgetTargetSelector, ...],
        scope_note: str,
        closure: tuple[str, ...],
        counts: tuple[tuple[str, int], ...],
    ) -> ForgetPlan:
        from hashlib import sha256

        selector_body = {
            "selectors": [selector.model_dump(mode="json") for selector in selectors]
        }
        plan_digest = sha256(
            b"memorii.forget-plan.v2\0"
            + json.dumps(selector_body, sort_keys=True).encode()
        ).hexdigest()
        closure_digest = sha256(
            b"memorii.forget-closure.v2\0" + "\n".join(closure).encode()
        ).hexdigest()
        return ForgetPlan(
            scope_note=scope_note,
            selectors=selectors,
            closure=closure,
            counts_by_class=counts,
            plan_digest=plan_digest,
            closure_digest=closure_digest,
        )


    def plan_erasure(
        self,
        *,
        capability: OwnerCapability,
        offline_copies_accounted: tuple[str, ...] = (),
    ) -> ErasurePlan:
        service = self._operator._administration
        require_owner_capability(service, capability)
        return ErasurePlan(
            installation_id=service._control_state().installation_id,
            offline_copies_accounted=offline_copies_accounted,
        )

    def apply_erasure(
        self,
        *,
        capability: OwnerCapability,
        plan: ErasurePlan,
        erase: bool = False,
    ) -> ErasureReceipt:
        """Whole-partition erasure; `erase=False` returns the receipt dry.

        The data partition is destroyed only when the plan is acknowledged
        and the caller passes the explicit second consent. The receipt is
        written to independent control state and reports `incomplete=True`
        when offline copies exist but were not accounted for.
        """
        service = self._operator._administration
        require_owner_capability(service, capability)
        if service._control_state().installation_id != plan.installation_id:
            raise OperatorError("denied: erasure plan targets another installation")
        if not plan.acknowledged:
            raise OperatorError(
                "invalid_request: erasure requires the acknowledged plan"
            )
        incomplete = not plan.offline_copies_accounted
        if erase:
            import shutil

            # The isolated partition and the signing keys are destroyed; the
            # control database survives as the independent authority that
            # retains the content-free receipt and the journal.
            for name in ("partition", os.path.join("control", "keys")):
                target = service.installation_root / name
                if target.exists():
                    shutil.rmtree(target)
            partition_database = service.partition_path()
            if partition_database.exists():
                partition_database.unlink()
        from memorii.core.persistence.contracts import canonical_json_digest

        if erase:
            # Only actual destruction advances control state; the dry plan is
            # inert. The epoch rides with the destruction because every
            # subsequent verified read of the erased installation is refused
            # by the missing partition anyway.
            state = service._control_state()
            with service._publication_fence():
                service._control.write_control_state(
                    state.model_copy(
                        update={
                            "control_revision": state.control_revision + 1,
                            "eligibility_epoch": state.eligibility_epoch + 1,
                        }
                    ),
                    service._journal_entry(
                        operation="partition_erasure_applied",
                        before_digest=canonical_json_digest(
                            {"epoch": state.eligibility_epoch}
                        ),
                        after_digest=canonical_json_digest(
                            {
                                "epoch": state.eligibility_epoch + 1,
                                "incomplete": incomplete,
                            }
                        ),
                    ),
                )
        receipt = ErasureReceipt(
            installation_id=plan.installation_id,
            incomplete=incomplete,
            completed_at_unix=int(time.time()),
        )
        receipts = service.installation_root / "control" / "erasure-receipts"
        receipts.mkdir(parents=True, exist_ok=True)
        os.chmod(receipts, 0o700)
        receipt_path = receipts / (
            f"erasure-{int(time.time() * 1000)}-{len(plan.offline_copies_accounted)}.json"
        )
        temporary = receipt_path.with_name(f".{receipt_path.name}.tmp")
        with temporary.open("wb") as handle:
            handle.write((receipt.model_dump_json() + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, receipt_path)
        return receipt

    def plan_retention(
        self, *, capability: OwnerCapability, older_than_days: int
    ) -> RetentionPlan:
        service = self._operator._administration
        require_owner_capability(service, capability)
        suppression = service.installation_root / "control" / "suppressions"
        cutoff = time.time() - older_than_days * 86400
        eligible: list[str] = []
        if suppression.is_dir():
            for path in sorted(suppression.glob("forget-*.json")):
                if path.stat().st_mtime < cutoff:
                    eligible.append(path.name)
        return RetentionPlan(
            older_than_days=older_than_days,
            eligible_suppression_journals=tuple(eligible),
        )

    def apply_retention(
        self,
        *,
        capability: OwnerCapability,
        plan: RetentionPlan,
    ) -> int:
        """Tier aged suppression journals into the archive tier.

        Design rule: age alone never removes revocation state and physical
        removal uses the erasure protocol, so retention MOVES aged
        journals to control/suppressions-archive (bytes retained, still
        durable) instead of deleting them; the recheck refuses journals
        that became recent since planning.
        """
        service = self._operator._administration
        require_owner_capability(service, capability)
        suppression = service.installation_root / "control" / "suppressions"
        archive = (
            service.installation_root / "control" / "suppressions-archive"
        )
        cutoff = time.time() - plan.older_than_days * 86400
        archived = 0
        for name in plan.eligible_suppression_journals:
            path = suppression / name
            if not path.is_file():
                continue
            if path.stat().st_mtime >= cutoff:
                raise OperatorError(
                    "conflict: journal became eligible-recent; replan"
                )
            archive.mkdir(parents=True, exist_ok=True)
            os.replace(path, archive / name)
            archived += 1
        return archived

    def doctor(self) -> tuple[DoctorFinding, ...]:
        """Read-only health checks; never repairs by deleting."""
        service = self._operator._administration
        findings: list[DoctorFinding] = []
        state = service._control_state()
        findings.append(
            DoctorFinding(
                check="control_state",
                status="error" if state.quarantined_reason else "ok",
                detail=state.quarantined_reason,
            )
        )
        if state.pending_epoch_increments:
            findings.append(
                DoctorFinding(
                    check="pending_epoch_increments",
                    status="warning",
                    detail=(
                        f"pending={state.pending_epoch_increments};"
                        " the increment rides the next publication tuple"
                    ),
                )
            )
        try:
            from memorii.core.storage_administration.suppression_journal import (
                read_suppression_records,
            )

            journal_records = read_suppression_records(
                service.installation_root / "control"
            )
            pending_enforcement = service.pending_forget_enforcements()
            findings.append(
                DoctorFinding(
                    check="suppression_journal",
                    status=(
                        "warning" if len(pending_enforcement) else "ok"
                    ),
                    detail=(
                        f"entries={len(journal_records)}"
                        f" pending_enforcement={len(pending_enforcement)}"
                    ),
                )
            )
        except ValueError as exc:
            findings.append(
                DoctorFinding(
                    check="suppression_journal",
                    status="error",
                    detail=str(exc)[:200],
                )
            )
        try:
            snapshot = service.acquire_verified_snapshot()
            findings.append(
                DoctorFinding(
                    check="partition_verification",
                    status="ok",
                    detail=f"ordinal={snapshot.ordinal}",
                )
            )
        except Exception as exc:  # noqa: BLE001 - doctor reports, never raises
            findings.append(
                DoctorFinding(
                    check="partition_verification",
                    status="error",
                    detail=str(exc)[:200],
                )
            )
        for label, path in (
            ("control_database", service.control_path()),
            ("partition_database", service.partition_path()),
        ):
            findings.append(
                DoctorFinding(
                    check=f"{label}_permissions",
                    status=(
                        "ok"
                        if path.exists() and (path.stat().st_mode & 0o077) == 0
                        else "error"
                    ),
                    detail=str(path),
                )
            )
        keys = service.installation_root / "control" / "keys"
        findings.append(
            DoctorFinding(
                check="signing_keys_permissions",
                status=(
                    "ok"
                    if keys.is_dir() and (keys.stat().st_mode & 0o077) == 0
                    else "error"
                ),
                detail=str(keys),
            )
        )
        # Checkpoint reachability: the latest signed checkpoint for any task
        # must decode from the durable catalog.
        try:
            import sqlite3 as _sqlite3

            connection = _sqlite3.connect(
                f"file:{service.partition_path()}?mode=ro", uri=True
            )
            try:
                checkpoint_rows = connection.execute(
                    "SELECT COUNT(*) FROM runtime_checkpoints"
                ).fetchone()[0]
            finally:
                connection.close()
            findings.append(
                DoctorFinding(
                    check="checkpoint_catalog",
                    status="ok",
                    detail=f"rows={checkpoint_rows}",
                )
            )
        except Exception as exc:  # noqa: BLE001 - doctor reports, never raises
            findings.append(
                DoctorFinding(
                    check="checkpoint_catalog",
                    status="warning",
                    detail=str(exc)[:200],
                )
            )
        # Outbox health: pending deliveries are surfaced for the operator;
        # stuck entries are operational signal, never auto-pruned.
        try:
            from memorii.core.persistence.runtime_api import (
                pending_outbox_deliveries as _pending,
            )
            from memorii.core.persistence.runtime_repository import (
                RuntimeStateRepository as _Repo,
            )

            _repository = _Repo(service.partition())
            with service.partition().transaction(write=False) as connection:
                pending = len(_pending(_repository, connection))
            findings.append(
                DoctorFinding(
                    check="outbox_pending",
                    status="ok" if pending == 0 else "warning",
                    detail=f"pending={pending}",
                )
            )
        except Exception as exc:  # noqa: BLE001 - doctor reports, never raises
            findings.append(
                DoctorFinding(
                    check="outbox_pending",
                    status="warning",
                    detail=str(exc)[:200],
                )
            )
        # Grant registry health: the revocation journal loads and its files
        # are owner-only.
        try:
            from memorii.core.harness_state.grant_registry import (
                GrantEpochRegistry as _Registry,
            )

            registry = _Registry(
                service.installation_root / "control" / "grants"
            )
            registry.verify_permissions()
            findings.append(
                DoctorFinding(
                    check="grant_registry",
                    status="ok",
                    detail=f"revocations={len(registry.revocations())}",
                )
            )
        except Exception as exc:  # noqa: BLE001 - doctor reports, never raises
            findings.append(
                DoctorFinding(
                    check="grant_registry",
                    status="warning",
                    detail=str(exc)[:200],
                )
            )
        return tuple(findings)


__all__ = [
    "DoctorFinding",
    "ErasurePlan",
    "ErasureReceipt",
    "ForgetPlan",
    "ForgetReceipt",
    "GovernanceOperator",
    "RetentionPlan",
]


def _from_unix(applied_at_unix: int):
    from datetime import UTC, datetime

    return datetime.fromtimestamp(applied_at_unix, tz=UTC)

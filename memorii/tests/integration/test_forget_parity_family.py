"""The design §10.1 parity-family expansion and the §10.3 crash-cut.

One shared fixture (the serving-parity closure: claim, entity link, a
legacy graph node for the revoked entity) walks the previously uncovered
serving rows and the in-window oracle: the journal is the serving gate of
record between apply and enforcement, every exhaustion walk stays exact,
and a crash between apply and enforcement recovers at reopen.
"""

import contextlib
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.memory_evolution.graph_records import canonical_graph_codec_manifest
from memorii.core.memory_evolution.models import MemoryGraphNode, MemoryGraphNodeType
from memorii.core.memory_evolution.service import MemoryEvolutionService
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_evolution.writer_admission import (
    writer_admission_memory_id as _writer_admission_memory_id,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.query import MemoryPlaneQuery
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.persistence.factory import PublishedMemoryPlaneStore
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    StorageAdministrationOperator,
)
from memorii.core.storage_administration.operator_governance import (
    ForgetTargetSelector,
    GovernanceOperator,
)
from memorii.core.storage_administration.revoked_identity_view import (
    view_from_control_root,
)
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from tests.integration.test_forget_serving_parity import (
    CLAIM_MEMORY_ID,
    LINK_MEMORY_ID,
    _seed_records,
)
from tests.unit.core.test_storage_administration_operator import (
    _capability,
    _operator,
)

NOW = datetime.now(UTC)
GRAPH_NODE_MEMORY_ID = "mem:evolution:graph-node:parity"


def _graph_seed_record() -> CanonicalMemoryRecord:
    node = MemoryGraphNode(
        node_id="entity:parity",
        node_type=MemoryGraphNodeType.ENTITY,
        label="parity entity",
        canonical_id="entity:parity",
        lifecycle_state="active",
        confidence=0.9,
        payload_ref="parity",
        properties={"canonical_entity_id": "entity:parity"},
    )
    return CanonicalMemoryRecord(
        memory_id=GRAPH_NODE_MEMORY_ID,
        domain=MemoryDomain.SEMANTIC,
        text="parity entity",
        content={"memory_evolution_kind": "graph_node", "graph_node": node.model_dump(mode="python")},
        status=CommitStatus.COMMITTED,
        source_kind="memory_evolution",
    )


def _forget(operator, governance, capability, *, barrier: bool) -> None:
    plan = governance.plan_forget(
        capability=capability,
        selectors=(
            ForgetTargetSelector(selector_kind="entity", selector_id="entity:parity"),
        ),
        scope_note="parity family",
    )
    if barrier:
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=operator.status().control_revision,
                reason="barrier",
            ),
            capability=capability,
        )
    governance.apply_forget(capability=capability, plan=plan)
    if barrier:
        operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=operator.status().control_revision,
                reason="resume",
            ),
            capability=capability,
        )


def test_in_window_journal_is_the_serving_gate_before_enforcement(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        plane = MemoryPlaneService(
            record_store=PublishedMemoryPlaneStore(
                service, SqliteMemoryPlaneStore(service.partition())
            )
        )
        service.publish_memory_plane_batch(
            (*_seed_records(), _graph_seed_record()),
            operation_binding="family_seed",
        )
        governance = GovernanceOperator(operator)

        from memorii.core.memory_evolution import MemoryQueryRequest

        query = MemoryQueryRequest(
            query="Who is the parity entity?", reference_time=NOW
        )
        before = MemoryEvolutionService(memory_plane=plane, revoked_view=None)
        assert len(before.retrieve(query).selected_record_ids) >= 1

        _forget(operator, governance, capability, barrier=True)

        # In-window oracle: no enforcement publication has run, and the
        # journal alone already gates every serving path that consults a
        # derived view.
        assert service.pending_forget_enforcements()
        view = view_from_control_root(
            service.installation_root / "control", records=plane.list_records()
        )
        assert view.is_revoked_entity("entity:parity")
        evolution = MemoryEvolutionService(memory_plane=plane, revoked_view=view)
        assert evolution.retrieve(query).selected_record_ids == []
    finally:
        service.close()


def test_runtime_step_and_host_query_exhaustion_exclude_revoked(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        store = PublishedMemoryPlaneStore(
            service, SqliteMemoryPlaneStore(service.partition())
        )
        plane = MemoryPlaneService(record_store=store)
        # Forty runtime records plus the parity closure; the forget revokes
        # the entity closure (claim, link, graph node) AND a contiguous
        # sixteen-record block (a bulk forget spanning entire scan chunks).
        bulk = tuple(
            CanonicalMemoryRecord(
                memory_id=f"mem:provider:runtime:bulk:{index}",
                domain=MemoryDomain.SEMANTIC,
                text=f"bulk fixture {index}",
                content={"note": f"bulk {index}"},
                visibility=MemoryRecordVisibility.RUNTIME_CONTEXT,
                status=CommitStatus.COMMITTED,
                source_kind="provider_seed",
            )
            for index in range(40)
        )
        service.publish_memory_plane_batch(
            (*_seed_records(), _graph_seed_record(), *bulk),
            operation_binding="family_seed",
        )
        governance = GovernanceOperator(operator)

        from memorii.domain.retrieval import (
            DomainRetrievalQuery,
            RetrievalNamespace,
            RetrievalScope,
        )

        query_obj = DomainRetrievalQuery(
            domain=MemoryDomain.SEMANTIC,
            scope=RetrievalScope(),
            namespace=RetrievalNamespace(memory_domain=MemoryDomain.SEMANTIC),
        )
        before_ids = {
            getattr(item, "memory_id", None)
            for item in MemoryPlaneService(record_store=store).query_runtime_memory(query_obj)
        }
        assert before_ids
        assert CLAIM_MEMORY_ID in before_ids

        bulk_revoked_ids = tuple(
            record.memory_id for record in bulk[10:26]
        )
        selectors = (
            ForgetTargetSelector(selector_kind="entity", selector_id="entity:parity"),
            *(
                ForgetTargetSelector(selector_kind="record", selector_id=memory_id)
                for memory_id in bulk_revoked_ids
            ),
        )
        plan = governance.plan_forget(
            capability=capability, selectors=selectors, scope_note="bulk family"
        )
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=operator.status().control_revision,
                reason="barrier",
            ),
            capability=capability,
        )
        governance.apply_forget(capability=capability, plan=plan)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=operator.status().control_revision,
                reason="resume",
            ),
            capability=capability,
        )
        view = view_from_control_root(
            service.installation_root / "control", records=plane.list_records()
        )

        gated = MemoryPlaneService(record_store=store, revoked_view=view)
        after_ids = {
            getattr(item, "memory_id", None)
            for item in gated.query_runtime_memory(query_obj)
        }
        assert CLAIM_MEMORY_ID not in after_ids
        assert all(memory_id not in after_ids for memory_id in bulk_revoked_ids)

        # Host record-query surface: paginate to exhaustion under the gate.
        # Kept rows (24 bulk survivors + the seed runtime claim is not seeded
        # here) force at least five pages of five; the contiguous revoked
        # block spans entire scan chunks, exercising the chunk-refill loop.
        expected_kept = sorted(
            record.memory_id
            for record in bulk
            if record.memory_id not in bulk_revoked_ids
        )
        seen: list[str] = []
        cursor = None
        steps = 0
        while True:
            steps += 1
            assert steps < 50, "cursor walk did not terminate"
            page = gated.query_records_host(
                MemoryPlaneQuery(kind="filtered_records", page_size=5), cursor=cursor
            )
            seen.extend(record.memory_id for record in page.records)
            if page.next_cursor is None:
                assert not page.truncated
                break
            cursor = page.next_cursor
        assert steps >= 5, f"exhaustion walk never paginated (steps={steps})"
        assert len(seen) == len(set(seen)), "duplicate rows across pages"
        assert sorted(seen) == expected_kept, "host query leaked revoked or dropped kept"
        assert all(
            memory_id not in (CLAIM_MEMORY_ID, LINK_MEMORY_ID, GRAPH_NODE_MEMORY_ID)
            for memory_id in seen
        )

        # Post-enforcement: the directive index record itself (coordinates
        # content, runtime-context visibility) must never serve on any host
        # surface (design 6.2.1 / the section 8 absence oracle).
        fingerprint = canonical_graph_codec_manifest().manifest_fingerprint
        writers = SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest()
        )
        if plane.get_record(_writer_admission_memory_id()) is None:
            writers.create_initial_evidence_only(
                admission_id="family-enforce",
                writer_implementation_fingerprint=fingerprint,
                graph_schema_fingerprint=fingerprint,
            )
        from memorii.core.memory_evolution.atomic_store import (
            SemanticIngestionAtomicStore,
        )

        store = SemanticIngestionAtomicStore(plane, writers)
        governance.enforce_forget(store=store)
        seen_after: list[str] = []
        cursor = None
        while True:
            page = gated.query_records_host(
                MemoryPlaneQuery(kind="filtered_records", page_size=5), cursor=cursor
            )
            seen_after.extend(record.memory_id for record in page.records)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        # Enforcement legitimately appends authority/replay records; the
        # oracle is absence: no revoked id and no directive coordinate ever
        # serves, and no previously-kept record is lost.
        assert set(expected_kept) <= set(seen_after), "kept records lost"
        assert not any(
            memory_id in bulk_revoked_ids
            or memory_id in (CLAIM_MEMORY_ID, LINK_MEMORY_ID, GRAPH_NODE_MEMORY_ID)
            for memory_id in seen_after
        ), "revoked record served post-enforcement"
        assert not any(
            memory_id.startswith("semantic_ingestion:revocation:")
            for memory_id in seen_after
        ), "directive leaked post-enforcement"
        after_enforced_ids = {
            getattr(item, "memory_id", None)
            for item in gated.query_runtime_memory(query_obj)
        }
        assert not any(
            memory_id and memory_id.startswith("semantic_ingestion:revocation:")
            for memory_id in after_enforced_ids
        )
    finally:
        service.close()


def test_legacy_graph_node_tombstoned_revoked_and_never_served(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        plane = MemoryPlaneService(
            record_store=PublishedMemoryPlaneStore(
                service, SqliteMemoryPlaneStore(service.partition())
            )
        )
        fingerprint = canonical_graph_codec_manifest().manifest_fingerprint
        writers = SemanticWriterAdmissionStore(
            plane, bounded_preplanning_ownership_manifest()
        )
        writers.create_initial_evidence_only(
            admission_id="family",
            writer_implementation_fingerprint=fingerprint,
            graph_schema_fingerprint=fingerprint,
        )
        from memorii.core.memory_evolution.atomic_store import (
            SemanticIngestionAtomicStore,
        )

        store = SemanticIngestionAtomicStore(plane, writers)
        service.publish_memory_plane_batch(
            (*_seed_records(), _graph_seed_record()),
            operation_binding="family_seed",
        )
        governance = GovernanceOperator(operator)
        _forget(operator, governance, capability, barrier=True)
        governance.enforce_forget(store=store)

        # The legacy graph node was rewritten to a REVOKED-lifecycle
        # superseding version and never crashes the validity map.
        current = plane.get_record(GRAPH_NODE_MEMORY_ID)
        assert current is not None
        node = current.content["graph_node"]
        assert node["lifecycle_state"] == "revoked"

        view = view_from_control_root(
            service.installation_root / "control", records=plane.list_records()
        )
        evolution = MemoryEvolutionService(memory_plane=plane, revoked_view=view)
        snapshot = evolution._graph_queries.snapshot()
        assert all(node_id != "entity:parity" for node_id in
                   [node.node_id for node in snapshot.nodes])
    finally:
        service.close()


def test_crash_between_apply_and_enforcement_recovers_at_reopen(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    from memorii.core.storage_administration.service import StorageAdministrationService
    service = StorageAdministrationService(root)
    service.initialize()
    operator = StorageAdministrationOperator(service)
    capability = _capability(service)
    try:
        service.publish_memory_plane_batch(
            (*_seed_records(), _graph_seed_record()),
            operation_binding="family_seed",
        )
        governance = GovernanceOperator(operator)
        _forget(operator, governance, capability, barrier=True)
        assert service.pending_forget_enforcements()

        # Crash stand-in: the enforcement never ran; reopen fresh
        # administration + store over the same installation.
        service.close()
        reopened = StorageAdministrationService(root)
        try:
            assert reopened.pending_forget_enforcements()
            reopened_plane = MemoryPlaneService(
                record_store=PublishedMemoryPlaneStore(
                    reopened, SqliteMemoryPlaneStore(reopened.partition())
                )
            )
            fingerprint = canonical_graph_codec_manifest().manifest_fingerprint
            writers = SemanticWriterAdmissionStore(
                reopened_plane, bounded_preplanning_ownership_manifest()
            )
            if reopened_plane.get_record(
                __import__(
                    "memorii.core.memory_evolution.writer_admission",
                    fromlist=["writer_admission_memory_id"],
                ).writer_admission_memory_id()
            ) is None:
                writers.create_initial_evidence_only(
                    admission_id="family-reopen",
                    writer_implementation_fingerprint=fingerprint,
                    graph_schema_fingerprint=fingerprint,
                )
            from memorii.core.memory_evolution.atomic_store import (
                SemanticIngestionAtomicStore as _S,
            )

            store = _S(reopened_plane, writers)
            reopened_governance = GovernanceOperator(
                StorageAdministrationOperator(reopened)
            )
            reopened.set_forget_enforcement_emitter(
                lambda _record: reopened_governance.enforce_forget(store=store)
            )
            assert reopened.drain_pending_forget_enforcement() == 0
            replay = store.semantic_replay_state()
            assert any(
                item.record_kind == "revocation_directive"
                for item in replay.materialized_records
            )
        finally:
            reopened.close()
    finally:
        with contextlib.suppress(Exception):
            service.close()

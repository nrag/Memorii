"""Independent-process runner for bootstrap graph V3 race/replay proofs."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import timedelta
from pathlib import Path

from memorii.core.memory_evolution.atomic_store import PreplanningStoreError
from memorii.core.memory_evolution.writer_admission import SemanticWriterAdmissionError
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.bootstrap_graph_host import (
    BootstrapGraphHostBundleBuilder,
)
from memorii.core.semantic_ingestion.bootstrap_graph_repository import (
    AtomicStoreBootstrapGraphControlEpochRepositoryV3,
)
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.integrations.hermes_provider import HermesMemoryProvider
from tests.fixtures.semantic_ingestion import bootstrap_graph_v3_fixture
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphAuthorityProviderV3,
)
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
    GRAPH_SCENARIO_BEHAVIOR,
    RemovedBootstrapGraphHostBundleBuilder,
    graph_fact_proposal,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)


def _rewrite_jsonl_fixture(
    records_path: Path,
    *,
    mutate_record: object,
) -> int:
    """Rewrite a valid persisted JSONL fixture without bypassing store policy."""
    lines = records_path.read_text(encoding="utf-8").splitlines()
    changed = 0
    rewritten: list[str] = []
    for line in lines:
        batch = json.loads(line)
        records = []
        for record in batch["records"]:
            replacement = mutate_record(record)
            if replacement is None:
                changed += 1
                continue
            changed += int(replacement != record)
            records.append(replacement)
        batch["records"] = records
        checksum_payload = json.dumps(
            {
                "revision": batch["revision"],
                "data_revision": batch["data_revision"],
                "records": records,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        batch["checksum"] = hashlib.sha256(
            checksum_payload.encode("utf-8")
        ).hexdigest()
        rewritten.append(json.dumps(batch, sort_keys=True, separators=(",", ":")))
    records_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    return changed


def _member_payload(member: dict) -> dict:
    """Decode a graph member's canonical payload through its envelope."""
    from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value

    raw = member["canonical_payload"]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    payload = decode_typed_value(raw.encode("utf-8"))
    while isinstance(payload, dict) and set(payload) == {"codec_key", "payload", "schema"}:
        inner = payload["payload"]
        payload = (
            decode_typed_value(inner.encode("utf-8"))
            if isinstance(inner, str)
            else inner
        )
    if isinstance(payload, str):
        payload = decode_typed_value(payload.encode("utf-8"))
    return payload


def _persisted_successor_evidence(service: object) -> dict[str, object]:
    """Expose persisted successor arms, lineage, and pre-execution identities."""

    members = service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_member"
    )
    attempts = []
    lineages = []
    pre_execution = []
    lineage_entries = []
    group_evidence = []
    for record in members:
        member = record.content["member"]
        canonical_payload = member["canonical_payload"]
        # The member content stores the typed-value JSON document (a str);
        # raw-bytes members arrive from in-memory plane records.
        if isinstance(canonical_payload, bytes):
            canonical_payload = canonical_payload.decode("utf-8")
        payload = _member_payload(member)
        kind = member["kind"]
        # Member payloads of one kind can carry the reuse-partition authority
        # shape; select by the payload's own fields, not the member kind.
        if kind == "bootstrap_graph_dependent_attempt" and "attempt_index" in payload:
            attempts.append({
                "attempt_index": payload["attempt_index"],
                "attempt_id": payload["attempt_id"],
                "trigger": payload["trigger"],
                "authority": payload["attempt_authority"],
            })
        elif kind == "bootstrap_source_plan_lineage" and "latest_entry_by_group" in payload:
            lineages.append({
                "latest_entry_by_group": payload["latest_entry_by_group"],
                "entries": payload["entries"],
            })
        elif kind == "bootstrap_source_plan_lineage_entry" and "entry_digest" in payload:
            lineage_entries.append(payload)
        elif kind == "bootstrap_graph_pre_execution_group_evidence" and "evidence_digest" in payload:
            group_evidence.append(payload)
        elif (
            kind == "bootstrap_graph_pre_execution_identity_closure"
            and "closure_digest" in payload
        ):
            pre_execution.append({
                "closure_digest": payload["closure_digest"],
                "identity_by_group": payload["identity_by_group"],
                "identities": payload["identities"],
            })
    if not pre_execution and group_evidence:
        # Group evidence is keyed by plan-member digest; the identity view is
        # by transaction group, joined through the lineage entries.
        member_to_group = {
            item["group_plan_member_digest"]: item["transaction_group_id"]
            for item in lineage_entries
        }
        identity_by_group = {}
        for item in group_evidence:
            group_id = member_to_group.get(item["group_plan_member_digest"])
            if group_id is not None:
                identity_by_group[group_id] = item
        pre_execution.append({
            "closure_digest": None,
            "identity_by_group": identity_by_group,
            "identities": group_evidence,
        })
    if not lineages and lineage_entries:
        # The plane retains one lineage-entry member per group append; derive
        # the aggregate view (latest entry per group, ordinal order) from
        # them when no aggregate member exists.
        by_group: dict[str, object] = {}
        for entry in sorted(lineage_entries, key=lambda item: item["lineage_ordinal"]):
            group_id = entry["transaction_group_id"]
            if group_id not in by_group or entry["lineage_ordinal"] >= by_group[group_id]["lineage_ordinal"]:
                by_group[group_id] = entry
        lineages.append({
            "latest_entry_by_group": by_group,
            "entries": lineage_entries,
        })
    return {
        "attempts": attempts,
        "lineages": lineages,
        "pre_execution": pre_execution,
    }


def run(*, storage_root: Path, root: str, scenario: str, phase: str) -> dict[str, object]:
    behavior = GRAPH_SCENARIO_BEHAVIOR[scenario]
    proposal = graph_fact_proposal(
        3
        if behavior in {
            "partial_commit", "reused_committed", "reused_final",
            "reused_unfinished", "terminal_locator",
        }
        else 1
    )
    normalization, lane_calls = _v3_normalization_host_builder(proposal=proposal)
    successful_calls: list[str] = []
    cas_attempts: list[str] = []
    unavailable_calls: list[str] = []
    conflict_calls: list[str] = []
    partial_conflict_calls: list[str] = []
    exhausted_conflict_calls: list[str] = []
    acquire_errors: list[str] = []
    current_scope = [""]
    clock = [TEST_NOW]
    service_holder: list[object] = []
    lost_ack_injected = False
    scan_calls = 0
    if behavior == "reused_committed":
        original_successful_executor = (
            bootstrap_graph_v3_fixture.DeterministicBootstrapGraphSuccessfulExecutorV3
        )

        def committed_successful_executor(*, host_authority, calls, **kwargs):
            return original_successful_executor(
                host_authority=host_authority,
                calls=calls,
                disposition="committed",
                **kwargs,
            )

        # The fixture's provider resolves this constructor at acquisition time.
        # Keep the committed arm process-local so all public roots still use the
        # canonical production coordinator and persistence path.
        bootstrap_graph_v3_fixture.DeterministicBootstrapGraphSuccessfulExecutorV3 = (
            committed_successful_executor
        )

    def before_cas(_group_id: str) -> None:
        if phase != "first":
            raise AssertionError("replay unexpectedly reached graph CAS")
        if behavior == "scope_revoked":
            current_scope[0] = "f" * 64
            # The store-backed group commit derives its outcome from the
            # sealed reductions and never consults the executor, so the
            # revocation must fail the CAS itself: one attempt, zero
            # effects, fail-closed at the graph boundary.
            raise PreplanningStoreError(
                "injected scope revocation before group CAS"
            )
        service_holder[0]._memory_plane.upsert_record(
            CanonicalMemoryRecord(
                memory_id="unrelated:independent-jsonl",
                domain=MemoryDomain.EXECUTION,
                text="unrelated graph partition write",
                content={"partition": "outside-sealed-read-set"},
                status=CommitStatus.COMMITTED,
                source_kind="bootstrap_graph_unrelated_foreign_write",
                timestamp=TEST_NOW,
            )
        )

    def before_epoch_created(atomic_store: object) -> None:
        if behavior == "writer_changed":
            original = atomic_store._writers.commit_binding
            atomic_store._writers.commit_binding = lambda record: original(record).model_copy(
                update={"admission_digest": "f" * 64}
            )
        elif behavior == "writer_unavailable":
            def reject(_binding: object) -> None:
                raise SemanticWriterAdmissionError("writer authority is unavailable")
            atomic_store._writers.require_current = reject

    def after_epoch_created(atomic_store: object, request: object, epoch: object) -> object:
        if behavior not in {
            "lease_renewed", "lease_reclaimed", "writer_changed", "writer_unavailable"
        }:
            return epoch
        fence = request.graph_authority.operation_fence_binding
        control = atomic_store.get_operation(fence)
        if behavior in {"writer_changed", "writer_unavailable"}:
            return epoch
        if behavior == "lease_reclaimed":
            clock[0] = control.lease.expires_at + timedelta(seconds=1)
            atomic_store.acquire_lease(
                operation_fence=fence,
                writer_binding=control.writer_binding,
                execution_token="graph-reclaimed-execution",
                owner_id="graph-reclaimed-owner",
                duration=timedelta(minutes=10),
            )
        else:
            atomic_store.renew_lease(
                operation_fence=fence,
                writer_binding=control.writer_binding,
                lease=control.lease,
                duration=timedelta(minutes=10),
            )
        return AtomicStoreBootstrapGraphControlEpochRepositoryV3(
            atomic_store=atomic_store
        ).refresh_current(request=request, current_epoch=epoch).epoch

    class UnavailableAuthorityProvider:
        def acquire(self, **_kwargs: object) -> None:
            return None

    provider = DeterministicBootstrapGraphAuthorityProviderV3(
        successful_calls=successful_calls,
        acquire_errors=acquire_errors,
        cas_attempts=cas_attempts,
        # The store derives the group result disposition from the compiled
        # reductions (native terminal status), not the executor's outcome:
        # committed retained arms need accepted materialization.
        accepted_materialization=(behavior == "reused_committed"),
        unavailable_calls=unavailable_calls if behavior == "durable_retry" else None,
        conflict_calls=conflict_calls if behavior == "resolved_conflict" else None,
        partial_conflict_calls=(
            partial_conflict_calls
            if behavior in {
                "partial_commit", "reused_committed", "reused_final",
                "reused_unfinished", "terminal_locator",
            }
            else None
        ),
        exhausted_conflict_calls=(
            exhausted_conflict_calls if behavior == "exhausted_conflict" else None
        ),
        before_compare_and_swap=(
            before_cas
            if behavior in {"scope_revoked", "unrelated_conflict"}
            else None
        ),
        current_scope_digest=(lambda: current_scope[0]) if behavior == "scope_revoked" else None,
        after_epoch_created=after_epoch_created,
        before_epoch_created=before_epoch_created,
    )
    memory_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage_root / "memory-plane")
    )
    common: dict[str, object] = {
        "now_provider": lambda: clock[0],
        "host_bootstrap_capability": _built_in_local_capability(scenario_test=True),
        "host_bootstrap_material_verifier": DeterministicTestHostBootstrapMaterialVerifier(),
        "source_normalization_host_bundle_builder": normalization,
    }
    if behavior == "coordinator_removed":
        common["bootstrap_graph_host_bundle_builder"] = (
            RemovedBootstrapGraphHostBundleBuilder()
        )
    else:
        common["bootstrap_graph_host_bundle_builder"] = BootstrapGraphHostBundleBuilder(
            authority_provider=(
                UnavailableAuthorityProvider()
                if behavior == "authority_omitted"
                else provider
            ),
            promotion_enabled=not (behavior == "rollback" and phase == "reopen"),
        )
    if root == "hermes":
        service = HermesMemoryProvider(
            service=ProviderMemoryService._from_scenario_test_host(
                memory_plane=memory_plane, **common
            )
        )._service
    else:
        service = ProviderMemoryService._from_scenario_test_host(
            memory_plane=memory_plane, **common
        )
    service_holder.append(service)
    if behavior == "lost_ack" and phase == "first":
        atomic = service._semantic_atomic_store
        persist_terminal = atomic.persist_bootstrap_graph_terminal_v3

        def fail_after_terminal_cas(*, request):
            nonlocal lost_ack_injected
            reload = persist_terminal(request=request)
            if not lost_ack_injected:
                lost_ack_injected = True
                raise PreplanningStoreError("injected terminal acknowledgement failure")
            return reload

        atomic.persist_bootstrap_graph_terminal_v3 = fail_after_terminal_cas
    if behavior == "terminal_locator" and phase == "reopen":
        original_list_records = service._memory_plane.list_records

        def counted_list_records(*args, **kwargs):
            nonlocal scan_calls
            scan_calls += int(
                kwargs.get("source_kind")
                == "semantic_ingestion_bootstrap_graph_v3_terminal_locator"
            )
            return original_list_records(*args, **kwargs)

        service._memory_plane.list_records = counted_list_records
    ingress = _host_ingress()
    resolved = service._resolve_ingress(ingress)
    if resolved is None:
        raise AssertionError("independent graph runner ingress was rejected")
    current_scope[0] = resolved.current_authorized_scopes.required_scope_set_digest
    operation_id = f"independent-{scenario}"
    prior_terminal_result = None
    if behavior == "rollback" and phase == "reopen":
        prior_terminal_result = service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id=operation_id,
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=ingress,
        )
        operation_id = f"{operation_id}-after-rollback"
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id=operation_id,
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=ingress,
    )
    fixture_path = storage_root / "memory-plane" / "memory_records.jsonl"
    terminal_locator_removed = 0
    mixed_version_fixture_mutations = 0
    if phase == "first" and behavior == "terminal_locator":
        removed_locator = {"count": 0}

        def drop_one_locator(record: dict[str, object]):
            if (
                record["source_kind"]
                != "semantic_ingestion_bootstrap_graph_v3_terminal_locator"
                or removed_locator["count"] >= 1
            ):
                return record
            removed_locator["count"] += 1
            return None

        terminal_locator_removed = _rewrite_jsonl_fixture(
            fixture_path, mutate_record=drop_one_locator
        )
    if phase == "first" and behavior == "mixed_version":
        def legacy_v2_fixture(record: dict[str, object]) -> dict[str, object]:
            if record["source_kind"] == "semantic_ingestion_bootstrap_graph_v3_member":
                record = dict(record)
                content = dict(record["content"])
                content["member"] = {"schema_version": 2, "kind": "legacy_graph_member"}
                record["content"] = content
            return record

        mixed_version_fixture_mutations = _rewrite_jsonl_fixture(
            fixture_path, mutate_record=legacy_v2_fixture
        )
    successor_evidence = (
        _persisted_successor_evidence(service)
        if behavior in {"reused_committed", "reused_final", "reused_unfinished"}
        else {}
    )
    return {
        "semantic_ingestion": result.blocked_reasons["semantic_ingestion"],
        "cas_attempts": len(cas_attempts),
        "graph_effects": len(successful_calls),
        "unavailable_calls": len(unavailable_calls),
        "conflict_calls": len(conflict_calls),
        "partial_conflict_calls": len(partial_conflict_calls),
        "exhausted_conflict_calls": len(exhausted_conflict_calls),
        "acquire_errors": acquire_errors,
        "lane_calls": lane_calls,
        "lost_ack_injected": lost_ack_injected,
        "scan_calls": scan_calls,
        "terminal_locator_removed": terminal_locator_removed,
        "mixed_version_fixture_mutations": mixed_version_fixture_mutations,
        "prior_terminal_semantic_ingestion": (
            None
            if prior_terminal_result is None
            else prior_terminal_result.blocked_reasons["semantic_ingestion"]
        ),
        "successor_evidence": successor_evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("storage_root", type=Path)
    parser.add_argument("root", choices=("direct", "factory", "filesystem", "hermes"))
    parser.add_argument(
        "scenario",
        choices=tuple(GRAPH_SCENARIO_BEHAVIOR),
    )
    parser.add_argument("phase", choices=("first", "reopen"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = run(
        storage_root=args.storage_root,
        root=args.root,
        scenario=args.scenario,
        phase=args.phase,
    )
    args.output.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()

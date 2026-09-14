"""Cohort closure failures using typed native deltas and a detached authority double."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalSourceTerminalOutcomeCore,
    CanonicalSourceTerminalOutcomeRecord,
    IngestionObservationDelta,
    IngestionObservationRecordMutation,
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.graph_observation_cohort import resolve_observation_membership
from memorii.core.memory_evolution.graph_observation_contracts import GraphObservationCohortSelector
from memorii.core.memory_evolution.graph_observation_paging import ObservationCohortUnavailableError
from memorii.core.memory_evolution.graph_observation_public_contracts import AuthenticatedGraphObservationContext
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain
from tests.unit.core.memory_evolution.test_observation_record_contracts import (
    _digest,
    _source_material,
    _source_terminal,
    _terminal_group_delta,
)


def _fixture():
    material = _source_material()
    group = _terminal_group_delta(material)
    template = _source_terminal(material)
    core = CanonicalSourceTerminalOutcomeCore.create(**{
        **template.core.model_dump(exclude={"core_digest"}),
        "group_result_digests": (_digest("group-result"),),
    })
    outcome = CanonicalSourceTerminalOutcomeRecord.create(
        core=core, preparation_fingerprint=material.preparation_fingerprint,
    )
    final = SourceFinalizationObservationDelta.create(
        kind="source_finalization", observation_delta_id="source-final",
        observation_revision_before="observation:1", observation_revision_after="observation:2",
        **{name: getattr(outcome, name) for name in (
            "source_id", "source_digest", "delivery_principal_binding_digest", "delivery_key_digest",
            "segment_governance_carriers", "message_admission_carriers", "governance_carrier_artifact",
            "required_outcome_scopes", "operation_fence_id", "operation_ids",
        )},
        source_outcome=outcome, observation_schema_fingerprint=_digest("schema"),
    )
    source = CanonicalMemoryRecord(
        memory_id=material.source_id, domain=MemoryDomain.TRANSCRIPT, text="Ada works.",
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_source",
        timestamp=datetime(2026, 9, 8, tzinfo=UTC),
    )
    # Cryptographic ledger replay is tested at the activated provider boundary;
    # this double isolates membership expansion from that expensive verifier.
    authority = SimpleNamespace(
        records=(source,), graph_deltas=(), observation=SimpleNamespace(entries=(
            SimpleNamespace(delta=group, result_digest=_digest("group-result"), sequence=1),
            SimpleNamespace(delta=final, result_digest=_digest("source-result"), sequence=2),
        )),
    )
    context = AuthenticatedGraphObservationContext(
        principal_subject_id="reader", tenant_partition_id=final.required_outcome_scopes.tenant_partition_id,
        authorized_scope_set_digest=_digest("scope"), authentication_session_id="session",
        context_digest=_digest("context"),
    )
    selector = GraphObservationCohortSelector(
        seed_source_ids=(source.memory_id,), seed_operation_ids=(), include_referenced_boundary_entities=True,
    )
    return authority, context, final.required_outcome_scopes.scopes[0], selector


def _sibling(group, shared_coordinate):
    changes = {
        "operation_fence_id": group.operation_fence_id if shared_coordinate == "fence" else "other-fence",
        "transaction_group_id": group.transaction_group_id if shared_coordinate == "transaction_group" else "other-group",
    }
    mutations = []
    for mutation in group.record_mutations:
        record = mutation.record
        identity_field = "introduction_id" if hasattr(record, "introduction_id") else "outcome_id"
        replacement = type(record).create(**{
            **record.model_dump(exclude={"record_digest"}), **changes,
            "operation_id": "operation:sibling", identity_field: "sibling:" + mutation.record_id,
        })
        mutations.append(IngestionObservationRecordMutation.create(
            mutation_kind="create", ingestion_record_kind=replacement.ingestion_record_kind,
            record_id=getattr(replacement, identity_field), record_version=1,
            record=replacement, record_digest=replacement.record_digest,
        ))
    return IngestionObservationDelta.create(**{
        **group.model_dump(exclude={"delta_digest"}), **changes,
        "observation_delta_id": "sibling-delta", "operation_ids": ("operation:sibling",),
        "record_mutations": tuple(mutations),
    })


def test_terminal_noncommitting_source_has_complete_cohort_without_graph_effects():
    result = resolve_observation_membership(*_fixture())
    assert result.operation_ids == ("operation:observation-record",)
    assert result.graph_deltas == ()


@pytest.mark.parametrize("coordinate", ["fence", "transaction_group"])
def test_sibling_group_omitted_by_source_finalization_is_not_silently_excluded(coordinate):
    authority, context, scope, selector = _fixture()
    sibling = _sibling(authority.observation.entries[0].delta, coordinate)
    authority.observation.entries += (SimpleNamespace(
        delta=sibling, result_digest=_digest("sibling-result"), sequence=3,
    ),)
    with pytest.raises(ObservationCohortUnavailableError, match="omits a selected operation group"):
        resolve_observation_membership(authority, context, scope, selector)

"""Closed classification for semantic-ingestion authority and control records."""

from __future__ import annotations

from typing import Literal

from memorii.core.memory_plane.models import CanonicalMemoryRecord

SemanticControlClass = Literal[
    "admission",
    "operation",
    "migration",
    "projection",
    "projection_publication",
    "clarification",
    "replay_authority",
    "recovery",
    "integrity",
    "conflict_authority",
    "unknown",
]

SEMANTIC_PROJECTION_SOURCE_KINDS = frozenset(
    f"semantic_projection_{projection_kind}_{authority_kind}"
    for projection_kind in ("temporal", "trust")
    for authority_kind in (
        "certificate",
        "generation",
        "history_entry",
        "active_pointer",
        "projection",
        "decay_command",
        "migration_plan",
        "migration_catch_up",
        "migration_command",
        "migration_result",
        "migration_cutover",
    )
)

_SOURCE_CLASSES: dict[str, SemanticControlClass] = {
    "semantic_ingestion_writer_admission": "admission",
    "semantic_ingestion_source": "admission",
    "semantic_ingestion_metadata_poor_snapshot": "admission",
    "semantic_ingestion_admission_index": "admission",
    "semantic_ingestion_profile_selection": "admission",
    "semantic_ingestion_profile_verification": "admission",
    "semantic_ingestion_profile_outcome": "admission",
    "semantic_ingestion_legacy_delivery_record": "admission",
    "semantic_ingestion_preplanning_control": "operation",
    "semantic_ingestion_preplanning_artifact": "operation",
    "semantic_ingestion_generation_member": "operation",
    "semantic_ingestion_generation_manifest": "operation",
    "semantic_ingestion_authorization_authority": "operation",
    "semantic_ingestion_projection_publication": "projection_publication",
    "semantic_ingestion_migrated_target": "migration",
    "semantic_ingestion_conflict_clarification_transaction": "clarification",
    "semantic_ingestion_conflict_clarification_context": "clarification",
    "semantic_ingestion_conflict_clarification_receipt": "clarification",
    "semantic_ingestion_conflict_clarification_recovery_authority": "clarification",
    "semantic_ingestion_event_batch": "replay_authority",
    "semantic_ingestion_replay_state": "replay_authority",
    "semantic_ingestion_replay_authority": "replay_authority",
    "semantic_ingestion_checkpoint_lifecycle": "replay_authority",
    "semantic_ingestion_event_schema_registry_history": "replay_authority",
    "semantic_ingestion_reference_integrity": "replay_authority",
    "semantic_ingestion_graph_identity_reservation": "replay_authority",
    "semantic_ingestion_accepted_identity_operation": "operation",
    "semantic_ingestion_clean_recovery_request": "recovery",
    "semantic_ingestion_clean_generation": "recovery",
    "semantic_ingestion_clean_generation_status": "recovery",
    "semantic_ingestion_retained_corrupt_event_batch_slot": "recovery",
    "semantic_ingestion_replay_integrity_control": "integrity",
    "semantic_ingestion_replay_integrity_attention": "integrity",
    "semantic_ingestion_conflict_authority": "conflict_authority",
}
_SOURCE_CLASSES.update({source_kind: "projection" for source_kind in SEMANTIC_PROJECTION_SOURCE_KINDS})
_SOURCE_CLASSES.update(
    {
        f"semantic_ingestion_migration_{kind}": "migration"
        for kind in ("plan", "checkpoint", "certificate", "target_projection")
    }
)

# Before writer admission exists, source-admission carriers are the only
# semantic records permitted through the public admission path. Once the
# governed writer is installed, the same kinds are governed normally.
SEMANTIC_PUBLIC_NON_AUTHORITY_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "semantic_ingestion_source",
        "semantic_ingestion_metadata_poor_snapshot",
        "semantic_ingestion_admission_index",
        "semantic_ingestion_profile_selection",
        "semantic_ingestion_profile_verification",
        "semantic_ingestion_profile_outcome",
        "semantic_ingestion_legacy_delivery_record",
    }
)

_ID_PREFIX_CLASSES: tuple[tuple[str, SemanticControlClass], ...] = (
    ("semantic_projection:", "projection"),
    ("semantic_ingestion:projection-publication:", "projection_publication"),
    ("semantic_ingestion:clarification:", "clarification"),
    ("semantic_ingestion:conflict-authority:", "conflict_authority"),
    ("semantic_ingestion:event-authority:integrity-", "integrity"),
    ("semantic_ingestion:event-authority:clean-", "recovery"),
    ("semantic_ingestion:event-authority:", "replay_authority"),
    ("semantic_ingestion:reference-integrity:", "replay_authority"),
    ("semantic_ingestion:graph-reservation:", "replay_authority"),
    ("semantic_ingestion:migration:", "migration"),
    ("semantic_ingestion:migrated:", "migration"),
    ("semantic_ingestion:writer_admission:", "admission"),
    ("semantic_ingestion:source:", "admission"),
    ("semantic_ingestion:admission:", "admission"),
    ("semantic_ingestion:operation:", "operation"),
    ("semantic_ingestion:artifact:", "operation"),
    ("semantic_ingestion:generation:", "operation"),
    ("semantic_ingestion:authorization:", "operation"),
    ("semantic_ingestion:accepted-identity:", "operation"),
)

SEMANTIC_CONTROL_SOURCE_KINDS: frozenset[str] = frozenset(_SOURCE_CLASSES)
SEMANTIC_CONTROL_ID_PREFIXES: tuple[str, ...] = tuple(prefix for prefix, _ in _ID_PREFIX_CLASSES)


def semantic_control_class(record: CanonicalMemoryRecord) -> SemanticControlClass | None:
    """Classify every semantic authority namespace, including unknown siblings."""

    source_kind = record.source_kind
    source_class = _SOURCE_CLASSES.get(source_kind)
    id_class: SemanticControlClass | None = None
    for prefix, control_class in _ID_PREFIX_CLASSES:
        if record.memory_id.startswith(prefix):
            id_class = control_class
            break
    if source_class is not None and id_class is not None and source_class != id_class:
        return "unknown"
    if source_class is not None:
        return source_class
    if id_class is not None:
        return id_class
    if source_kind.startswith(("semantic_ingestion_", "semantic_projection_")) or record.memory_id.startswith(
        ("semantic_ingestion:", "semantic_projection:")
    ):
        return "unknown"
    return None


def is_semantic_control_record(record: CanonicalMemoryRecord) -> bool:
    return semantic_control_class(record) is not None


__all__ = [
    "SEMANTIC_CONTROL_ID_PREFIXES",
    "SEMANTIC_CONTROL_SOURCE_KINDS",
    "SEMANTIC_PROJECTION_SOURCE_KINDS",
    "SEMANTIC_PUBLIC_NON_AUTHORITY_SOURCE_KINDS",
    "SemanticControlClass",
    "is_semantic_control_record",
    "semantic_control_class",
]

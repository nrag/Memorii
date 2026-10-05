"""The single derived revoked-identity view every serving gate consults.

One owner derives the set of revoked identities from the two authorities:
the typed suppression journal (available immediately at apply, before any
publication) and the semantic revocation directives (once the enforcement
publication lands, via their content-free index records). Serving roots
receive one typed, injected view; none parses control files. The empty
view is valid and means "nothing revoked"; internal integrity readers are
never filtered — only host/operator-serving endpoints consult the view.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.storage_administration.suppression_journal import (
    read_suppression_records,
)

_DIRECTIVE_RECORD_PREFIX = "semantic_ingestion:revocation:"
_DIRECTIVE_RECORD_SOURCE_KIND = "semantic_ingestion_revocation_directive"


class RevokedIdentityServingGate(Protocol):
    """The serving-gate surface composition roots inject.

    Serving components depend on this protocol, never on the concrete
    view, so test harnesses can compose a minimal gate and the factory
    composes the real derived view.
    """

    def is_revoked_entity(self, logical_entity_id: str) -> bool: ...

    def is_revoked_claim(self, claim_id: str) -> bool: ...

    def is_revoked_source(self, source_id: str) -> bool: ...

    def is_revoked_record(self, memory_id: str) -> bool: ...

    def is_revoked_task(self, task_id: str) -> bool: ...

    def is_revoked_justification(self, justification_id: str) -> bool: ...

    def keeps_record(self, record: object) -> bool: ...

    def filter_records(self, records: object) -> tuple: ...


class RevokedIdentities(BaseModel):
    """Content-free identity sets; frozen and closed."""

    entities: frozenset[str] = Field(default=frozenset())
    claims: frozenset[str] = Field(default=frozenset())
    sources: frozenset[str] = Field(default=frozenset())
    records: frozenset[str] = Field(default=frozenset())
    tasks: frozenset[str] = Field(default=frozenset())
    justifications: frozenset[str] = Field(default=frozenset())

    model_config = ConfigDict(extra="forbid", frozen=True)

    def __bool__(self) -> bool:
        return bool(
            self.entities
            or self.claims
            or self.sources
            or self.records
            or self.tasks
            or self.justifications
        )

    def union(self, other: RevokedIdentities) -> RevokedIdentities:
        return RevokedIdentities(
            entities=self.entities | other.entities,
            claims=self.claims | other.claims,
            sources=self.sources | other.sources,
            records=self.records | other.records,
            tasks=self.tasks | other.tasks,
            justifications=self.justifications | other.justifications,
        )


class RevokedIdentityView:
    """Read-only serving gate; derived, never authoritatively stored."""

    def __init__(self, identities: RevokedIdentities | None = None) -> None:
        self._identities = identities or RevokedIdentities()

    @classmethod
    def empty(cls) -> RevokedIdentityView:
        return cls(RevokedIdentities())

    @property
    def identities(self) -> RevokedIdentities:
        return self._identities

    def is_revoked_entity(self, logical_entity_id: str) -> bool:
        return logical_entity_id in self._identities.entities

    def is_revoked_claim(self, claim_id: str) -> bool:
        return claim_id in self._identities.claims

    def is_revoked_source(self, source_id: str) -> bool:
        return source_id in self._identities.sources

    def is_revoked_record(self, memory_id: str) -> bool:
        return memory_id in self._identities.records

    def is_revoked_task(self, task_id: str) -> bool:
        return task_id in self._identities.tasks

    def is_revoked_justification(self, justification_id: str) -> bool:
        return justification_id in self._identities.justifications

    def keeps_record(self, record) -> bool:
        """Serving filter for one memory-plane record; True means serve."""

        # Revocation directives themselves never serve on host paths
        # (design 6.2.1): their coordinate content is exactly what the
        # absence oracle forbids disclosing.
        if record.memory_id.startswith("semantic_ingestion:revocation:") or (
            getattr(record, "source_kind", None)
            == "semantic_ingestion_revocation_directive"
        ):
            return False
        memory_evolution_kind = (
            record.content.get("memory_evolution_kind")
            if isinstance(getattr(record, "content", None), dict)
            else None
        )
        if self.is_revoked_record(record.memory_id):
            return False
        if memory_evolution_kind == "claim_state":
            claim = record.content.get("claim_state") or {}
            claim_id = claim.get("claim_id")
            if isinstance(claim_id, str) and self.is_revoked_claim(claim_id):
                return False
        elif memory_evolution_kind == "entity_link":
            link = record.content.get("entity_link") or {}
            entity_id = link.get("canonical_entity_id")
            if isinstance(entity_id, str) and self.is_revoked_entity(entity_id):
                return False
        return True

    def filter_records(self, records) -> tuple:
        """Serving filter over a record sequence (tuple/list -> tuple)."""

        return tuple(record for record in records if self.keeps_record(record))

    def revoked_source_ids(self) -> frozenset[str]:
        return self._identities.sources


def identities_from_journal(control_root: Path) -> RevokedIdentities:
    """Derive the revoked-identity sets from the typed journal only."""

    records = read_suppression_records(control_root)
    entities: set[str] = set()
    claims: set[str] = set()
    sources: set[str] = set()
    plain_records: set[str] = set()
    tasks: set[str] = set()
    justifications: set[str] = set()
    for record in records:
        for coordinate in record.suppressed:
            target = {
                "entity": entities,
                "claim": claims,
                "source": sources,
                "task": tasks,
                "justification": justifications,
            }.get(coordinate.coordinate_kind)
            if coordinate.coordinate_kind == "record":
                plain_records.add(coordinate.coordinate_id)
            elif target is not None:
                target.add(coordinate.coordinate_id)
    return RevokedIdentities(
        entities=frozenset(entities),
        claims=frozenset(claims),
        sources=frozenset(sources),
        records=frozenset(plain_records),
        tasks=frozenset(tasks),
        justifications=frozenset(justifications),
    )


def identities_from_directive_records(records) -> RevokedIdentities:
    """Derive the revoked-identity sets from directive index records.

    Each enforcement publication writes one content-free index record per
    suppression (memory_id ``semantic_ingestion:revocation:<id>``) whose
    content repeats the directive's revoked target coordinates.
    """

    entities: set[str] = set()
    claims: set[str] = set()
    sources: set[str] = set()
    plain_records: set[str] = set()
    tasks: set[str] = set()
    justifications: set[str] = set()
    for record in records:
        if not str(record.memory_id).startswith(_DIRECTIVE_RECORD_PREFIX):
            continue
        if str(getattr(record, "source_kind", "")) != _DIRECTIVE_RECORD_SOURCE_KIND:
            continue
        for coordinate in record.content.get("revoked_targets") or []:
            kind = coordinate.get("coordinate_kind")
            identifier = coordinate.get("coordinate_id")
            if not isinstance(identifier, str) or not identifier:
                continue
            if kind == "entity":
                entities.add(identifier)
            elif kind == "claim":
                claims.add(identifier)
            elif kind == "source":
                sources.add(identifier)
            elif kind == "record":
                plain_records.add(identifier)
            elif kind == "task":
                tasks.add(identifier)
            elif kind == "justification":
                justifications.add(identifier)
    return RevokedIdentities(
        entities=frozenset(entities),
        claims=frozenset(claims),
        sources=frozenset(sources),
        records=frozenset(plain_records),
        tasks=frozenset(tasks),
        justifications=frozenset(justifications),
    )


def view_from_control_root(
    control_root: Path, records: tuple = ()
) -> RevokedIdentityView:
    """Compose the serving view: journal plus retention-archive identities.

    Retention tiering moves aged journal entries to suppressions-archive
    (bytes retained); age never removes revocation state, so the archive
    contributes identities exactly like the live journal. Directive index
    records supplement when a caller supplies them.
    """

    identities = identities_from_journal(control_root)
    archive = Path(control_root) / "suppressions-archive"
    if archive.is_dir():
        identities = identities.union(_archive_identities(archive))
    if records:
        identities = identities.union(identities_from_directive_records(records))
    return RevokedIdentityView(identities)


def _archive_identities(archive: Path) -> RevokedIdentities:
    import json as _json

    from memorii.core.storage_administration.suppression_journal import (
        SuppressionRecord,
    )

    entities: set[str] = set()
    claims: set[str] = set()
    sources: set[str] = set()
    records: set[str] = set()
    tasks: set[str] = set()
    justifications: set[str] = set()
    for path in sorted(archive.glob("forget-*.json")):
        try:
            entry = SuppressionRecord.model_validate(_json.loads(path.read_text()))
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"retention archive entry is unreadable: {path.name}"
            ) from exc
        for coordinate in entry.suppressed:
            if coordinate.coordinate_kind == "entity":
                entities.add(coordinate.coordinate_id)
            elif coordinate.coordinate_kind == "claim":
                claims.add(coordinate.coordinate_id)
            elif coordinate.coordinate_kind == "source":
                sources.add(coordinate.coordinate_id)
            elif coordinate.coordinate_kind == "record":
                records.add(coordinate.coordinate_id)
            elif coordinate.coordinate_kind == "task":
                tasks.add(coordinate.coordinate_id)
            elif coordinate.coordinate_kind == "justification":
                justifications.add(coordinate.coordinate_id)
    return RevokedIdentities(
        entities=frozenset(entities),
        claims=frozenset(claims),
        sources=frozenset(sources),
        records=frozenset(records),
        tasks=frozenset(tasks),
        justifications=frozenset(justifications),
    )


def empty_revoked_view() -> RevokedIdentityView:
    """The valid empty view: nothing is revoked.

    For compositions with no control state at all (ephemeral test planes),
    where an explicit empty gate is the honest value. Production roots
    over real installations must derive from the control root instead.
    """

    return RevokedIdentityView(RevokedIdentities())


def _journal_fingerprint(control_root: Path) -> tuple:
    """Cheap change signal over the suppression journal directory.

    One stat of the directory itself: create, rename, and replace (the
    journal's atomic write) all update the directory mtime on POSIX, so
    a single syscall detects every change the per-file walk did — the
    walk made every serving predicate O(journal entries).
    """

    directory = control_root / "suppressions"
    try:
        info = directory.stat()
    except (FileNotFoundError, NotADirectoryError, OSError):
        return ()
    return (info.st_mtime_ns, info.st_size, info.st_ino)


class RefreshingRevokedIdentityView:
    """Serving gate that re-derives from the suppression journal on change.

    Derived once at construction and re-derived whenever the journal
    directory changes — the design's journal-write refresh point. Apply
    writes a new journal entry (and restore re-apply does too), so a
    long-lived serving process observes new revocations without a
    restart. Journal identities cover every coordinate class (the
    journal is append-only and is the serving gate of record), so no
    record scan is needed. A missing journal yields the valid empty view.
    """

    def __init__(self, control_root: Path) -> None:
        self._control_root = Path(control_root)
        self._fingerprint: tuple = ()
        self._view = empty_revoked_view()
        self._refresh()

    def _refresh(self) -> None:
        fingerprint = _journal_fingerprint(self._control_root)
        if fingerprint != self._fingerprint:
            self._view = view_from_control_root(self._control_root)
            self._fingerprint = fingerprint

    def is_revoked_entity(self, logical_entity_id: str) -> bool:
        self._refresh()
        return self._view.is_revoked_entity(logical_entity_id)

    def is_revoked_claim(self, claim_id: str) -> bool:
        self._refresh()
        return self._view.is_revoked_claim(claim_id)

    def is_revoked_source(self, source_id: str) -> bool:
        self._refresh()
        return self._view.is_revoked_source(source_id)

    def is_revoked_record(self, memory_id: str) -> bool:
        self._refresh()
        return self._view.is_revoked_record(memory_id)

    def is_revoked_task(self, task_id: str) -> bool:
        self._refresh()
        return self._view.is_revoked_task(task_id)

    def is_revoked_justification(self, justification_id: str) -> bool:
        self._refresh()
        return self._view.is_revoked_justification(justification_id)

    def keeps_record(self, record: object) -> bool:
        self._refresh()
        return self._view.keeps_record(record)

    def filter_records(self, records: object) -> tuple:
        self._refresh()
        return self._view.filter_records(records)


__all__ = [
    "RefreshingRevokedIdentityView",
    "RevokedIdentities",
    "RevokedIdentityView",
    "empty_revoked_view",
    "identities_from_directive_records",
    "identities_from_journal",
    "view_from_control_root",
]

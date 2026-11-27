"""Protected, snapshot-linearized reads of structured semantic facts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memorii.core.memory_evolution.admission import source_admission_source_digest
from memorii.core.memory_evolution.claim_queries import ClaimStateQueryService
from memorii.core.memory_evolution.models import ClaimLifecycleState, ClaimState, RetrievalView
from memorii.core.memory_evolution.semantic_state import AcceptedClaimIdentity
from memorii.core.memory_evolution.state_repository import EvolutionStateRepository
from memorii.core.memory_evolution.writer_admission import CatalogBundleLocator
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.scoped_context.authority import ResolvedScopedReadGrant
from memorii.core.scoped_context.service import (
    LegacyBootstrapV3ProjectionReadVerifier,
    _authorized,
    _current_eligible,
    _inner_scope_agrees,
    _is_new_structured_claim_projection,
    _source_closure_ids,
    verify_structured_catalog_projection_for_read,
)
from memorii.core.semantic_ingestion.catalog_authority import (
    CatalogAuthorityCoordinate,
    StructuredClaimCatalogBinding,
    StructuredFactReadAuthority,
    StructuredGrantState,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import (
    CatalogCapturedTurnPin,
    PackageIndexedCatalogBundleLocator,
    SeedCatalogBundleLocator,
)
from memorii.core.semantic_ingestion.contracts import SourceAuthorityEvidence
from memorii.core.semantic_ingestion.default_catalog_corpus import load_default_catalog_acceptance_corpus
from memorii.core.storage_administration.revoked_identity_view import RevokedIdentityView
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility, TemporalValidityStatus


@dataclass(frozen=True)
class _LifecycleTransition:
    """One committed correction or retraction reconstructed from its group pair."""

    transition_id: str
    operation_id: str
    transition_kind: Literal["correction", "retraction"]
    compared_claim_ids: tuple[str, ...]
    next_claim_ids: tuple[str, ...]
    recorded_at: datetime


@dataclass(frozen=True)
class _ProjectedClaim:
    claim_id: str
    predicate_id: str
    subject_entity_id: str
    object_value: str
    lifecycle_state: str
    valid_from: datetime | None
    valid_to: datetime | None
    system_time: datetime
    provenance: str
    projection: CanonicalMemoryRecord


@dataclass(frozen=True)
class _ReadPolicy:
    """Minimal read behavior required after catalog binding verification."""

    read_derivation_policy: Literal["none", "symmetric_view"]


class StructuredFactReadRequest(BaseModel):
    predicate_id: str = Field(min_length=1)
    subject_entity_id: str = Field(min_length=1)
    view: Literal["current", "history"] = "current"
    system_as_of: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class StructuredFactReadItem(BaseModel):
    claim_id: str
    source_claim_id: str
    predicate_id: str
    subject_entity_id: str
    object_value: str
    lifecycle_state: str
    valid_from: datetime | None
    valid_to: datetime | None
    system_time: datetime
    provenance: str
    catalog_version_id: str
    catalog_version_digest: str
    derived_direction: Literal["forward", "reverse"] = "forward"

    model_config = ConfigDict(extra="forbid", frozen=True)


class StructuredFactReadResponse(BaseModel):
    status: Literal["ok", "denied", "unavailable"]
    items: tuple[StructuredFactReadItem, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


def read_structured_facts_from_snapshot(
    *,
    records: tuple[CanonicalMemoryRecord, ...],
    request: StructuredFactReadRequest,
    authority: StructuredFactReadAuthority,
    now: datetime,
) -> StructuredFactReadResponse:
    """Read committed claims after one canonical binding and grant join."""
    controls = _controls(records)
    if controls is None:
        return StructuredFactReadResponse(status="unavailable")
    bindings, grant_states, pins, projections = controls
    if not _current_grants(grant_states, authority):
        return StructuredFactReadResponse(status="denied")
    row = _catalog_row(request.predicate_id)
    if row is None:
        return StructuredFactReadResponse(status="unavailable")
    transitions = _lifecycle_transitions(records)
    if transitions is None:
        return StructuredFactReadResponse(status="unavailable")
    try:
        states = _query_states(records, request=request, now=now, transitions=transitions)
    except (TypeError, ValueError):
        return StructuredFactReadResponse(status="unavailable")
    if not states:
        projected = _query_projected_claims(
            records=records,
            projections=projections,
            request=request,
            transitions=transitions,
        )
        if projected is None:
            return StructuredFactReadResponse(status="unavailable")
        items = _projected_items(
            claims=projected,
            records=records,
            bindings=bindings,
            grant_states=grant_states,
            pins=pins,
            authority=authority,
            reverse=False,
        )
        if items is None:
            return StructuredFactReadResponse(status="unavailable")
        if row.read_derivation_policy == "symmetric_view":
            reverse = _query_projected_claims(
                records=records,
                projections=projections,
                request=request.model_copy(update={"subject_entity_id": "*"}),
                transitions=transitions,
            )
            if reverse is None:
                return StructuredFactReadResponse(status="unavailable")
            reverse = tuple(claim for claim in reverse if claim.object_value == request.subject_entity_id)
            reverse_items = _projected_items(
                claims=reverse,
                records=records,
                bindings=bindings,
                grant_states=grant_states,
                pins=pins,
                authority=authority,
                reverse=True,
                requested_reverse_endpoint=request.subject_entity_id,
            )
            if reverse_items is None:
                return StructuredFactReadResponse(status="unavailable")
            items += reverse_items
        return StructuredFactReadResponse(
            status="ok",
            items=tuple(sorted(items, key=lambda item: (item.system_time, item.claim_id, item.derived_direction))),
        )
    items = _items(
        states=states,
        records=records,
        bindings=bindings,
        grant_states=grant_states,
        pins=pins,
        projections=projections,
        authority=authority,
        request=request,
        reverse=False,
    )
    if items is None:
        return StructuredFactReadResponse(status="unavailable")
    if row.read_derivation_policy == "symmetric_view":
        try:
            reverse_states = [
                state
                for state in _query_states(
                    records,
                    request=request.model_copy(update={"subject_entity_id": None}),
                    now=now,
                    transitions=transitions,
                )
                if state.object_value == request.subject_entity_id
            ]
        except (TypeError, ValueError):
            return StructuredFactReadResponse(status="unavailable")
        reverse_items = _items(
            states=reverse_states,
            records=records,
            bindings=bindings,
            grant_states=grant_states,
            pins=pins,
            projections=projections,
            authority=authority,
            request=request,
            reverse=True,
        )
        if reverse_items is None:
            return StructuredFactReadResponse(status="unavailable")
        items += reverse_items
    return StructuredFactReadResponse(
        status="ok",
        items=tuple(sorted(items, key=lambda item: (item.system_time, item.claim_id, item.derived_direction))),
    )


def _catalog_row(predicate_id: str) -> _ReadPolicy | None:
    row = next(
        (row for row in load_default_catalog_acceptance_corpus().rows if row.relation_id == predicate_id),
        None,
    )
    if row is not None:
        return _ReadPolicy(read_derivation_policy=row.read_derivation_policy)
    # The frozen first learned relation is directional.  Each returned item is
    # still joined to its agent-local binding and captured pin below.
    if predicate_id == "mentors":
        return _ReadPolicy(read_derivation_policy="none")
    return None


def _controls(
    records: tuple[CanonicalMemoryRecord, ...],
) -> (
    tuple[
        dict[str, StructuredClaimCatalogBinding],
        dict[tuple[str, str], StructuredGrantState],
        dict[str, CatalogCapturedTurnPin],
        dict[str, CanonicalMemoryRecord],
    ]
    | None
):
    bindings: dict[str, StructuredClaimCatalogBinding] = {}
    grants: dict[tuple[str, str], StructuredGrantState] = {}
    pins: dict[str, CatalogCapturedTurnPin] = {}
    projections: dict[str, CanonicalMemoryRecord] = {}
    for record in records:
        if record.source_kind == "semantic_ingestion_structured_claim_catalog_binding":
            try:
                binding = StructuredClaimCatalogBinding.model_validate(record.content["binding"])
            except (KeyError, TypeError, ValueError):
                return None
            if (
                record.memory_id != "semantic_ingestion:structured-claim-catalog:" + binding.claim_assertion_id
                or binding.claim_assertion_id in bindings
            ):
                return None
            bindings[binding.claim_assertion_id] = binding
        elif record.source_kind == "semantic_ingestion_structured_grant_state":
            try:
                state = StructuredGrantState.model_validate(record.content["state"])
            except (KeyError, TypeError, ValueError):
                return None
            key = (state.grant_kind, state.grant.grant_id)
            if key in grants:
                return None
            grants[key] = state
        elif record.source_kind == "semantic_ingestion_catalog_capture_pin":
            try:
                pin = CatalogCapturedTurnPin.model_validate(record.content["catalog_capture_pin"])
            except (KeyError, TypeError, ValueError):
                return None
            if record.memory_id != pin.memory_id or pin.memory_id in pins:
                return None
            pins[pin.memory_id] = pin
        elif record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion":
            claim_id = record.content.get("claim_assertion_id")
            if not isinstance(claim_id, str) or claim_id in projections:
                return None
            projections[claim_id] = record
    return bindings, grants, pins, projections


def _current_grants(
    grant_states: dict[tuple[str, str], StructuredGrantState], authority: StructuredFactReadAuthority
) -> bool:
    fact = grant_states.get(("fact", authority.fact_grant.grant_id))
    catalog = grant_states.get(("catalog_visibility", authority.catalog_visibility_grant.grant_id))
    return bool(
        fact is not None
        and catalog is not None
        and fact.active
        and catalog.active
        and fact.grant == authority.fact_grant
        and catalog.grant == authority.catalog_visibility_grant
    )


def verified_lifecycle_transitions(
    records: tuple[CanonicalMemoryRecord, ...],
) -> tuple[_LifecycleTransition, ...] | None:
    """Decode the immutable native request/reload pairs for lifecycle history.

    A group primary is persisted in the same successful CAS as its claim
    projections and schema-2 bindings.  The request carries the sealed target
    selection; the reload proves that exact request reached a committed group
    result.  Neither a free-standing planning record nor an unverified reload
    may change a direct read.
    """
    from memorii.core.memory_evolution.bootstrap_group_primary import (
        BootstrapGroupPrimaryVerificationError,
        decode_verified_bootstrap_graph_group_commit_primary,
    )
    from memorii.core.semantic_ingestion.contracts import (
        BootstrapNativeCorrectionEffectV3,
        BootstrapNativeRetractionEffectV3,
    )

    transitions: list[_LifecycleTransition] = []
    seen: set[str] = set()
    for record in records:
        if record.source_kind != "semantic_ingestion_bootstrap_graph_v3_group_commit_primary":
            continue
        try:
            request, reload = decode_verified_bootstrap_graph_group_commit_primary(
                record, require_committed_result=False,
            )
        except BootstrapGroupPrimaryVerificationError:
            return None
        core = reload.persisted_result.core
        if (
            reload.transaction_group_id != request.transaction_group_id
            or reload.operation_ids != request.operation_ids
            or reload.request_ctv_digest != request.request_ctv_digest
            or core.request_ctv_digest != request.request_ctv_digest
            or tuple(item.operation_id for item in core.ordered_operation_results) != request.operation_ids
        ):
            return None
        results = {item.operation_id: item for item in core.ordered_operation_results}
        if any(
            (result := results.get(input_item.operation_id)) is None
            or result.final_status != input_item.reduction.native_terminal.status
            for input_item in request.ordered_operation_inputs
        ):
            return None
        if core.disposition != "committed":
            continue
        if reload.group_result_schema_version < 2:
            return None
        for input_item in request.ordered_operation_inputs:
            materialization = input_item.reduction.effect_materialization
            effect = materialization.accepted_effect
            result = results.get(input_item.operation_id)
            assert result is not None
            if not isinstance(effect, (BootstrapNativeCorrectionEffectV3, BootstrapNativeRetractionEffectV3)):
                continue
            if result.final_status != "accepted":
                continue
            transition_records = tuple(
                item
                for item in effect.transition_records
                if item.record_kind == "temporal_transition"
                and item.planning_payload.planning_record.get("transition_kind") == effect.kind
            )
            if len(transition_records) != 1:
                return None
            transition = transition_records[0]
            transition_values = transition.planning_payload.planning_record
            transition_id = transition_values.get("transition_id")
            if not isinstance(transition_id, str) or transition.record_id != transition_id:
                return None
            compared_bindings = (
                effect.corrected_targets
                if isinstance(effect, BootstrapNativeCorrectionEffectV3)
                else effect.retracted_targets
            )
            try:
                compared = tuple(sorted(_target_claim_id(binding) for binding in compared_bindings))
            except ValueError:
                return None
            if not compared or len(compared) != len(set(compared)):
                return None
            next_claims = (
                tuple(
                    item.record_id
                    for item in effect.replacement_effect.planning_records
                    if item.record_kind == "claim_assertion"
                    and item.planning_payload.planning_record.get("claim_assertion_id") == item.record_id
                )
                if isinstance(effect, BootstrapNativeCorrectionEffectV3)
                else ()
            )
            if isinstance(effect, BootstrapNativeCorrectionEffectV3) and len(next_claims) != 1:
                return None
            if isinstance(effect, BootstrapNativeRetractionEffectV3) and next_claims:
                return None
            if transition_id in seen:
                return None
            seen.add(transition_id)
            transitions.append(
                _LifecycleTransition(
                    transition_id=transition_id,
                    operation_id=input_item.operation_id,
                    transition_kind=effect.kind,
                    compared_claim_ids=compared,
                    next_claim_ids=next_claims,
                    recorded_at=record.timestamp,
                )
            )
    return tuple(sorted(transitions, key=lambda item: (item.recorded_at, item.transition_id)))


_lifecycle_transitions = verified_lifecycle_transitions


def _query_projected_claims(
    *,
    records: tuple[CanonicalMemoryRecord, ...],
    projections: dict[str, CanonicalMemoryRecord],
    request: StructuredFactReadRequest,
    transitions: tuple[_LifecycleTransition, ...],
) -> tuple[_ProjectedClaim, ...] | None:
    """Reconstruct native claim state from protected immutable projections."""
    binding_times = {
        record.content["binding"]["claim_assertion_id"]: record.timestamp
        for record in records
        if record.source_kind == "semantic_ingestion_structured_claim_catalog_binding"
        and isinstance(record.content.get("binding"), dict)
        and isinstance(record.content["binding"].get("claim_assertion_id"), str)
    }
    next_times = {
        claim_id: transition.recorded_at for transition in transitions for claim_id in transition.next_claim_ids
    }
    lifecycle: dict[str, str] = {claim_id: "active" for claim_id in projections}
    cutoff = request.system_as_of
    for transition in transitions:
        if cutoff is not None and transition.recorded_at > cutoff:
            continue
        prior_state = "superseded" if transition.transition_kind == "correction" else "retracted"
        for claim_id in transition.compared_claim_ids:
            lifecycle[claim_id] = prior_state
        for claim_id in transition.next_claim_ids:
            lifecycle[claim_id] = "active"

    claims: list[_ProjectedClaim] = []
    for claim_id, projection in projections.items():
        identity = projection.content.get("claim_identity")
        if not isinstance(identity, dict):
            return None
        key = identity.get("assertion_key_at_recording")
        slot = key.get("slot") if isinstance(key, dict) else None
        value = key.get("value") if isinstance(key, dict) else None
        subject = identity.get("subject_assertion_ref")
        if not isinstance(slot, dict) or not isinstance(value, dict) or not isinstance(subject, dict):
            return None
        predicate_id = slot.get("predicate_id")
        subject_id = subject.get("logical_entity_id_at_assertion")
        object_value = (
            value.get("object_logical_entity_id")
            if value.get("object_kind") == "entity"
            else value.get("canonical_literal_value")
        )
        available_at = binding_times.get(claim_id)
        if claim_id in next_times and available_at is not None:
            available_at = max(available_at, next_times[claim_id])
        if (
            not isinstance(predicate_id, str)
            or not isinstance(subject_id, str)
            or not isinstance(object_value, str)
        ):
            return None
        if available_at is None:
            return None
        if (
            predicate_id != request.predicate_id
            or (request.subject_entity_id != "*" and subject_id != request.subject_entity_id)
            or (cutoff is not None and available_at > cutoff)
        ):
            continue
        state = lifecycle.get(claim_id, "active")
        # A transaction-time query reconstructs the effective claim set at
        # that instant.  Unbounded history remains an audit view and includes
        # superseded and retracted claims with their lifecycle labels.
        if (request.view == "current" or cutoff is not None) and state != "active":
            continue
        claims.append(
            _ProjectedClaim(
                claim_id=claim_id,
                predicate_id=predicate_id,
                subject_entity_id=subject_id,
                object_value=object_value,
                lifecycle_state=state,
                valid_from=projection.valid_from,
                valid_to=projection.valid_to,
                system_time=available_at,
                provenance=str(projection.content.get("source_id", "")),
                projection=projection,
            )
        )
    return tuple(sorted(claims, key=lambda claim: (claim.system_time, claim.claim_id)))


def _projected_items(
    *,
    claims: tuple[_ProjectedClaim, ...],
    records: tuple[CanonicalMemoryRecord, ...],
    bindings: dict[str, StructuredClaimCatalogBinding],
    grant_states: dict[tuple[str, str], StructuredGrantState],
    pins: dict[str, CatalogCapturedTurnPin],
    authority: StructuredFactReadAuthority,
    reverse: bool,
    requested_reverse_endpoint: str | None = None,
) -> list[StructuredFactReadItem] | None:
    locator = PackageIndexedCatalogBundleLocator()
    items: list[StructuredFactReadItem] = []
    for claim in claims:
        binding = bindings.get(claim.claim_id)
        if binding is None or binding.schema_version != 2:
            return None
        if not verify_structured_catalog_projection_for_read(
            claim.projection,
            bindings=bindings,
            grant_states=grant_states,
            pins=pins,
            records=records,
            authority=authority,
            catalog_bundle_locator=locator,
        ):
            return None
        if reverse and (
            requested_reverse_endpoint is None
            or not _endpoint_visibility_allows(
                claim.projection,
                requested_reverse_endpoint,
                claim.subject_entity_id,
                claim.object_value,
            )
        ):
            return None
        items.append(
            StructuredFactReadItem(
                claim_id=claim.claim_id,
                source_claim_id=claim.claim_id,
                predicate_id=claim.predicate_id,
                subject_entity_id=claim.object_value if reverse else claim.subject_entity_id,
                object_value=claim.subject_entity_id if reverse else claim.object_value,
                lifecycle_state=claim.lifecycle_state,
                valid_from=claim.valid_from,
                valid_to=claim.valid_to,
                system_time=claim.system_time,
                provenance=claim.provenance,
                catalog_version_id=binding.selected_version_id or "",
                catalog_version_digest=binding.selected_version_digest or "",
                derived_direction="reverse" if reverse else "forward",
            )
        )
    return items


def _target_claim_id(binding: object) -> str:
    """Extract only the closed claim selector carried by a correction target."""
    authority = getattr(binding, "authority", None)
    target = getattr(authority, "target", None)
    record_id = getattr(target, "record_id", None)
    if not isinstance(record_id, str) or not record_id:
        raise ValueError("lifecycle target is not a retained claim record")
    return record_id


def _query_states(
    records: tuple[CanonicalMemoryRecord, ...],
    *,
    request: StructuredFactReadRequest,
    now: datetime,
    transitions: tuple[_LifecycleTransition, ...],
) -> list[ClaimState]:
    query = ClaimStateQueryService(repository=EvolutionStateRepository.from_snapshot(records), now_provider=lambda: now)
    if request.view == "current" or request.system_as_of is not None:
        # ``system_as_of`` is transaction time, while HISTORICAL_AT is valid
        # time.  Both current and as-of reads reconstruct one effective claim
        # image from immutable versions instead of using it as a validity
        # predicate.  History without a cutoff remains an audit view.
        versions = query.retrieve(
            view=RetrievalView.ALL_VERSIONS,
            predicate_id=request.predicate_id,
            subject_entity_id=request.subject_entity_id,
        )
        if request.system_as_of is not None:
            # Begin with the presently active claim IDs and reverse only the
            # immutable transitions recorded after the requested system time.
            # This retains the pre-correction target even though its current
            # state is superseded and never confuses system time with validity.
            active_ids = {state.claim_id for state in versions if state.lifecycle_state is ClaimLifecycleState.ACTIVE}
            revived_ids: set[str] = set()
            for transition in reversed(transitions):
                if transition.recorded_at > request.system_as_of:
                    active_ids.difference_update(transition.next_claim_ids)
                    active_ids.update(transition.compared_claim_ids)
                    revived_ids.update(transition.compared_claim_ids)
            versions = [
                state
                for state in versions
                if state.claim_id in active_ids
                and (state.updated_at <= request.system_as_of or state.claim_id in revived_ids)
            ]
            return versions
        return [state for state in versions if state.lifecycle_state is ClaimLifecycleState.ACTIVE]
    return [
        state
        for state in query.retrieve(
            view=RetrievalView.ALL_VERSIONS,
            predicate_id=request.predicate_id,
            subject_entity_id=request.subject_entity_id,
        )
        # A revoked claim is a content-free tombstone: excluded from every
        # view, including all-versions history reads. This branch cannot
        # rely on its candidate-only exclusion.
        if state.lifecycle_state is not ClaimLifecycleState.CANDIDATE
        and state.lifecycle_state is not ClaimLifecycleState.REVOKED
    ]


def _items(
    *,
    states: list[ClaimState],
    records: tuple[CanonicalMemoryRecord, ...],
    bindings: dict[str, StructuredClaimCatalogBinding],
    grant_states: dict[tuple[str, str], StructuredGrantState],
    pins: dict[str, CatalogCapturedTurnPin],
    projections: dict[str, CanonicalMemoryRecord],
    authority: StructuredFactReadAuthority,
    request: StructuredFactReadRequest,
    reverse: bool,
) -> list[StructuredFactReadItem] | None:
    items: list[StructuredFactReadItem] = []
    locator = PackageIndexedCatalogBundleLocator()
    for state in states:
        claim_id = state.claim_id if state.claim_id in bindings else state.source_claim_id
        binding = bindings.get(claim_id)
        projection = projections.get(claim_id)
        if (
            binding is None
            or projection is None
            or binding.schema_version != 2
            or binding.claim_assertion_id != claim_id
            or state.lifecycle_state is ClaimLifecycleState.CANDIDATE
            or state.claim_key.predicate_id != request.predicate_id
        ):
            return None
        if not _projection_matches_state(projection, state, claim_id):
            return None
        if not verify_structured_catalog_projection_for_read(
            projection,
            bindings=bindings,
            grant_states=grant_states,
            pins=pins,
            records=records,
            authority=authority,
            catalog_bundle_locator=locator,
        ):
            return None
        if reverse and not _endpoint_visibility_allows(
            projection, request.subject_entity_id, state.claim_key.subject_entity_id, state.object_value
        ):
            return None
        items.append(
            StructuredFactReadItem(
                claim_id=state.claim_id,
                source_claim_id=state.source_claim_id,
                predicate_id=state.claim_key.predicate_id,
                subject_entity_id=state.object_value if reverse else state.claim_key.subject_entity_id,
                object_value=state.claim_key.subject_entity_id if reverse else state.object_value,
                lifecycle_state=state.lifecycle_state.value,
                valid_from=state.valid_from,
                valid_to=state.valid_to,
                system_time=state.updated_at,
                provenance=state.source_claim_id,
                catalog_version_id=binding.selected_version_id or "",
                catalog_version_digest=binding.selected_version_digest or "",
                derived_direction="reverse" if reverse else "forward",
            )
        )
    return items


def _endpoint_visibility_allows(
    projection: CanonicalMemoryRecord, requested: str, subject: str, object_value: str
) -> bool:
    """Bind both reverse endpoints to the authorized immutable claim identity."""
    identity = projection.content.get("claim_identity")
    if not isinstance(identity, dict):
        return False
    subject_ref = identity.get("subject_assertion_ref")
    object_ref = identity.get("object_assertion_ref")
    if not isinstance(subject_ref, dict) or not isinstance(object_ref, dict):
        return False
    return (
        subject_ref.get("logical_entity_id_at_assertion") == subject
        and object_ref.get("logical_entity_id_at_assertion") == object_value
        and requested == object_value
    )


def _projection_matches_state(
    projection: CanonicalMemoryRecord,
    state: ClaimState,
    claim_id: str,
) -> bool:
    """Join a state only to its immutable assertion projection.

    The state repository is intentionally general purpose.  A direct fact
    reader must additionally prove that the selected state has the exact
    protected assertion carrier whose schema-2 binding was verified.
    """
    if (
        projection.content.get("claim_assertion_id") != claim_id
        or projection.content.get("claim_assertion_record_digest") is None
    ):
        return False
    identity = projection.content.get("claim_identity")
    if not isinstance(identity, dict):
        return False
    key = identity.get("assertion_key_at_recording")
    if not isinstance(key, dict):
        return False
    slot = key.get("slot")
    if not isinstance(slot, dict) or slot.get("predicate_id") != state.claim_key.predicate_id:
        return False
    subject = identity.get("subject_assertion_ref")
    if not isinstance(subject, dict):
        return False
    return subject.get("logical_entity_id_at_assertion") == state.claim_key.subject_entity_id


@dataclass(frozen=True)
class _CurrentFactCandidate:
    record_ids: frozenset[str]
    claim_ids: frozenset[str]
    entity_ids: frozenset[str]
    source_ids: frozenset[str]
    item: StructuredFactReadItem | None

    def suppressed(self, view: RevokedIdentityView) -> bool:
        identities = view.identities
        return bool(
            self.record_ids & identities.records
            or self.claim_ids & identities.claims
            or self.entity_ids & identities.entities
            or self.source_ids & (identities.sources | identities.records)
        )


@dataclass(frozen=True)
class PendingCurrentCatalogRead:
    subject_id: str
    candidates: tuple[_CurrentFactCandidate, ...]

    def release(self, view: RevokedIdentityView) -> tuple[StructuredFactReadItem, ...] | None:
        if view.is_revoked_entity(self.subject_id):
            return ()
        items: dict[tuple[str, str], StructuredFactReadItem] = {}
        for candidate in self.candidates:
            if candidate.suppressed(view):
                continue
            item = candidate.item
            if item is None:
                return None
            # Native and claim-state carriers may describe the same assertion.
            items.setdefault((item.source_claim_id, item.derived_direction), item)
        return tuple(sorted(items.values(), key=lambda item: (item.system_time, item.claim_id, item.derived_direction)))


class CatalogBoundProjectionReadVerifier(LegacyBootstrapV3ProjectionReadVerifier, Protocol):
    def verify_catalog_bound_bootstrap_v3_runtime_projection(
        self,
        projection: CanonicalMemoryRecord,
        *,
        records: tuple[CanonicalMemoryRecord, ...],
        endpoints: tuple[tuple[str, str], ...],
        required_ids: set[str],
    ) -> bool: ...


def _native_selectors(record: CanonicalMemoryRecord) -> tuple[object, object, object, bool]:
    identity = record.content.get("claim_identity")
    key = identity.get("assertion_key_at_recording") if isinstance(identity, dict) else None
    slot = key.get("slot") if isinstance(key, dict) else None
    value = key.get("value") if isinstance(key, dict) else None
    if not isinstance(slot, dict) or not isinstance(value, dict):
        return None, None, None, False
    is_entity = value.get("object_kind") == "entity"
    return (
        slot.get("predicate_id"), slot.get("subject_logical_entity_id"),
        value.get("object_logical_entity_id" if is_entity else "canonical_literal_value"), is_entity,
    )


def _control_record(
    record: CanonicalMemoryRecord | None, *, domain: MemoryDomain, source_kind: str,
) -> bool:
    return (
        record is not None and record.domain is domain and record.source_kind == source_kind
        and record.visibility is MemoryRecordVisibility.INTERNAL_CONTROL and record.status is CommitStatus.COMMITTED
    )


def _current_bounds(start: datetime | None, end: datetime | None, now: datetime) -> bool:
    return (start is None or start <= now) and (end is None or now < end)


def _native_source_verified(
    projection: CanonicalMemoryRecord, source: CanonicalMemoryRecord, *, now: datetime,
) -> bool:
    try:
        evidence = SourceAuthorityEvidence.model_validate(projection.content.get("source_authority_evidence"))
        return (
            source.status is CommitStatus.COMMITTED
            and _current_eligible(source, now)
            and source.memory_id == evidence.source_id == projection.content.get("source_id")
            and source_admission_source_digest(source) == evidence.source_digest == projection.content.get("source_digest")
            and source.user_id == projection.user_id
            and source.agent_id == projection.agent_id
            and source.task_id == projection.task_id
        )
    except (TypeError, ValueError):
        return False


def read_current_catalog_bound_facts(
    *,
    records: tuple[CanonicalMemoryRecord, ...],
    revision: int,
    grant: ResolvedScopedReadGrant,
    current_authorities: Mapping[CatalogAuthorityCoordinate, StructuredFactReadAuthority],
    grant_states: Mapping[tuple[str, str], StructuredGrantState],
    locator: CatalogBundleLocator,
    legacy_verifier: CatalogBoundProjectionReadVerifier,
    predicate_id: str,
    subject_id: str,
    symmetric: bool,
    now: datetime,
) -> PendingCurrentCatalogRead:
    """Assemble currently eligible exact claims before the final serving sample."""
    by_id = {record.memory_id: record for record in records}
    projections: dict[str, list[CanonicalMemoryRecord]] = {}
    state_records: dict[str, list[CanonicalMemoryRecord]] = {}
    for record in records:
        if record.domain is not MemoryDomain.SEMANTIC or not _authorized(record, grant):
            continue
        if _is_new_structured_claim_projection(record):
            predicate, subject, value, is_entity = _native_selectors(record)
            claim_id = record.content.get("claim_assertion_id")
            if isinstance(claim_id, str) and predicate == predicate_id and (
                subject == subject_id or (symmetric and is_entity and value == subject_id)
            ):
                projections.setdefault(claim_id, []).append(record)
        elif record.content.get("memory_evolution_kind") == "claim_state":
            raw = record.content.get("claim_state")
            if not isinstance(raw, dict):
                continue
            key = raw.get("claim_key")
            if not isinstance(key, dict) or key.get("predicate_id") != predicate_id or not (
                key.get("subject_entity_id") == subject_id or (symmetric and raw.get("object_value") == subject_id)
            ):
                continue
            ids = [value for value in (raw.get("claim_id"), raw.get("source_claim_id")) if isinstance(value, str)]
            bound_id = next((value for value in ids if "semantic_ingestion:structured-claim-catalog:" + value in by_id), None)
            if bound_id is None:
                # This carrier also stores pre-catalog claim states.
                continue
            state_records.setdefault(bound_id, []).append(record)

    pending: list[_CurrentFactCandidate] = []
    live_projections = {
        claim_id: candidates for claim_id, candidates in projections.items()
        if any(
            row.validity_status not in {TemporalValidityStatus.EXPIRED, TemporalValidityStatus.INVALIDATED}
            and _current_bounds(row.valid_from, row.valid_to, now)
            for row in candidates
        )
    }
    backing_projections: dict[str, list[CanonicalMemoryRecord]] = {}
    # A claim-state row is the serving carrier under its own committed scope.
    # Its exact assertion projection can be retained solely as proof.
    for record in records:
        if (
            record.domain is MemoryDomain.SEMANTIC
            and record.visibility is MemoryRecordVisibility.RUNTIME_CONTEXT
            and record.status is CommitStatus.COMMITTED
            and _is_new_structured_claim_projection(record)
            and isinstance(claim_id := record.content.get("claim_assertion_id"), str)
            and claim_id in state_records
            and claim_id not in live_projections
            and any(
                state.user_id == record.user_id and state.task_id == record.task_id
                and record.session_id in (None, state.session_id)
                for state in state_records[claim_id]
            )
        ):
            backing_projections.setdefault(claim_id, []).append(record)
    visible_bindings: dict[str, StructuredClaimCatalogBinding | None] = {}
    for claim_id in live_projections.keys() | state_records.keys():
        binding_record = by_id.get("semantic_ingestion:structured-claim-catalog:" + claim_id)
        binding = None
        if binding_record is not None and _control_record(
            binding_record, domain=MemoryDomain.SEMANTIC, source_kind="semantic_ingestion_structured_claim_catalog_binding",
        ):
            try:
                binding = StructuredClaimCatalogBinding.model_validate(binding_record.content.get("binding"))
            except ValidationError:
                binding = None
        if binding is not None:
            authority = current_authorities.get(binding.catalog_scope)
            if authority is None or (
                authority.authenticated != binding.authenticated
                or authority.fact_grant.fact_scope != binding.fact_scope
            ):
                continue
        visible_bindings[claim_id] = binding
    live_projections = {claim_id: items for claim_id, items in live_projections.items() if claim_id in visible_bindings}
    state_records = {claim_id: items for claim_id, items in state_records.items() if claim_id in visible_bindings}
    if not live_projections and not state_records:
        return PendingCurrentCatalogRead(subject_id, ())

    # Fanout indexes identify the immutable native groups that produced the
    # claim and any native correction or retraction targeting that claim.
    relevant_ids = {claim_id.encode("utf-8").hex() for claim_id in live_projections.keys() | state_records.keys()}
    group_ids = {
        row.content.get("transaction_group_id")
        for matching in live_projections.values() for row in matching
        if isinstance(row.content.get("transaction_group_id"), str)
    }
    primary_ids = {
        row.content.get("primary_id") for row in records
        if row.source_kind == "semantic_ingestion_bootstrap_graph_v3_group_commit_fanout"
        and isinstance(row.content.get("primary_id"), str)
        and isinstance(row.content.get("transaction_group_id"), str)
        and row.content["transaction_group_id"] in group_ids
    }
    transition_records = tuple(
        record for record in records
        if record.source_kind == "semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
        and (
            record.memory_id in primary_ids
            or (
                isinstance(payload := record.content.get("request_hex"), str)
                and any(value in payload for value in relevant_ids)
            )
        )
    )
    transitions = verified_lifecycle_transitions(transition_records)
    retired: set[str] = set()
    replacement_times: dict[str, datetime] = {}
    for transition in transitions or ():
        if transition.recorded_at <= now:
            retired.update(transition.compared_claim_ids)
            retired.difference_update(transition.next_claim_ids)
            for claim_id in transition.next_claim_ids:
                replacement_times[claim_id] = transition.recorded_at

    for claim_id in sorted(live_projections.keys() | state_records.keys()):
        if claim_id in retired:
            continue
        native = live_projections.get(claim_id) or backing_projections.get(claim_id, [])
        states: list[tuple[CanonicalMemoryRecord, ClaimState | None]] = []
        for record in state_records.get(claim_id, ()):
            try:
                state = ClaimState.model_validate(record.content.get("claim_state"))
            except ValidationError:
                state = None
            states.append((record, state))
        if states and all(
            state is not None
            and (
                state.lifecycle_state is not ClaimLifecycleState.ACTIVE
                or not _current_bounds(state.valid_from, state.valid_to, now)
            )
            for _, state in states
        ):
            continue
        projection = native[0] if native else None
        binding_id = "semantic_ingestion:structured-claim-catalog:" + claim_id
        binding_record = by_id.get(binding_id)
        binding = visible_bindings[claim_id]
        authority = current_authorities.get(binding.catalog_scope) if binding is not None else None
        if binding_record is None and projection is not None and (
            legacy_verifier.verify_legacy_bootstrap_v3_runtime_projection(
                projection, revision=revision, records=records, grant=grant,
            ) == "verified"
        ):
            continue

        state_record, state = states[0] if states else (None, None)
        record_ids = {binding_id, *[row.memory_id for row in native], *[row.memory_id for row, _ in states]}
        claim_ids = {claim_id}
        source_ids: set[str] = set()
        entities = {subject_id}
        item = None
        if state is not None:
            claim_ids.update((state.claim_id, state.source_claim_id))
        if state_record is not None:
            source_ids.update(_source_closure_ids(state_record, by_id))
        if projection is not None:
            predicate, subject, value, is_entity = _native_selectors(projection)
            if isinstance(subject, str):
                entities.add(subject)
            if is_entity and isinstance(value, str):
                entities.add(value)
            source = projection.content.get("source_id")
            retained_source = by_id.get(source) if isinstance(source, str) else None
            if isinstance(source, str):
                source_ids.add(source)
                if retained_source is not None:
                    source_ids.update(_source_closure_ids(retained_source, by_id))
            source_ids.update(_source_closure_ids(projection, by_id))
            try:
                identity = AcceptedClaimIdentity.model_validate_json(json.dumps(projection.content.get("claim_identity")))
            except (TypeError, ValueError):
                identity = None
            if identity is not None:
                endpoints = tuple(
                    (ref.entity_revision_id, ref.logical_entity_id_at_assertion)
                    for ref in (identity.subject_assertion_ref, identity.object_assertion_ref)
                    if ref is not None
                )
                record_ids.update(revision_id for revision_id, _ in endpoints)
            else:
                endpoints = ()
            pins: dict[str, CatalogCapturedTurnPin] = {}
            if binding is not None and binding.pin_memory_id is not None:
                record_ids.add(binding.pin_memory_id)
                pin_record = by_id.get(binding.pin_memory_id)
                if pin_record is not None and _control_record(
                    pin_record, domain=MemoryDomain.EXECUTION, source_kind="semantic_ingestion_catalog_capture_pin",
                ):
                    try:
                        pin = CatalogCapturedTurnPin.model_validate(pin_record.content.get("catalog_capture_pin"))
                    except ValidationError:
                        pin = None
                    if pin is not None and pin.memory_id == pin_record.memory_id:
                        pins[pin.memory_id] = pin

            state_verified = not states or (
                len(states) == 1 and state_record is not None and state is not None
                and _inner_scope_agrees(state_record) and state.claim_key.subject_entity_id == subject
                and state.claim_key.predicate_id == predicate_id and state.object_value == value
                and bool(_source_closure_ids(state_record, by_id))
            )
            provenance_verified = all(
                (dependency := by_id.get(source_id)) is not None
                and (
                    source_id == source
                    or (_authorized(dependency, grant) and _current_eligible(dependency, now))
                )
                for source_id in source_ids
            )
            if (
                len(native) == 1 and state_verified and transitions is not None
                and binding_record is not None and binding is not None and authority is not None
                and binding.claim_assertion_id == claim_id and identity is not None
                and isinstance(subject, str) and isinstance(value, str) and isinstance(source, str)
                and retained_source is not None and _native_source_verified(projection, retained_source, now=now)
                and provenance_verified
                and verify_structured_catalog_projection_for_read(
                    projection, bindings={claim_id: binding}, grant_states=grant_states, pins=pins,
                    records=records, authority=authority, catalog_bundle_locator=locator,
                    required_predicate_id=predicate_id,
                )
                and legacy_verifier.verify_catalog_bound_bootstrap_v3_runtime_projection(
                    projection, records=records, endpoints=endpoints, required_ids=record_ids,
                )
            ):
                version = SeedCatalogBundleLocator().locate().version if binding.schema_version == 1 else None
                version_id = version.version_id if version is not None else binding.selected_version_id
                version_digest = version.version_digest if version is not None else binding.selected_version_digest
                if version_id is not None and version_digest is not None:
                    directions: list[Literal["forward", "reverse"]] = []
                    if subject == subject_id:
                        directions.append("forward")
                    if symmetric and is_entity and value == subject_id:
                        directions.append("reverse")
                    for direction in directions:
                        item = StructuredFactReadItem(
                            claim_id=state.claim_id if state is not None else claim_id,
                            source_claim_id=state.source_claim_id if state is not None else claim_id,
                            predicate_id=predicate_id,
                            subject_entity_id=value if direction == "reverse" else subject,
                            object_value=subject if direction == "reverse" else value,
                            lifecycle_state="active",
                            valid_from=state.valid_from if state is not None else projection.valid_from,
                            valid_to=state.valid_to if state is not None else projection.valid_to,
                            system_time=(
                                state.updated_at if state is not None else
                                max(binding_record.timestamp, replacement_times.get(claim_id, binding_record.timestamp))
                            ),
                            provenance=state.source_claim_id if state is not None else source,
                            catalog_version_id=version_id,
                            catalog_version_digest=version_digest,
                            derived_direction=direction,
                        )
                        pending.append(_CurrentFactCandidate(
                            frozenset(record_ids), frozenset(claim_ids), frozenset(entities), frozenset(source_ids), item,
                        ))
                    continue
        pending.append(_CurrentFactCandidate(
            frozenset(record_ids), frozenset(claim_ids), frozenset(entities), frozenset(source_ids), item,
        ))
    return PendingCurrentCatalogRead(subject_id, tuple(pending))


__all__ = [
    "StructuredFactReadItem",
    "StructuredFactReadRequest",
    "StructuredFactReadResponse",
    "read_structured_facts_from_snapshot",
]

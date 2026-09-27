"""Protected, snapshot-linearized reads of structured semantic facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.claim_queries import ClaimStateQueryService
from memorii.core.memory_evolution.models import ClaimLifecycleState, ClaimState, RetrievalView
from memorii.core.memory_evolution.state_repository import EvolutionStateRepository
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.scoped_context.service import verify_structured_catalog_projection_for_read
from memorii.core.semantic_ingestion.catalog_authority import (
    StructuredClaimCatalogBinding,
    StructuredFactReadAuthority,
    StructuredGrantState,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import (
    CatalogCapturedTurnPin,
    PackageIndexedCatalogBundleLocator,
)
from memorii.core.semantic_ingestion.default_catalog_corpus import (
    DefaultCatalogCorpusRow,
    load_default_catalog_acceptance_corpus,
)


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


def _catalog_row(predicate_id: str) -> DefaultCatalogCorpusRow | None:
    return next((row for row in load_default_catalog_acceptance_corpus().rows if row.relation_id == predicate_id), None)


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
                record, require_committed_result=True,
            )
        except BootstrapGroupPrimaryVerificationError:
            return None
        core = reload.persisted_result.core
        if (
            reload.group_result_schema_version < 2
            or reload.transaction_group_id != request.transaction_group_id
            or reload.operation_ids != request.operation_ids
            or reload.request_ctv_digest != request.request_ctv_digest
            or core.request_ctv_digest != request.request_ctv_digest
            or core.disposition != "committed"
            or tuple(item.operation_id for item in core.ordered_operation_results) != request.operation_ids
        ):
            return None
        results = {item.operation_id: item for item in core.ordered_operation_results}
        for input_item in request.ordered_operation_inputs:
            materialization = input_item.reduction.effect_materialization
            effect = materialization.accepted_effect
            result = results.get(input_item.operation_id)
            if result is None or result.final_status != input_item.reduction.native_terminal.status:
                return None
            if not isinstance(effect, (BootstrapNativeCorrectionEffectV3, BootstrapNativeRetractionEffectV3)):
                continue
            if result.final_status != "accepted":
                return None
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
        if state.lifecycle_state is not ClaimLifecycleState.CANDIDATE
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


__all__ = [
    "StructuredFactReadItem",
    "StructuredFactReadRequest",
    "StructuredFactReadResponse",
    "read_structured_facts_from_snapshot",
]

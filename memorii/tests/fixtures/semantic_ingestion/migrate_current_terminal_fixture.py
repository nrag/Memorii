"""Migrate the captured terminal fixtures under a graph-grammar change.

The `.ctv` captures embed graph snapshots, planning states, and read sets
whose digests cover the codec/reference manifest fingerprints and the
per-kind record counts. When the canonical graph grammar changes (a new
record kind joins the closed union), the captures go stale: their counts
tuples and fingerprints no longer match the deployed manifests, and every
enclosing content-addressed digest diverges.

This tool re-derives each capture against the CURRENT grammar:

1. replace the old codec/reference manifest fingerprints by value and
   insert the new kind's zero count into every snapshot counts tuple,
2. rebuild the payload as real models bottom-up: every child becomes a
   validated model before its parent's digest is recomputed over the
   fully-serialized body (``model_dump``), so wrap serializers and
   conditional omissions apply exactly as they did at capture time,
3. special digest shapes are honored in the same pass — the coordinator
   request's subset core digest, the snapshot-authority's replay pin,
   the graph-plane read-set/snapshot/planning-state digests, and the
   content-addressed ``_digest_field`` convention with its versioned
   exclusions,
4. the coordinator is rebuilt first and its request/epoch digests are
   scattered through every raw sibling that pins them before those
   siblings rebuild, and
5. the re-encoded envelope bytes are re-gzipped and the fixture manifest
   digests refreshed.

Nothing is hand-edited: the wire bytes stay byte-representative of a
capture made under the current grammar.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import warnings
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Literal, Union, get_args, get_origin

_FIXTURE_ROOT = Path(__file__).with_name("current_terminal")

_TARGETS = {
    "publication-request.ctv": "BootstrapGraphTerminalPublicationRequestV3",
    "terminal-reload.ctv": "BootstrapGraphTerminalReloadV3",
    "publication-intent.ctv": "BootstrapGraphTerminalPublicationIntentV3",
}

_NEW_KIND = "revocation_directive"

# The terminal member schema version of the capture being migrated; the
# canonical input cannot see the publication intent, so migrate() publishes
# it here for schema-aware result-digest pinning (v3 selects persisted
# result digests; other versions select the construction result digest).
_MEMBER_SCHEMA_VERSION = None

# The rebuilt publication-request root's exported pins, consumed when the
# memory-records fixture refreshes its terminal-recovery record.
_ROOT_EXPORT: dict = {}


# --- module and class resolution -------------------------------------------


def _modules() -> tuple:
    import memorii.core.memory_evolution.graph_effect_contracts as effects
    import memorii.core.semantic_ingestion.contracts as contracts

    return (contracts, effects)


def _model_class(name: str) -> type:
    for module in _modules():
        found = getattr(module, name, None)
        if isinstance(found, type) and hasattr(found, "model_fields"):
            if not found.__pydantic_complete__:
                rebuild_contracts = _modules()[0].rebuild_bootstrap_graph_effect_contracts
                rebuild_contracts()
            return found
    raise SystemExit(f"unknown contract class: {name}")


def _lookup(name: str) -> object:
    for module in _modules():
        found = getattr(module, name, None)
        if found is not None:
            return found
    return name


def _unwrap(annotation: object) -> object:
    if annotation.__class__ is Annotated or get_origin(annotation) is Annotated:
        return get_args(annotation)[0]
    return annotation


def _resolve_forward_ref(annotation: object) -> object:
    if isinstance(annotation, str):
        return _lookup(annotation)
    if annotation.__class__ is Annotated or get_origin(annotation) is Annotated:
        args = get_args(annotation)
        if args and isinstance(args[0], str):
            return Annotated[(_lookup(args[0]), *args[1:])]  # type: ignore[misc]
        if args:
            return Annotated[(args[0], *args[1:])]  # type: ignore[misc]
    return annotation


def _literal_accepts(candidate: type, data: dict) -> bool:
    for name, field in candidate.model_fields.items():
        if name not in data:
            continue
        annotation = _unwrap(_resolve_forward_ref(field.annotation))
        if get_origin(annotation) is Literal:
            if data[name] not in get_args(annotation):
                return False
    return True


def _candidate_classes(annotation: object, data: dict) -> list[type]:
    """Ordered union candidates for a dict payload; best first."""

    annotation = _unwrap(_resolve_forward_ref(annotation))
    if isinstance(annotation, type) and hasattr(annotation, "model_fields"):
        return [annotation]
    origin = get_origin(annotation)
    if origin in (list, tuple):
        args = get_args(annotation)
        return _candidate_classes(args[0], data) if args else []
    if origin is Union:
        candidates = [
            resolved
            for resolved in (
                _resolve_forward_ref(arg) for arg in get_args(annotation)
            )
            if isinstance(resolved, type) and hasattr(resolved, "model_fields")
        ]
        matches = [
            c for c in candidates if set(data) <= set(c.model_fields)
        ] or candidates
        exact = [c for c in matches if set(c.model_fields) == set(data)]
        discriminated = [c for c in (exact or matches) if _literal_accepts(c, data)]
        pool = discriminated or (exact or matches)
        pool.sort(key=lambda c: -len(set(data) & set(c.model_fields)))
        return pool
    return []


def _class_for_dict(annotation: object, data: dict) -> type | None:
    pool = _candidate_classes(annotation, data)
    return pool[0] if pool else None


def _rebuild_first(node: dict, annotation: object):
    """Rebuild with the first union candidate that validates."""

    errors: list[Exception] = []
    candidates = _candidate_classes(annotation, node)
    for candidate in candidates:
        try:
            return rebuild(node, candidate)
        except Exception as exc:  # noqa: BLE001 - try-next-variant
            errors.append(exc)
    if errors:
        raise errors[0]
    raise ValueError(
        "no union candidate resolved for payload with keys: "
        + ",".join(sorted(node))
    )


def _item_class(annotation: object, sample: dict) -> type | None:
    annotation = _unwrap(_resolve_forward_ref(annotation))
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (list, tuple) and args:
        return _class_for_dict(args[0], sample)
    return None


def _content_addressed_index() -> list[type]:
    seen: list[type] = []
    for module in _modules():
        rebuild_contracts = getattr(
            module, "rebuild_bootstrap_graph_effect_contracts", None
        )
        if rebuild_contracts is not None:
            rebuild_contracts()
            break
    for module in _modules():
        for name in dir(module):
            candidate = getattr(module, name)
            if (
                isinstance(candidate, type)
                and hasattr(candidate, "model_fields")
                and hasattr(candidate, "model_fields")
                and getattr(candidate, "_digest_domain", None) is not None
                and candidate not in seen
            ):
                seen.append(candidate)
    return seen


def _owner_by_field_set(node: dict) -> type | None:
    """Exact field-set match across content-addressed contracts."""

    keys = frozenset(node)
    matches = [
        cls
        for cls in _content_addressed_index()
        if frozenset(cls.model_fields) == keys
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    discriminated = [cls for cls in matches if _literal_accepts(cls, node)]
    return discriminated[0] if len(discriminated) == 1 else matches[0]


def _private_attr_default(cls: type, name: str):
    private = getattr(cls, "__private_attributes__", {}).get(name)
    if private is not None and getattr(private, "default", None) is not None:
        return private.default
    return getattr(cls, name, None)


def _contract_digest(domain: bytes, value: object) -> str:
    from memorii.core.semantic_ingestion.contracts import contract_digest

    return contract_digest(domain, value)


# --- value patching ---------------------------------------------------------


def _discover_replacements(payload: dict) -> dict[str, str]:
    from memorii.core.memory_evolution.graph_records import (
        canonical_graph_codec_manifest,
    )
    from memorii.core.memory_evolution.reference_integrity import (
        generated_reference_schema_manifest,
    )

    replacements: dict[str, str] = {}

    def find_codec(node: object) -> None:
        if isinstance(node, dict):
            fingerprint = node.get("codec_manifest_fingerprint")
            if isinstance(fingerprint, str):
                replacements.setdefault(
                    fingerprint,
                    canonical_graph_codec_manifest().manifest_fingerprint,
                )
            for value in node.values():
                find_codec(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                find_codec(item)

    find_codec(payload)
    old_codec = next(
        (
            old
            for old, new in replacements.items()
            if new == canonical_graph_codec_manifest().manifest_fingerprint
        ),
        None,
    )

    def find_reference(node: object) -> None:
        if old_codec is None:
            return
        if isinstance(node, dict):
            prints = node.get("manifest_fingerprints")
            if isinstance(prints, (list, tuple)):
                for item in prints:
                    if (
                        isinstance(item, str)
                        and len(item) == 64
                        and item != old_codec
                        and item not in replacements.values()
                    ):
                        replacements.setdefault(
                            item,
                            generated_reference_schema_manifest().manifest_fingerprint,
                        )
            for value in node.values():
                find_reference(value)
        elif isinstance(node, (list, tuple)):
            for member in node:
                find_reference(member)

    find_reference(payload)
    return replacements


def _patch_values(node: object, replacements: dict[str, str], new_kind: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and value in replacements:
                node[key] = replacements[value]
            elif key == "exact_record_counts_by_kind" and isinstance(
                value, (list, tuple)
            ):
                kinds = [item[0] for item in value]
                if new_kind not in kinds:
                    entries = list(value) + [(new_kind, 0)]
                    node[key] = tuple(
                        sorted(entries, key=lambda item: item[0])
                    )
            elif isinstance(value, (dict, list, tuple)):
                _patch_values(value, replacements, new_kind)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _patch_values(item, replacements, new_kind)


# --- bottom-up model rebuild ------------------------------------------------


def _dump_body(instance: object, digest_field: str) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dumped = instance.model_dump(mode="python")
    return {
        key: value for key, value in dumped.items() if key != digest_field
    }


def _graph_plane_digest(cls: type, values: dict, node: dict) -> tuple[str, str] | None:
    """Recompute the graph-plane digest models over serialized bodies."""

    from memorii.core.memory_evolution.graph_records import graph_digest

    shapes = (
        (
            {"read_set_digest", "record_keys", "partition_versions", "manifest_fingerprints"},
            "read_set_digest",
            b"memorii.graph-read-set.v1\0",
        ),
        (
            {"snapshot_digest", "exact_record_counts_by_kind", "records", "read_set"},
            "snapshot_digest",
            b"memorii.graph-state-snapshot.v1\0",
        ),
        (
            {"state_digest", "codec_manifest_fingerprint", "records",
             "applied_planned_delta_digests", "base_snapshot_digest"},
            "state_digest",
            b"memorii.graph-planning-state.v1\0",
        ),
    )
    for keys, digest_field, domain in shapes:
        if keys <= set(node):
            body = _dump_body(cls.model_construct(**values), digest_field)
            return digest_field, graph_digest(domain, body)
    return None


def _excluded_fields(cls: type, node: dict) -> frozenset:
    excluded = (
        _private_attr_default(cls, "_digest_excluded_fields") or frozenset()
    )
    versioned = getattr(cls, "_versioned_digest_excluded_fields", None)
    if callable(versioned):
        return excluded | cls._versioned_digest_excluded_fields(node)
    excluded = excluded | (
        _private_attr_default(cls, "_legacy_v1_digest_excluded_fields")
        or frozenset()
    )
    schema_1 = _private_attr_default(cls, "_schema_1_digest_excluded_fields")
    if schema_1 and node.get("source_result_schema_version", 1) == 1:
        return excluded | schema_1
    return excluded


def rebuild(node: dict, cls: type):
    """Recursively materialize the payload as models, bottom-up."""

    if not cls.__pydantic_complete__:
        cls.model_rebuild(raise_errors=False)
        if not cls.__pydantic_complete__:
            _modules()[0].rebuild_bootstrap_graph_effect_contracts()
        cls.model_rebuild(raise_errors=False)

    values: dict[str, object] = {}
    for name, field in cls.model_fields.items():
        if name not in node:
            continue
        value = node[name]
        annotation = _resolve_forward_ref(field.annotation)
        if isinstance(value, dict):
            if _candidate_classes(annotation, value):
                value = _rebuild_first(value, annotation)
        elif (
            isinstance(value, (list, tuple))
            and value
            and isinstance(value[0], dict)
        ):
            item_annotation = _unwrap(_resolve_forward_ref(annotation))
            origin = get_origin(item_annotation)
            args = get_args(item_annotation)
            if origin in (list, tuple) and args:
                item_annotation = args[0]
                value = type(value)(
                    _rebuild_first(item, item_annotation) for item in value
                )
        values[name] = value

    graph_plane = _graph_plane_digest(cls, values, node)
    if graph_plane is not None:
        values[graph_plane[0]] = graph_plane[1]

    if {"request_core_digest", "graph_authority", "schema_version"} <= set(node):
        # The coordinator request: subset core digest, authority replay pin,
        # and the initial control epoch that pins the core digest.
        core = {
            name: values.get(name)
            for name in (
                "schema_version", "normalization_replay", "source_alignment",
                "source_dependency_groups", "delivery_principal_binding_digest",
                "required_outcome_scopes", "graph_authority",
            )
            if name in values
        }
        replay_model = values.get("normalization_replay")
        authority_dict = node.get("graph_authority")
        if (
            replay_model is not None
            and isinstance(authority_dict, dict)
            and "normalization_replay_digest" in authority_dict
        ):
            authority_dict["normalization_replay_digest"] = (
                replay_model.replay_digest
            )
            authority_cls = _class_for_dict(
                _resolve_forward_ref(
                    cls.model_fields["graph_authority"].annotation
                ),
                authority_dict,
            )
            if authority_cls is not None:
                values["graph_authority"] = rebuild(authority_dict, authority_cls)
                core["graph_authority"] = values["graph_authority"]
        node["request_core_digest"] = _contract_digest(
            b"memorii.semantic-ingestion.bootstrap-graph-request-core.v3",
            core,
        )
        values["request_core_digest"] = node["request_core_digest"]
        epoch_dict = node.get("initial_control_epoch")
        if isinstance(epoch_dict, dict) and "request_core_digest" in epoch_dict:
            epoch_dict["request_core_digest"] = node["request_core_digest"]
            epoch_cls = _class_for_dict(
                _resolve_forward_ref(
                    cls.model_fields["initial_control_epoch"].annotation
                ),
                epoch_dict,
            )
            if epoch_cls is not None:
                values["initial_control_epoch"] = rebuild(epoch_dict, epoch_cls)

    if {
        "member_intents", "intent_digest", "locator_digest",
        "canonical_source_result_input_digest",
    } <= set(node):
        # The publication intent carries a second derived digest: the
        # locator binds the freshly recomputed intent digest. The base
        # generic block computes intent_digest; this block adds the locator
        # and keeps both consistent exactly as create() does.
        construct = cls.model_construct(**values)
        excluded = _excluded_fields(cls, node) | {"locator_digest"}
        body = {
            name: getattr(construct, name)
            for name in cls.model_fields
            if name != "intent_digest" and name not in excluded
        }
        intent_digest = _contract_digest(cls._digest_domain, body)
        values["intent_digest"] = intent_digest
        values["locator_digest"] = _contract_digest(
            b"memorii.semantic-ingestion.bootstrap-graph-terminal-publication-locator.v3",
            {"intent_digest": intent_digest},
        )

    if {
        "canonical_outcome_core", "completed_canonical_source_result",
        "ordered_group_result_constructions", "ordered_group_commit_reload_digests",
        "input_digest",
    } <= set(node):
        # The canonical input's record and core pin the constructions'
        # persisted result digests and reload digests; the constructions
        # above were rebuilt, so re-pin both holders and rebuild them.
        constructions = values.get("ordered_group_result_constructions") or ()
        if constructions:
            persisted = tuple(
                item.group_commit_reload.persisted_result.result_digest
                if (_MEMBER_SCHEMA_VERSION or node.get("schema_version")) == 3
                else item.result_digest
                for item in constructions
            )
            node["ordered_group_commit_reload_digests"] = tuple(
                item.group_commit_reload.reload_digest for item in constructions
            )
            values["ordered_group_commit_reload_digests"] = node[
                "ordered_group_commit_reload_digests"
            ]
            record_dict = node.get("completed_canonical_source_result")
            if isinstance(record_dict, dict) and "group_result_digests" in record_dict:
                record_dict["group_result_digests"] = persisted
                embedded = record_dict.get("core")
                if isinstance(embedded, dict) and "group_result_digests" in embedded:
                    embedded["group_result_digests"] = persisted
                record_cls = _class_for_dict(
                    _resolve_forward_ref(
                        cls.model_fields[
                            "completed_canonical_source_result"
                        ].annotation
                    ),
                    record_dict,
                )
                if record_cls is not None:
                    values["completed_canonical_source_result"] = rebuild(
                        record_dict, record_cls
                    )
            core_dict = node.get("canonical_outcome_core")
            if isinstance(core_dict, dict) and "group_result_digests" in core_dict:
                core_dict["group_result_digests"] = persisted
                core_cls = _class_for_dict(
                    _resolve_forward_ref(
                        cls.model_fields["canonical_outcome_core"].annotation
                    ),
                    core_dict,
                )
                if core_cls is not None:
                    values["canonical_outcome_core"] = rebuild(core_dict, core_cls)

    if {
        "group_plan_member", "planning_authorization", "group_commit_reload",
        "control_epoch", "attempt", "result_digest",
    } <= set(node):
        # Group-construction sibling pins: the authorization pins the
        # member digest, the attempt pins the epoch digest and the
        # coordinator's request digests, the lineage entry pins the
        # attempt's own digest, and the reload's successor generation pins
        # both epoch and request digests. The children above were rebuilt
        # with fresh digests, so re-pin and rebuild the holders before this
        # node's own digest is computed.
        attempt_dict = node.get("attempt")
        attempt_cls = _class_for_dict(
            _resolve_forward_ref(cls.model_fields["attempt"].annotation),
            attempt_dict,
        ) if isinstance(attempt_dict, dict) else None
        if attempt_cls is not None:
            values["attempt"] = rebuild(attempt_dict, attempt_cls)
        attempt_model = values.get("attempt")
        if attempt_model is not None:
            if "request_digest" in node:
                node["request_digest"] = attempt_model.request_digest
                values["request_digest"] = attempt_model.request_digest
            lineage_dict = node.get("source_plan_lineage_entry")
            if (
                isinstance(lineage_dict, dict)
                and "attempt_digest" in lineage_dict
            ):
                lineage_dict["attempt_digest"] = attempt_model.attempt_digest
                lineage_cls = _class_for_dict(
                    _resolve_forward_ref(
                        cls.model_fields["source_plan_lineage_entry"].annotation
                    ),
                    lineage_dict,
                )
                if lineage_cls is not None:
                    values["source_plan_lineage_entry"] = rebuild(
                        lineage_dict, lineage_cls
                    )
        member = values.get("group_plan_member")
        epoch = values.get("control_epoch")
        authorization_dict = node.get("planning_authorization")
        if (
            member is not None
            and isinstance(authorization_dict, dict)
            and "group_plan_member_digest" in authorization_dict
        ):
            authorization_dict["group_plan_member_digest"] = member.member_digest
            authorization_cls = _class_for_dict(
                _resolve_forward_ref(
                    cls.model_fields["planning_authorization"].annotation
                ),
                authorization_dict,
            )
            if authorization_cls is not None:
                values["planning_authorization"] = rebuild(
                    authorization_dict, authorization_cls
                )
        attempt_dict = node.get("attempt")
        if (
            epoch is not None
            and isinstance(attempt_dict, dict)
            and "control_epoch_digest" in attempt_dict
        ):
            attempt_dict["control_epoch_digest"] = epoch.epoch_digest
            attempt_cls = _class_for_dict(
                _resolve_forward_ref(cls.model_fields["attempt"].annotation),
                attempt_dict,
            )
            if attempt_cls is not None:
                values["attempt"] = rebuild(attempt_dict, attempt_cls)
            attempt_model = values.get("attempt")
            if attempt_model is not None:
                lineage_dict = node.get("source_plan_lineage_entry")
                if (
                    isinstance(lineage_dict, dict)
                    and "attempt_digest" in lineage_dict
                ):
                    lineage_dict["attempt_digest"] = attempt_model.attempt_digest
                    lineage_cls = _class_for_dict(
                        _resolve_forward_ref(
                            cls.model_fields["source_plan_lineage_entry"].annotation
                        ),
                        lineage_dict,
                    )
                    if lineage_cls is not None:
                        values["source_plan_lineage_entry"] = rebuild(
                            lineage_dict, lineage_cls
                        )
        reload_dict = node.get("group_commit_reload")
        if (
            epoch is not None
            and isinstance(reload_dict, dict)
            and isinstance(reload_dict.get("successor_generation"), dict)
        ):
            successor = reload_dict["successor_generation"]
            if "control_epoch_digest" in successor:
                successor["control_epoch_digest"] = epoch.epoch_digest
            if "request_digest" in successor and "request_digest" in node:
                successor["request_digest"] = node["request_digest"]
            reload_cls = _class_for_dict(
                _resolve_forward_ref(
                    cls.model_fields["group_commit_reload"].annotation
                ),
                reload_dict,
            )
            if reload_cls is not None:
                values["group_commit_reload"] = rebuild(reload_dict, reload_cls)

    if {"manifest_digest", "source_outcomes", "transaction_group_outcomes"} <= set(node):
        # The execution manifest's whole-body digest, and its identity
        # closure pin: the closure record's digest is recomputed as its own
        # model before the outer field is re-pinned.
        manifests = values.get("pre_execution_manifests")
        if manifests is not None and hasattr(manifests, "closure_digest"):
            node["pre_execution_manifest_identity_closure_digest"] = (
                manifests.closure_digest
            )
            values["pre_execution_manifest_identity_closure_digest"] = (
                manifests.closure_digest
            )
        manifest_construct = cls.model_construct(**values)
        values["manifest_digest"] = _contract_digest(
            b"memorii.semantic-ingestion.execution-manifest.v1",
            {
                name: getattr(manifest_construct, name)
                for name in cls.model_fields
                if name != "manifest_digest"
            },
        )

    digest_field = _private_attr_default(cls, "_digest_field")
    digest_domain = _private_attr_default(cls, "_digest_domain")
    if (
        isinstance(digest_field, str)
        and isinstance(digest_domain, bytes)
        and digest_field in node
    ):
        # The contract-digest preimage keeps children as live model
        # instances (lowered to canonical maps by the emitter itself), so
        # the body is taken from the constructed model's fields — exactly
        # as validate_content_digest does — never from a model_dump.
        construct = cls.model_construct(**values)
        excluded = _excluded_fields(cls, node)
        body = {
            name: getattr(construct, name)
            for name in cls.model_fields
            if name != digest_field and name not in excluded
        }
        values[digest_field] = _contract_digest(digest_domain, body)
    try:
        return cls.model_validate(values)
    except Exception:
        # Wire dicts carry JSON lists where strict models want tuples and
        # base64 text where they want bytes; the digest bodies are already
        # computed, so retry after coercing both.
        return cls.model_validate(
            _coerce_bytes(cls, _coerce_declared_tuples(cls, values))
        )


def _coerce_declared_tuples(cls: type, values: dict) -> dict:
    coerced = dict(values)
    for name, field in cls.model_fields.items():
        if name not in coerced:
            continue
        annotation = _unwrap(_resolve_forward_ref(field.annotation))
        if get_origin(annotation) is not tuple:
            continue
        value = coerced[name]
        if isinstance(value, list):
            value = tuple(value)
        if isinstance(value, tuple):
            coerced[name] = tuple(
                _coerce_declared_tuples_for_item(item) for item in value
            )
    return coerced


def _coerce_declared_tuples_for_item(item: object) -> object:
    if isinstance(item, dict):
        item_cls = _owner_by_field_set(item)
        if item_cls is not None:
            return _coerce_declared_tuples(item_cls, item)
        return {
            key: _coerce_declared_tuples_for_item(value)
            for key, value in item.items()
        }
    if isinstance(item, list):
        return tuple(_coerce_declared_tuples_for_item(i) for i in item)
    return item


def _coerce_bytes(cls: type, values: dict) -> dict:
    coerced = dict(values)
    for name, field in cls.model_fields.items():
        if name not in coerced:
            continue
        annotation = _unwrap(_resolve_forward_ref(field.annotation))
        if annotation is not bytes or not isinstance(coerced[name], str):
            continue
        coerced[name] = coerced[name].encode()
    return coerced


# --- sibling digest pinning -------------------------------------------------


def _construction_pins(construction: dict, epoch_digest: str, core_digest: str,
                       request_digest: str) -> None:
    for holder in (
        construction.get("attempt"),
        construction.get("control_epoch"),
    ):
        if isinstance(holder, dict):
            if "control_epoch_digest" in holder:
                holder["control_epoch_digest"] = epoch_digest
            if "request_core_digest" in holder:
                holder["request_core_digest"] = core_digest
            if "request_digest" in holder:
                holder["request_digest"] = request_digest
    reload_holder = construction.get("group_commit_reload")
    if isinstance(reload_holder, dict):
        successor = reload_holder.get("successor_generation")
        if isinstance(successor, dict):
            if "control_epoch_digest" in successor:
                successor["control_epoch_digest"] = epoch_digest
            if "request_digest" in successor:
                successor["request_digest"] = request_digest


def _scatter_coordinator_pins(patched: dict, root_class: type) -> None:
    """Rebuild the coordinator first, then scatter its digests."""

    coordinator_node = patched.get("coordinator_request")
    if not isinstance(coordinator_node, dict):
        return
    coordinator_cls = _class_for_dict(
        _resolve_forward_ref(
            root_class.model_fields["coordinator_request"].annotation
        ),
        coordinator_node,
    )
    if coordinator_cls is None:
        return
    coordinator = rebuild(coordinator_node, coordinator_cls)
    epoch_digest = coordinator.initial_control_epoch.epoch_digest
    core_digest = coordinator.request_core_digest
    request_digest = coordinator.request_digest

    root_epoch = patched.get("control_epoch")
    if isinstance(root_epoch, dict):
        if "request_core_digest" in root_epoch:
            root_epoch["request_core_digest"] = core_digest
        if "request_digest" in root_epoch:
            root_epoch["request_digest"] = request_digest
    attempt = patched.get("final_attempt")
    if isinstance(attempt, dict) and "control_epoch_digest" in attempt:
        attempt["control_epoch_digest"] = epoch_digest
    intent = patched.get("publication_intent")
    if isinstance(intent, dict) and "control_epoch_digest" in intent:
        intent["control_epoch_digest"] = epoch_digest
    for construction in patched.get(
        "ordered_group_result_constructions", ()
    ) or ():
        if isinstance(construction, dict):
            _construction_pins(construction, epoch_digest, core_digest, request_digest)
    inner = patched.get("canonical_source_result_input")
    if isinstance(inner, dict):
        if "request_digest" in inner:
            inner["request_digest"] = request_digest
        if "control_epoch_digest" in inner:
            inner["control_epoch_digest"] = epoch_digest
        if "normalization_replay_digest" in inner:
            replay = getattr(coordinator, "normalization_replay", None)
            if replay is not None:
                inner["normalization_replay_digest"] = replay.replay_digest
        for construction in inner.get(
            "ordered_group_result_constructions", ()
        ) or ():
            if isinstance(construction, dict):
                _construction_pins(construction, epoch_digest, core_digest, request_digest)
    predecessor = patched.get("predecessor_generation")
    if isinstance(predecessor, dict):
        if "request_digest" in predecessor:
            predecessor["request_digest"] = request_digest
        if "control_epoch_digest" in predecessor:
            predecessor["control_epoch_digest"] = epoch_digest


def _rebind_from_children(patched: dict, rebuilt: dict) -> None:
    """Copy rebuilt child digests into the sibling fields that pin them."""

    def pin(holder: object, field: str, value: object) -> None:
        if isinstance(holder, dict) and field in holder and value is not None:
            holder[field] = value

    final_plan = rebuilt.get("final_plan")
    lineage = rebuilt.get("complete_lineage")
    epoch = rebuilt.get("control_epoch")
    constructions = rebuilt.get("ordered_group_result_constructions") or ()

    handoff_core = patched.get("handoff_core")
    if isinstance(handoff_core, dict):
        if final_plan is not None:
            pin(handoff_core, "transaction_group_plan_digest",
                getattr(final_plan, "plan_digest", None))
        if lineage is not None:
            pin(handoff_core, "source_plan_lineage_digest",
                getattr(lineage, "lineage_digest", None))
    embedded = patched.get("handoff", {})
    if isinstance(embedded, dict) and isinstance(embedded.get("core"), dict):
        if final_plan is not None:
            pin(embedded["core"], "transaction_group_plan_digest",
                getattr(final_plan, "plan_digest", None))
        if lineage is not None:
            pin(embedded["core"], "source_plan_lineage_digest",
                getattr(lineage, "lineage_digest", None))

    canonical_input = patched.get("canonical_source_result_input")
    if isinstance(canonical_input, dict):
        inner_constructions = canonical_input.get(
            "ordered_group_result_constructions"
        )
        if isinstance(inner_constructions, (list, tuple)):
            digests = tuple(
                item.get("group_commit_reload", {})
                .get("persisted_result", {})
                .get("result_digest")
                for item in inner_constructions
                if isinstance(item, dict)
            )
            record = canonical_input.get("completed_canonical_source_result")
            if isinstance(record, dict):
                pin(record, "group_result_digests", digests)
                if isinstance(record.get("core"), dict):
                    pin(record["core"], "group_result_digests", digests)
            pin(
                canonical_input.get("canonical_outcome_core"),
                "group_result_digests",
                digests,
            )

    if constructions:
        patched["ordered_group_commit_reload_digests"] = tuple(
            item.group_commit_reload.reload_digest for item in constructions
        )
    if epoch is not None:
        pin(patched.get("publication_intent"), "control_epoch_digest",
            getattr(epoch, "epoch_digest", None))


def _rebind_publication_intent(
    patched: dict, root_class: type, rebuilt: dict
) -> None:
    """Re-pin the publication intent and its member intents, then rebuild.

    Each member intent pins the construction input digest of exactly one
    terminal member; after the root children rebuilt with fresh digests,
    every pin is refreshed, member digests recomputed, the intent rebuilt
    (intent + locator digests), and the handoff's embedded copies restored
    from the rebuilt intent.
    """

    intent_dict = patched.get("publication_intent")
    if not isinstance(intent_dict, dict):
        return
    intent_cls = _class_for_dict(
        _resolve_forward_ref(
            root_class.model_fields["publication_intent"].annotation
        ),
        intent_dict,
    )
    if intent_cls is None:
        return

    member_digest = {
        "bootstrap_graph_coordinator_request": getattr(
            rebuilt.get("coordinator_request"), "request_digest", None
        ),
        "bootstrap_graph_control_epoch": getattr(
            rebuilt.get("control_epoch"), "epoch_digest", None
        ),
        "bootstrap_graph_dependent_attempt": getattr(
            rebuilt.get("final_attempt"), "attempt_digest", None
        ),
        "bootstrap_transaction_group_plan": getattr(
            rebuilt.get("final_plan"), "plan_digest", None
        ),
        "bootstrap_source_plan_lineage_entry": getattr(
            rebuilt.get("complete_lineage"), "lineage_digest", None
        ),
        "ingestion_execution_manifest": getattr(
            rebuilt.get("execution_manifest"), "manifest_digest", None
        ),
        "bootstrap_graph_canonical_source_result": getattr(
            rebuilt.get("canonical_source_result_input"), "input_digest", None
        ),
    }
    for name, value in (
        ("request_digest", getattr(rebuilt.get("coordinator_request"), "request_digest", None)),
        ("normalization_replay_digest", getattr(
            getattr(rebuilt.get("coordinator_request"), "normalization_replay", None),
            "replay_digest", None,
        )),
        ("transaction_group_plan_digest", getattr(rebuilt.get("final_plan"), "plan_digest", None)),
        ("source_plan_lineage_digest", getattr(rebuilt.get("complete_lineage"), "lineage_digest", None)),
        ("control_epoch_digest", getattr(rebuilt.get("control_epoch"), "epoch_digest", None)),
        ("canonical_source_result_input_digest", getattr(
            rebuilt.get("canonical_source_result_input"), "input_digest", None
        )),
    ):
        if value is not None and name in intent_dict:
            intent_dict[name] = value

    member_cls = None
    for name, field in intent_cls.model_fields.items():
        if name == "member_intents":
            member_cls = _item_class(field.annotation, intent_dict["member_intents"][0])
            break
    if member_cls is not None:
        for member in intent_dict["member_intents"]:
            if not isinstance(member, dict):
                continue
            fresh = member_digest.get(member.get("kind"))
            if fresh is not None:
                member["construction_input_digest"] = fresh
            try:
                rebuilt_member = rebuild(member, member_cls)
                member.update(
                    {
                        "intent_member_digest": rebuilt_member.intent_member_digest,
                    }
                )
            except Exception:
                continue
    try:
        intent_model = rebuild(intent_dict, intent_cls)
    except Exception:
        return
    patched["publication_intent"] = intent_model
    handoff = patched.get("handoff")
    if isinstance(handoff, dict):
        handoff["publication_intent"] = deepcopy(intent_model)
        patched["handoff"] = handoff


# --- migration driver -------------------------------------------------------


def migrate(name: str, class_name: str) -> bool:
    from memorii.core.memory_evolution.ingestion_contracts import (
        decode_typed_value,
    )
    from memorii.core.semantic_ingestion.contracts import (
        restore_closed_wire_enums,
    )

    path = _FIXTURE_ROOT / f"{name}.gz"
    envelope = decode_typed_value(gzip.decompress(path.read_bytes()))
    payload = envelope["payload"]

    global _MEMBER_SCHEMA_VERSION
    replacements = _discover_replacements(payload)
    patched = deepcopy(payload)
    _patch_values(patched, replacements, _NEW_KIND)
    patched = restore_closed_wire_enums(patched)
    intent_probe = patched.get("publication_intent")
    _MEMBER_SCHEMA_VERSION = (
        intent_probe.get("terminal_member_schema_version")
        if isinstance(intent_probe, dict)
        else None
    )

    root_class = _model_class(class_name)
    _scatter_coordinator_pins(patched, root_class)

    rebuilt_children: dict[str, object] = {}
    for name_field, field in root_class.model_fields.items():
        if (
            name_field not in patched
            or name_field in (
                "coordinator_request", "handoff", "handoff_core",
                "publication_intent", "canonical_source_result_input",
                "source_finalization_observation_delta",
            )
        ):
            continue
        value = patched[name_field]
        annotation = _resolve_forward_ref(field.annotation)
        if isinstance(value, dict):
            child_cls = _class_for_dict(annotation, value)
            if child_cls is not None:
                rebuilt_children[name_field] = rebuild(value, child_cls)
        elif (
            isinstance(value, (list, tuple))
            and value
            and isinstance(value[0], dict)
        ):
            item_cls = _item_class(annotation, value[0])
            if item_cls is not None:
                rebuilt_children[name_field] = type(value)(
                    rebuild(item, item_cls) for item in value
                )

    for key, model in rebuilt_children.items():
        patched[key] = model
    _rebind_from_children(patched, rebuilt_children)

    # The handoff core and canonical record pin the group result digests:
    # schema v3 selects each construction's persisted result digest, and the
    # handoff core is rebuilt later, so pin both dict sites now from the
    # rebuilt constructions.
    constructions = rebuilt_children.get("ordered_group_result_constructions")
    if constructions:
        intent_dict = patched.get("publication_intent")
        member_schema = (
            intent_dict.get("terminal_member_schema_version")
            if isinstance(intent_dict, dict)
            else getattr(intent_dict, "terminal_member_schema_version", None)
        )
        persisted = tuple(
            item.group_commit_reload.persisted_result.result_digest
            if member_schema == 3
            else item.result_digest
            for item in constructions
        )
        handoff_core = patched.get("handoff_core")
        if (
            isinstance(handoff_core, dict)
            and "ordered_group_result_digests" in handoff_core
        ):
            handoff_core["ordered_group_result_digests"] = persisted
        canonical_input = patched.get("canonical_source_result_input")
        if not isinstance(canonical_input, dict):
            # Already a rebuilt model from the child pass; nothing to pin.
            canonical_input = None
        record = (
            canonical_input.get("completed_canonical_source_result")
            if canonical_input
            else None
        )
        if isinstance(record, dict) and "group_result_digests" in record:
            record["group_result_digests"] = persisted
            embedded = record.get("core")
            if isinstance(embedded, dict) and "group_result_digests" in embedded:
                embedded["group_result_digests"] = persisted
            core_outer = (
                canonical_input.get("canonical_outcome_core")
                if canonical_input
                else None
            )
            if isinstance(core_outer, dict) and "group_result_digests" in core_outer:
                core_outer["group_result_digests"] = persisted
        if canonical_input is not None:
            canonical_cls = _class_for_dict(
                _resolve_forward_ref(
                    root_class.model_fields[
                        "canonical_source_result_input"
                    ].annotation
                ),
                canonical_input,
            )
            if canonical_cls is not None:
                rebuilt_children["canonical_source_result_input"] = rebuild(
                    canonical_input, canonical_cls
                )

    if "canonical_source_result_input" in rebuilt_children:
        patched["canonical_source_result_input"] = rebuilt_children[
            "canonical_source_result_input"
        ]
        # The source finalization delta embeds an exact copy of the record;
        # refresh it from the rebuilt canonical input, then rebuild.
        delta_node = patched.get("source_finalization_observation_delta")
        if isinstance(delta_node, dict) and "source_outcome" in delta_node:
            record_model = deepcopy(
                rebuilt_children["canonical_source_result_input"]
                .completed_canonical_source_result
            )
            delta_node["source_outcome"] = record_model
            delta_cls = _class_for_dict(
                _resolve_forward_ref(
                    root_class.model_fields[
                        "source_finalization_observation_delta"
                    ].annotation
                ),
                delta_node,
            )
            if delta_cls is not None:
                try:
                    patched["source_finalization_observation_delta"] = (
                        rebuild(delta_node, delta_cls)
                    )
                except Exception:
                    pass
    _rebind_publication_intent(patched, root_class, rebuilt_children)

    # The coordinator model was built during scattering; restore it for the
    # root pass exactly as rebuilt.
    coordinator_node = patched.get("coordinator_request")
    if isinstance(coordinator_node, dict):
        coordinator_cls = _class_for_dict(
            _resolve_forward_ref(
                root_class.model_fields["coordinator_request"].annotation
            ),
            coordinator_node,
        )
        if coordinator_cls is not None:
            patched["coordinator_request"] = rebuild(
                coordinator_node, coordinator_cls
            )

    # The handoff core pins the plan and lineage digests, finalized only
    # above by the rebind; rebuild it from its dict, then pin the handoff's
    # embedded core copy and rebuild the handoff last so both carry the
    # final pins.
    handoff_core_node = patched.get("handoff_core")
    if isinstance(handoff_core_node, dict):
        handoff_core_cls = _class_for_dict(
            _resolve_forward_ref(
                root_class.model_fields["handoff_core"].annotation
            ),
            handoff_core_node,
        )
        if handoff_core_cls is not None:
            try:
                patched["handoff_core"] = rebuild(
                    handoff_core_node, handoff_core_cls
                )
            except Exception:
                pass
    handoff_node = patched.get("handoff")
    if isinstance(handoff_node, dict):
        embedded = handoff_node.get("core")
        if isinstance(embedded, dict):
            handoff_core_model = patched.get("handoff_core")
            for pin_field in (
                "transaction_group_plan_digest",
                "source_plan_lineage_digest",
                "ordered_group_result_digests",
            ):
                source = (
                    handoff_core_model.get(pin_field)
                    if isinstance(handoff_core_model, dict)
                    else getattr(handoff_core_model, pin_field, None)
                )
                if pin_field in embedded and source is not None:
                    embedded[pin_field] = source
        handoff_cls = _class_for_dict(
            _resolve_forward_ref(root_class.model_fields["handoff"].annotation),
            handoff_node,
        )
        if handoff_cls is not None:
            try:
                patched["handoff"] = rebuild(handoff_node, handoff_cls)
            except Exception:
                pass

    root = rebuild(patched, root_class)
    from memorii.core.semantic_ingestion.contracts import (
        encode_semantic_contract,
    )

    encoded = encode_semantic_contract(root)
    path.write_bytes(gzip.compress(encoded))

    global _ROOT_EXPORT
    if class_name == "BootstrapGraphTerminalPublicationRequestV3":
        _ROOT_EXPORT = {
            "handoff_digest": getattr(
                getattr(root, "handoff", None), "handoff_digest", None
            ),
            "canonical_source_result": None,
            "finalization_delta": None,
            "group_result_digests": tuple(
                item.group_commit_reload.persisted_result.result_digest
                if _MEMBER_SCHEMA_VERSION == 3
                else item.result_digest
                for item in root.ordered_group_result_constructions
            ),
            "control_epoch_digest": root.control_epoch.epoch_digest,
            "request_digest": root.coordinator_request.request_digest,
            "replay_digest": (
                root.coordinator_request.normalization_replay.replay_digest
            ),
            "lineage_digest": root.complete_lineage.lineage_digest,
        }
        recovery_record = getattr(root, "canonical_source_result_input", None)
        result_model = getattr(recovery_record, "completed_canonical_source_result", None)
        if result_model is not None:
            _ROOT_EXPORT["canonical_source_result"] = result_model
        _ROOT_EXPORT["finalization_delta"] = getattr(
            root, "source_finalization_observation_delta", None
        )
    return True


def migrate_memory_records() -> bool:
    """Migrate every embedded payload in the rehydrated-plane fixture.

    Bootstrap member records and both manifest shapes embed canonical
    payload envelopes pinning planning states, constructions, and per-kind
    counts. Each payload is decoded, fingerprint-patched, rebuilt through
    its owning model when one resolves (recomputing its internal digests),
    or re-encoded with value patches alone; the member-level payload and
    member digests are then recomputed from the new bytes and written to
    the stored record and every manifest copy symmetrically. The
    reference-integrity ledger record and the manifest request digests are
    refreshed afterwards.
    """

    import hashlib as _hashlib
    import json as _json

    from memorii.core.memory_evolution.ingestion_contracts import (
        decode_typed_value,
        encode_typed_value,
    )
    from memorii.core.semantic_ingestion.contracts import (
        restore_closed_wire_enums,
    )

    global _MEMBER_SCHEMA_VERSION
    records_path = _FIXTURE_ROOT / "memory-records.json.gz"
    if not records_path.is_file():
        return False
    records = _json.loads(gzip.decompress(records_path.read_bytes()).decode())
    compilation_cls = _model_class("BootstrapGraphPlanCompilationV3")
    migrated_members: dict[str, dict] = {}

    def migrate_member_payload(member: dict) -> bool:
        payload = member.get("canonical_payload")
        if not isinstance(payload, str):
            return False
        try:
            decoded = decode_typed_value(payload.encode())
            inner = decoded["payload"]
        except (ValueError, KeyError):
            return False
        if not isinstance(inner, dict):
            return False
        replacements = _discover_replacements(inner)
        counts_pinned = "exact_record_counts_by_kind" in _json.dumps(
            inner, default=lambda o: o.decode() if isinstance(o, bytes) else str(o)
        )
        if not replacements and not counts_pinned:
            return False
        patched = deepcopy(inner)
        _patch_values(patched, replacements or {}, _NEW_KIND)
        patched = restore_closed_wire_enums(patched)
        inner_cls = (
            compilation_cls
            if set(patched) == set(compilation_cls.model_fields)
            else _owner_by_field_set(patched)
        )
        if inner_cls is not None:
            try:
                model = rebuild(patched, inner_cls)
                import warnings as _warnings

                with _warnings.catch_warnings():
                    _warnings.simplefilter("ignore")
                    member_dump = model.model_dump(mode="python")
            except Exception:
                member_dump = patched
        else:
            member_dump = patched
        encoded = encode_typed_value(
            {
                "codec_key": decoded.get("codec_key"),
                "payload": member_dump,
                "schema": decoded.get("schema"),
            }
        )
        member["canonical_payload"] = encoded.decode()
        member["payload_digest"] = _hashlib.sha256(encoded).hexdigest()
        # The member digest preimage carries canonical_payload as BYTES
        # (the CTV emitter serializes bytes as base64, not as the raw
        # string), so the digest body must hold the encoded bytes.
        digest_body = {
            name: (
                member["canonical_payload"].encode()
                if name == "canonical_payload"
                else value
            )
            for name, value in member.items()
            if name != "member_digest"
        }
        member["member_digest"] = _contract_digest(
            b"memorii.semantic-ingestion.bootstrap-graph-plan-atomic-member.v3",
            digest_body,
        )
        return True

    for record in records:
        member = (record.get("content") or {}).get("member")
        if not isinstance(member, dict):
            continue
        if "canonical_payload" in member and migrate_member_payload(member):
            migrated_members[member.get("member_id", "")] = member

    # Refresh every manifest copy (request manifests and member manifests)
    # from the migrated members.
    for record in records:
        content = record.get("content") or {}
        holders = []
        request = content.get("request")
        if isinstance(request, dict) and "members" in request:
            holders.append(request)
        if "members" in content:
            holders.append(content)
        for holder in holders:
            for embedded in holder.get("members", ()) or ():
                if not isinstance(embedded, dict):
                    continue
                fresh = migrated_members.get(embedded.get("member_id", ""))
                if fresh is None:
                    continue
                embedded["canonical_payload"] = fresh["canonical_payload"]
                embedded["payload_digest"] = fresh["payload_digest"]
                embedded["member_digest"] = fresh["member_digest"]
            digest_list = holder.get("required_member_digests")
            if isinstance(digest_list, list):
                embedded_list = list(holder.get("members", ()) or ())
                holder["required_member_digests"] = [
                    migrated_members[m.get("member_id")]["member_digest"]
                    if m.get("member_id") in migrated_members
                    else digest
                    for m, digest in zip(embedded_list, digest_list, strict=False)
                ]
            holder_cls = _owner_by_field_set(holder)
            if holder_cls is not None:
                try:
                    holder_model = rebuild(holder, holder_cls)
                    for field in ("request_digest", "write_digest", "manifest_digest"):
                        if field in holder and hasattr(holder_model, field):
                            holder[field] = getattr(holder_model, field)
                except Exception:
                    pass

    # The reference-integrity ledger record pins the per-kind counts and
    # the reference manifest fingerprint; extend the counts with the new
    # kind's zero, refresh both fingerprints, and recompute the certificate
    # and ledger digests through the owning model.
    from memorii.core.memory_evolution.reference_integrity import (
        ReferenceAuditCertificate,
        ReferenceEdgeLedgerSnapshot,
        generated_reference_schema_manifest,
    )

    for record in records:
        content = record.get("content") or {}
        hex_value = content.get("canonical_hex")
        if (
            content.get("semantic_ingestion_kind")
            != "reference_integrity_ledger"
            or not isinstance(hex_value, str)
        ):
            continue
        snapshot = decode_typed_value(bytes.fromhex(hex_value))
        if not isinstance(snapshot, dict):
            continue
        snapshot["manifest_fingerprint"] = (
            generated_reference_schema_manifest().manifest_fingerprint
        )
        cert = snapshot.get("audit_certificate")
        if isinstance(cert, dict):
            cert["schema_manifest_fingerprint"] = (
                generated_reference_schema_manifest().manifest_fingerprint
            )
            counts = cert.get("base_record_counts_by_kind")
            if isinstance(counts, (list, tuple)):
                kinds = [item[0] for item in counts]
                if _NEW_KIND not in kinds:
                    cert["base_record_counts_by_kind"] = tuple(
                        sorted(list(counts) + [(_NEW_KIND, 0)], key=lambda i: i[0])
                    )
            digests = cert.get("base_record_digests_by_kind")
            if isinstance(digests, (list, tuple)):
                kind_names = [item[0] for item in digests]
                if _NEW_KIND not in kind_names:
                    from memorii.core.memory_evolution.reference_integrity import (
                        _digest as _ref_digest,
                    )

                    cert["base_record_digests_by_kind"] = tuple(
                        sorted(
                            list(digests)
                            + [(
                                _NEW_KIND,
                                _ref_digest(
                                    b"memorii.reference-audit-base-record-kind.v1\0",
                                    (),
                                ),
                            )],
                            key=lambda item: item[0],
                        )
                    )
            from memorii.core.memory_evolution.reference_integrity import (
                _digest as _ref_digest2,
            )

            identity_body = {
                key: value
                for key, value in cert.items()
                if key not in ("certificate_id", "certificate_digest")
            }
            cert["certificate_id"] = _ref_digest2(
                b"memorii.reference-audit-certificate-id.v1\0",
                identity_body,
            )
            digest_body = {
                key: value
                for key, value in cert.items()
                if key != "certificate_digest"
            }
            cert["certificate_digest"] = _ref_digest2(
                b"memorii.reference-audit-certificate.v1\0",
                digest_body,
            )
            rebuilt_cert = ReferenceAuditCertificate.model_validate(cert)
            snapshot["audit_certificate"] = rebuilt_cert
        from memorii.core.memory_evolution.reference_integrity import (
            _digest as _ledger_digest,
        )

        ledger_body = {
            key: value
            for key, value in snapshot.items()
            if key != "ledger_digest"
        }
        snapshot["ledger_digest"] = _ledger_digest(
            b"memorii.reference-edge-ledger-snapshot.v1\0", ledger_body
        )
        try:
            rebuilt_snapshot = ReferenceEdgeLedgerSnapshot.model_validate(
                snapshot
            )
        except Exception:
            import traceback as _tb

            print("ledger rebuild failed:", _tb.format_exc()[-260:])
            continue
        import warnings as _warnings2

        from memorii.core.memory_evolution.ingestion_contracts import (
            encode_typed_value as _encode,
        )

        with _warnings2.catch_warnings():
            _warnings2.simplefilter("ignore")
            snapshot_dump = rebuilt_snapshot.model_dump(mode="python")
        content["canonical_hex"] = _encode(snapshot_dump).hex()
        content["ledger_digest"] = rebuilt_snapshot.ledger_digest

    # The terminal-recovery record embeds the canonical source result and
    # the finalization delta and pins the handoff, epoch, request, replay,
    # and lineage digests — all freshly rebuilt in the .ctv migration.
    if _ROOT_EXPORT:
        reload_cls = _model_class("BootstrapGraphTerminalReloadV3")
        for record in records:
            content = record.get("content") or {}
            reload_value = content.get("reload")
            if not isinstance(reload_value, dict) or "reload_digest" not in reload_value:
                continue
            result_model = _ROOT_EXPORT.get("canonical_source_result")
            wrapper = reload_value.get("canonical_source_result")
            if (
                result_model is not None
                and isinstance(wrapper, dict)
                and "canonical_source_result" in wrapper
            ):
                # The reload embeds a canonical-source-result WRAPPER whose
                # inner record must equal the rebuilt root's record; patch
                # the record inside the existing wrapper, then rebuild the
                # wrapper through its own class so its result digest is
                # consistent.
                import warnings as _warnings4

                with _warnings4.catch_warnings():
                    _warnings4.simplefilter("ignore")
                    wrapper["canonical_source_result"] = (
                        result_model.model_dump(mode="python")
                    )
                wrapper_cls = _model_class(
                    "BootstrapGraphCanonicalSourceResultV3"
                )
                from memorii.core.semantic_ingestion.contracts import (
                    restore_closed_wire_enums as _restore,
                )

                wrapper = _restore(wrapper)
                wrapper["ordered_group_result_digests"] = list(
                    _ROOT_EXPORT.get("group_result_digests") or ()
                )
                for field, exported in (
                    ("request_digest", _ROOT_EXPORT.get("request_digest")),
                    ("normalization_replay_digest", _ROOT_EXPORT.get("replay_digest")),
                    ("source_plan_lineage_digest", _ROOT_EXPORT.get("lineage_digest")),
                    ("control_epoch_digest", _ROOT_EXPORT.get("control_epoch_digest")),
                ):
                    if exported is not None and field in wrapper:
                        wrapper[field] = exported
                try:
                    wrapper_model = rebuild(wrapper, wrapper_cls)
                    reload_value["canonical_source_result"] = wrapper_model
                except Exception:
                    reload_value["canonical_source_result"] = wrapper
            delta_model = _ROOT_EXPORT.get("finalization_delta")
            delta_field = reload_value.get("source_finalization_observation_delta")
            if delta_model is not None and isinstance(delta_field, dict):
                import warnings as _warnings5

                with _warnings5.catch_warnings():
                    _warnings5.simplefilter("ignore")
                    delta_field.clear()
                    delta_field.update(delta_model.model_dump(mode="python"))
            for field, exported in (
                ("handoff_digest", _ROOT_EXPORT.get("handoff_digest")),
                ("control_epoch_digest", _ROOT_EXPORT.get("control_epoch_digest")),
                ("request_digest", _ROOT_EXPORT.get("request_digest")),
                ("normalization_replay_digest", _ROOT_EXPORT.get("replay_digest")),
                ("source_plan_lineage_digest", _ROOT_EXPORT.get("lineage_digest")),
            ):
                if exported is not None and field in reload_value:
                    reload_value[field] = exported
            canonical = reload_value.get("canonical_source_result")
            if isinstance(canonical, dict):
                digests = _ROOT_EXPORT.get("group_result_digests")
                if digests and "ordered_group_result_digests" in canonical:
                    canonical["ordered_group_result_digests"] = list(digests)
            try:
                reload_model = rebuild(reload_value, reload_cls)
            except Exception:
                continue
            import warnings as _warnings3

            with _warnings3.catch_warnings():
                _warnings3.simplefilter("ignore")
                content["reload"] = reload_model.model_dump(mode="json")

    records_path.write_bytes(
        gzip.compress(_json.dumps(records, default=lambda o: o.decode() if isinstance(o, bytes) else str(o)).encode())
    )
    print("memory records migrated:", len(migrated_members))
    return True


def refresh_manifest() -> None:
    manifest_path = _FIXTURE_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["files"]:
        path = _FIXTURE_ROOT / entry["path"]
        if not path.is_file():
            continue
        raw = path.read_bytes()
        entry["sha256"] = hashlib.sha256(raw).hexdigest()
        try:
            entry["uncompressed_sha256"] = hashlib.sha256(
                gzip.decompress(raw)
            ).hexdigest()
        except (OSError, gzip.BadGzipFile):
            entry["uncompressed_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def main() -> int:
    migrated = [name for name, cls in _TARGETS.items() if migrate(name, cls)]
    migrate_memory_records()
    refresh_manifest()
    print("migrated:", migrated)
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
    if annotation.__class__ is Annotated:
        return get_args(annotation)[0]
    return annotation


def _resolve_forward_ref(annotation: object) -> object:
    if isinstance(annotation, str):
        return _lookup(annotation)
    if annotation.__class__ is Annotated:
        args = get_args(annotation)
        if args and isinstance(args[0], str):
            return Annotated[(_lookup(args[0]), *args[1:])]  # type: ignore[misc]
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


def _class_for_dict(annotation: object, data: dict) -> type | None:
    """Best-effort resolve of the model class a dict payload belongs to."""

    annotation = _unwrap(_resolve_forward_ref(annotation))
    if isinstance(annotation, type) and hasattr(annotation, "model_fields"):
        return annotation
    origin = get_origin(annotation)
    if origin in (list, tuple):
        args = get_args(annotation)
        if args:
            return _class_for_dict(args[0], data)
        return None
    if origin is Union:
        candidates = [
            arg
            for arg in get_args(annotation)
            if isinstance(arg, type) and hasattr(arg, "model_fields")
        ]
        matches = [
            candidate
            for candidate in candidates
            if set(data) <= set(candidate.model_fields)
        ]
        if not matches:
            matches = candidates
        exact = [c for c in matches if set(c.model_fields) == set(data)]
        if len(exact) == 1:
            return exact[0]
        discriminated = [c for c in (exact or matches) if _literal_accepts(c, data)]
        pool = discriminated or (exact or matches)
        if len(pool) == 1:
            return pool[0]
        if pool:
            return max(pool, key=lambda c: len(set(data) & set(c.model_fields)))
        return None
    return None


def _item_class(annotation: object, sample: dict) -> type | None:
    annotation = _unwrap(_resolve_forward_ref(annotation))
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (list, tuple) and args:
        return _class_for_dict(args[0], sample)
    return None


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
            child_cls = _class_for_dict(annotation, value)
            if child_cls is not None:
                value = rebuild(value, child_cls)
        elif (
            isinstance(value, (list, tuple))
            and value
            and isinstance(value[0], dict)
        ):
            item_cls = _item_class(annotation, value[0])
            if item_cls is not None:
                value = type(value)(
                    rebuild(item, item_cls) for item in value
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
        body = _dump_body(cls.model_construct(**values), "manifest_digest")
        values["manifest_digest"] = _contract_digest(
            b"memorii.semantic-ingestion.execution-manifest.v1", body
        )

    digest_field = _private_attr_default(cls, "_digest_field")
    digest_domain = _private_attr_default(cls, "_digest_domain")
    if (
        isinstance(digest_field, str)
        and isinstance(digest_domain, bytes)
        and digest_field in node
    ):
        body = _dump_body(cls.model_construct(**values), digest_field)
        excluded = _excluded_fields(cls, node)
        body = {
            key: value
            for key, value in body.items()
            if key not in excluded
        }
        values[digest_field] = _contract_digest(digest_domain, body)
    return cls.model_validate(values)


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


# --- migration driver -------------------------------------------------------


def migrate(name: str, class_name: str) -> bool:
    from memorii.core.memory_evolution.ingestion_contracts import (
        decode_typed_value,
        encode_typed_value,
    )
    from memorii.core.semantic_ingestion.contracts import (
        restore_closed_wire_enums,
    )

    path = _FIXTURE_ROOT / f"{name}.gz"
    envelope = decode_typed_value(gzip.decompress(path.read_bytes()))
    payload = envelope["payload"]

    replacements = _discover_replacements(payload)
    patched = deepcopy(payload)
    _patch_values(patched, replacements, _NEW_KIND)
    patched = restore_closed_wire_enums(patched)

    root_class = _model_class(class_name)
    _scatter_coordinator_pins(patched, root_class)

    rebuilt_children: dict[str, object] = {}
    for name_field, field in root_class.model_fields.items():
        if name_field not in patched or name_field == "coordinator_request":
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

    root = rebuild(patched, root_class)
    encoded = encode_typed_value(
        {"kind": envelope["kind"], "payload": root, "schema": envelope["schema"]}
    )
    path.write_bytes(gzip.compress(encoded))
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
    refresh_manifest()
    print("migrated:", migrated)
    return 0


if __name__ == "__main__":
    sys.exit(main())

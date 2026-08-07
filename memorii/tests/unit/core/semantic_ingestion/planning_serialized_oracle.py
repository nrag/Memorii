"""Independent primitive applicator for serialized graph-planning contracts."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value


def _digest(domain: bytes, value: object) -> str:
    return sha256(domain + encode_typed_value(value)).hexdigest()


def _key(record: dict) -> tuple[str, str]:
    payload = record["record"]["payload"]
    kind = (
        payload["record_kind"]
        if record["state_kind"] == "pending"
        else payload["record_kind"]
    )
    return kind, record["record"]["record_id"]


def _coordinate_group(value: dict) -> str:
    if set(value) != {"kind", "transaction_group_id", "coordinate"}:
        raise ValueError("planned_commit_coordinate_shape_invalid")
    if value["kind"] != "transaction_commit_coordinate" or value[
        "coordinate"
    ] not in {"graph_revision_before", "graph_revision_after", "committed_at"}:
        raise ValueError("planned_commit_coordinate_shape_invalid")
    group = value["transaction_group_id"]
    if not isinstance(group, str) or not group:
        raise ValueError("planned_commit_coordinate_shape_invalid")
    return group


def _coordinates(value: object) -> tuple[dict, ...]:
    found: list[dict] = []
    if isinstance(value, dict):
        if value.get("kind") == "transaction_commit_coordinate":
            _coordinate_group(value)
            found.append(value)
        else:
            for item in value.values():
                found.extend(_coordinates(item))
    elif isinstance(value, (tuple, list)):
        for item in value:
            found.extend(_coordinates(item))
    return tuple(found)


def apply_serialized(state: dict, delta: dict) -> dict:
    applied = tuple(state["applied_planned_delta_digests"])
    if delta["delta_digest"] in applied:
        raise ValueError("planning_delta_reapplied")
    if delta["sequence"] != len(applied) + 1:
        raise ValueError("planning_delta_prefix_skipped")
    if delta["base_state_digest"] != state["state_digest"]:
        raise ValueError("planning_delta_wrong_prefix")
    records = {_key(item): item for item in state["records"]}
    if tuple(records) != tuple(sorted(records)) or len(records) != len(state["records"]):
        raise ValueError("planning_state_records_not_canonical")
    for mutation in delta["mutations"]:
        key = (mutation["record_kind"], mutation["record_id"])
        current = records.get(key)
        before = mutation["before"]
        if before["kind"] == "absent":
            valid = current is None
        elif before["kind"] == "durable":
            valid = bool(
                current
                and current["state_kind"] == "durable"
                and current["record"]["record_version"] == before["record_version"]
                and current["record"]["record_digest"] == before["record_digest"]
            )
        elif before["kind"] == "pending":
            valid = bool(
                current
                and current["state_kind"] == "pending"
                and current["producing_transaction_group_id"]
                == before["producing_transaction_group_id"]
                and current["record"]["record_version"] == before["record_version"]
                and current["record"]["planning_record_digest"]
                == before["planning_record_digest"]
            )
        else:
            raise ValueError("planning_precondition_kind_unknown")
        if not valid:
            raise ValueError("planning_record_precondition_failed")
        after = mutation["after_planning_record"]
        if (
            after["record_id"] != mutation["record_id"]
            or after["payload"]["record_kind"] != mutation["record_kind"]
        ):
            raise ValueError("planning_mutation_record_binding_mismatch")
        planning_record = after["payload"]["planning_record"]
        if "record_digest" in planning_record:
            raise ValueError("planning_payload_prebound_record_digest")
        groups = {_coordinate_group(item) for item in _coordinates(planning_record)}
        if groups and groups != {delta["producing_transaction_group_id"]}:
            raise ValueError("planning_delta_producer_mismatch")
        records[key] = {
            "state_kind": "pending",
            "producing_transaction_group_id": delta[
                "producing_transaction_group_id"
            ],
            "record": after,
        }
    body = {
        "base_snapshot_digest": state["base_snapshot_digest"],
        "records": tuple(records[key] for key in sorted(records)),
        "codec_manifest_fingerprint": state["codec_manifest_fingerprint"],
        "applied_planned_delta_digests": applied + (delta["delta_digest"],),
    }
    return body | {
        "state_digest": _digest(b"memorii.graph-planning-state.v1\0", body)
    }


def materialize_serialized(
    state: dict,
    *,
    authorizing_group: str,
    commit_values: dict,
    durable_records: tuple[dict, ...],
) -> dict:
    supplied = {
        (item["payload"]["record_kind"], item["record_id"]): item
        for item in durable_records
    }
    expected: set[tuple[str, str]] = set()
    records = []
    for item in state["records"]:
        if item["state_kind"] == "durable":
            records.append(item)
            continue
        key = (item["record"]["payload"]["record_kind"], item["record"]["record_id"])
        if item["producing_transaction_group_id"] != authorizing_group:
            records.append(item)
            continue
        expected.add(key)
        durable = supplied.get(key)
        planned = deepcopy(item["record"]["payload"]["planning_record"])
        if commit_values["transaction_group_id"] != authorizing_group:
            raise ValueError("planning_commit_group_mismatch")
        declared = {
            "identity_lineage": (("transition.recorded_at", "committed_at"),),
            "temporal_transition": (("system_interval", "committed_at"),),
        }.get(planned["record_kind"], ())
        for path, coordinate_name in declared:
            container = planned
            parts = path.split(".")
            for part in parts[:-1]:
                container = container[part]
            coordinate = container[parts[-1]]
            if (
                _coordinate_group(coordinate) != authorizing_group
                or coordinate["coordinate"] != coordinate_name
            ):
                raise ValueError("planning_coordinate_authority_mismatch")
            replacement = commit_values[coordinate_name]
            if path == "system_interval":
                replacement = {"start": replacement, "end": None}
            container[parts[-1]] = replacement
        if planned["record_kind"] == "identity_lineage":
            transition = dict(planned["transition"])
            transition.pop("transition_digest", None)
            transition_digest = _digest(
                b"memorii.identity-lineage.transition.v1\0", transition
            )
            transition["transition_digest"] = transition_digest
            planned["transition"] = transition
            planned["statement_digest"] = transition_digest
        digest_domain = (
            b"memorii.semantic-ingestion.temporal-carrier.v1"
            if planned["record_kind"]
            in {
                "claim_assertion",
                "action_revision",
                "identity_lineage",
                "temporal_transition",
            }
            else b"memorii.canonical-graph-record.v1\0"
        )
        planned["record_digest"] = _digest(
            digest_domain
            + (
                b"\0"
                if planned["record_kind"]
                in {
                    "claim_assertion",
                    "action_revision",
                    "identity_lineage",
                    "temporal_transition",
                }
                else b""
            ),
            planned,
        )
        if (
            durable is None
            or durable["payload"] != planned
        ):
            differing = tuple(
                sorted(
                    field
                    for field in set(planned)
                    | (set(durable["payload"]) if durable is not None else set())
                    if durable is None
                    or planned.get(field) != durable["payload"].get(field)
                )
            )
            raise ValueError(
                "planning_materialization_projection_mismatch:"
                f"{key}:{differing}"
            )
        records.append({"state_kind": "durable", "record": durable})
    if set(supplied) != expected:
        raise ValueError("planning_materialization_group_scope_invalid")
    records.sort(key=_key)
    body = {
        "base_snapshot_digest": state["base_snapshot_digest"],
        "records": tuple(records),
        "codec_manifest_fingerprint": state["codec_manifest_fingerprint"],
        "applied_planned_delta_digests": tuple(
            state["applied_planned_delta_digests"]
        ),
    }
    return body | {
        "state_digest": _digest(b"memorii.graph-planning-state.v1\0", body)
    }

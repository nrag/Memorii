"""Full-fixture reference encoder with traversal-issued canonical member paths."""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import runpy
import threading
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel

from memorii.core.semantic_ingestion import contracts
from vcc_exp_001_member_span_inventory import JsonSpanScanner

PROFILE = "semantic-ingestion-canonical-profile-v1"
CODEC = "canonical-typed-value-v1"


def _json_scalar(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _shift(rows: list[dict[str, object]], amount: int) -> list[dict[str, object]]:
    return [row | {"begin": int(row["begin"]) + amount, "end": int(row["end"]) + amount} for row in rows]


def _emit(value: object, path: tuple[object, ...]) -> tuple[bytes, list[dict[str, object]]]:
    member_type: str | None = None
    if isinstance(value, BaseModel):
        member_type = f"{type(value).__module__}.{type(value).__qualname__}"
        value = {name: getattr(value, name) for name in type(value).model_fields}

    if value is None or isinstance(value, (bool, str)):
        raw, rows = _json_scalar(value), []
    elif isinstance(value, int):
        raw, rows = _json_scalar({"$type": "integer", "value": str(value)}), []
    elif isinstance(value, bytes):
        raw, rows = _json_scalar({"$type": "bytes", "value": base64.b64encode(value).decode("ascii")}), []
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("naive datetime")
        utc = value.astimezone(UTC)
        spelling = utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond:06d}Z"
        raw, rows = _json_scalar({"$type": "datetime", "value": spelling}), []
    elif isinstance(value, timedelta):
        micros = value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds
        raw, rows = _json_scalar({"$type": "duration_microseconds", "value": str(micros)}), []
    elif isinstance(value, Mapping):
        entries: list[bytes] = []
        rows = []
        prefix = b'{"$type":"map","entries":['
        position = len(prefix)
        for ordinal, key in enumerate(sorted(value, key=lambda item: _json_scalar(item))):
            if not isinstance(key, str):
                raise ValueError("non-string map key")
            child, child_rows = _emit(value[key], path + ("field", key))
            entry = b"[" + _json_scalar(key) + b"," + child + b"]"
            if ordinal:
                position += 1
            child_offset = position + 1 + len(_json_scalar(key)) + 1
            rows.extend(_shift(child_rows, child_offset))
            entries.append(entry)
            position += len(entry)
        raw = prefix + b",".join(entries) + b"]}"
    elif isinstance(value, (tuple, list)):
        tag = "tuple" if isinstance(value, tuple) else "list"
        prefix = b'{"$type":' + _json_scalar(tag) + b',"items":['
        parts: list[bytes] = []
        rows = []
        position = len(prefix)
        for index, item in enumerate(value):
            child, child_rows = _emit(item, path + ("index", index))
            if index:
                position += 1
            rows.extend(_shift(child_rows, position))
            parts.append(child)
            position += len(child)
        raw = prefix + b",".join(parts) + b"]}"
    elif isinstance(value, (set, frozenset)):
        tag = "frozenset" if isinstance(value, frozenset) else "set"
        encoded = []
        for item in value:
            child, child_rows = _emit(item, ())
            encoded.append((child, child_rows))
        encoded.sort(key=lambda item: item[0])
        if len({item[0] for item in encoded}) != len(encoded):
            raise ValueError("duplicate canonical set member")
        prefix = b'{"$type":' + _json_scalar(tag) + b',"items":['
        parts = []
        rows = []
        position = len(prefix)
        for index, (child, child_rows) in enumerate(encoded):
            if index:
                position += 1
            stable_path = path + ("set_member", index, sha256(child).hexdigest())
            for row in child_rows:
                relative = tuple(row["path"])
                rebound = row | {"path": list(stable_path + relative)}
                rows.extend(_shift([rebound], position))
            parts.append(child)
            position += len(child)
        raw = prefix + b",".join(parts) + b"]}"
    else:
        raise TypeError(f"unsupported CTV reference type: {type(value)!r}")

    if member_type is not None:
        rows.append({"path": list(path), "member_type": member_type, "begin": 0, "end": len(raw)})
    return raw, rows


def _canonical_contract(
    model: BaseModel,
) -> tuple[str, bytes, bytes, list[dict[str, object]], bool]:
    digest_field = getattr(type(model), "_digest_field", None)
    domain = getattr(type(model), "_digest_domain", None)
    if not isinstance(digest_field, str) or not isinstance(domain, bytes):
        raise LookupError("contract has no declared digest identity")
    validated_digest = getattr(model, digest_field, None)
    if not isinstance(validated_digest, str) or len(validated_digest) != 64:
        raise ValueError("contract validated digest is unavailable")
    body = {
        name: getattr(model, name)
        for name in type(model).model_fields
        if name != digest_field
    }
    digest_reference, _digest_rows = _emit(body, ())
    digest_production = contracts.encode_typed_value(contracts.canonical_contract_value(body))
    if digest_reference != digest_production:
        raise ValueError("reference digest-body bytes differ from production CTV")
    digest_preimage_verified = (
        sha256(domain + b"\0" + digest_production).hexdigest() == validated_digest
    )
    reference, rows = _emit(model, ())
    production = contracts.encode_typed_value(contracts.canonical_contract_value(model))
    if reference != production:
        raise ValueError("reference full-contract bytes differ from production CTV")
    return validated_digest, domain, production, rows, digest_preimage_verified


class Capture:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.local = threading.local()
        self.identities: dict[str, dict[str, object]] = {}
        self.failures: dict[str, list[str]] = {}
        self.inflight: set[str] = set()
        self.failed_identities: set[str] = set()
        self.constructions = 0

    def observe(self, model: BaseModel) -> None:
        if getattr(self.local, "active", False):
            return
        if type(model).__module__ != "memorii.core.semantic_ingestion.contracts":
            return
        digest_field = getattr(type(model), "_digest_field", None)
        if not isinstance(digest_field, str):
            return
        validated_digest = getattr(model, digest_field, None)
        if not isinstance(validated_digest, str) or len(validated_digest) != 64:
            return
        identity = f"{type(model).__module__}.{type(model).__qualname__}:{validated_digest}"
        with self.lock:
            self.constructions += 1
            if identity in self.identities or identity in self.inflight or identity in self.failed_identities:
                if identity in self.identities:
                    self.identities[identity]["occurrences"] = int(self.identities[identity]["occurrences"]) + 1
                return
            self.inflight.add(identity)
        self.local.active = True
        try:
            bound_digest, domain, production, rows, digest_preimage_verified = _canonical_contract(model)
            if bound_digest != validated_digest:
                raise ValueError("reserved identity changed during capture")
            scanner_spans = {(begin, end) for _path, begin, end in JsonSpanScanner(production).scan()}
            verified_rows = []
            for row in rows:
                begin, end = int(row["begin"]), int(row["end"])
                if (begin, end) not in scanner_spans:
                    raise ValueError("issued member span is not an independent JSON subtree")
                member_bytes = production[begin:end]
                verified_rows.append(row | {"member_sha256": sha256(member_bytes).hexdigest()})
            manifest_digest = sha256(
                json.dumps(verified_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            with self.lock:
                self.constructions += 1
                existing = self.identities.get(identity)
                if existing is None:
                    self.identities[identity] = {
                        "family": identity.rsplit(":", 1)[0],
                        "canonical_bytes": len(production),
                        "profile": PROFILE,
                        "codec": CODEC,
                        "digest_domain_sha256": sha256(domain).hexdigest(),
                        "generic_digest_preimage_verified": digest_preimage_verified,
                        "path_manifest_sha256": manifest_digest,
                        "member_paths": verified_rows,
                        "occurrences": 1,
                    }
        except LookupError:
            return
        except Exception as exc:
            key = f"{type(exc).__name__}:{exc}"
            with self.lock:
                self.failures.setdefault(identity, []).append(key)
                self.failed_identities.add(identity)
        finally:
            with self.lock:
                self.inflight.discard(identity)
            self.local.active = False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    frozen_document = json.loads(args.census.read_text())
    frozen = frozen_document["census"]["identities"]
    namespace = runpy.run_path(str(args.harness), run_name="vcc_full_reference")
    capture = Capture()
    original_init = BaseModel.__init__

    def observed_init(self: BaseModel, /, **data: Any) -> None:
        original_init(self, **data)
        capture.observe(self)

    BaseModel.__init__ = observed_init
    try:
        child_output = Path("/tmp/vcc-exp-001b-frozen-child-output.json")
        with child_output.open("w") as stream, contextlib.redirect_stdout(stream):
            try:
                execution = namespace["_child"](
                    "safe_reference", trace_only=True, trace_validation_floor=True
                )
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    raise
                execution = None
    finally:
        BaseModel.__init__ = original_init

    observed = capture.identities
    frozen_keys, observed_keys = set(frozen), set(observed)
    matched = frozen_keys & observed_keys
    missing = frozen_keys - observed_keys
    extra = observed_keys - frozen_keys
    byte_size_mismatches = sorted(
        key for key in matched if frozen[key]["canonical_bytes"] != observed[key]["canonical_bytes"]
    )
    path_rows = [row for identity in observed.values() for row in identity["member_paths"]]
    specialized_digest_identities = sorted(
        key
        for key, identity in observed.items()
        if not identity["generic_digest_preimage_verified"]
    )
    duplicate_issued_paths = sum(
        len(rows) - len({tuple(row["path"]) for row in rows})
        for rows in (identity["member_paths"] for identity in observed.values())
    )
    passed = (
        len(frozen_keys) == 238
        and not missing
        and not extra
        and not byte_size_mismatches
        and not capture.failures
        and duplicate_issued_paths == 0
    )
    output = {
        "schema": "memorii.semantic-ingestion.vcc-exp-001b.v1",
        "experiment": "VCC-EXP-001B",
        "evidence_stage": "reference_only_full_production_fixture",
        "production_implementation_changed": False,
        "tests_changed": False,
        "frozen_census_sha256": sha256(args.census.read_bytes()).hexdigest(),
        "harness_sha256": sha256(args.harness.read_bytes()).hexdigest(),
        "reconciliation": {
            "frozen_identities": len(frozen_keys),
            "observed_identities": len(observed_keys),
            "matched_identities": len(matched),
            "missing_identities": len(missing),
            "extra_identities": len(extra),
            "byte_size_mismatches": len(byte_size_mismatches),
            "missing_by_family": _counts(frozen[key]["family"] for key in missing),
            "extra_by_family": _counts(observed[key]["family"] for key in extra),
        },
        "path_proof": {
            "captured_constructions": capture.constructions,
            "member_paths": len(path_rows),
            "duplicate_issued_paths": duplicate_issued_paths,
            "reference_or_span_failures": capture.failures,
            "all_roots_byte_identical_to_production": not capture.failures,
            "all_issued_spans_independently_verified": not capture.failures,
            "generic_digest_preimage_verified_identities": len(observed) - len(specialized_digest_identities),
            "specialized_digest_identities": specialized_digest_identities,
        },
        "execution_result": "completed" if execution is None else type(execution).__name__,
        "passed": passed,
        "decision": (
            "traversal-issued exact member paths are feasible for the frozen full identity set"
            if passed else
            "full-fixture traversal inventory did not reconcile the frozen identity set"
        ),
        "identities": dict(sorted(observed.items())),
    }
    encoded = json.dumps(output, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    args.output.write_bytes(encoded)
    print(json.dumps({
        "passed": passed,
        **output["reconciliation"],
        **output["path_proof"],
        "output_sha256": sha256(encoded).hexdigest(),
    }, sort_keys=True))
    return 0 if passed else 2


def _counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


if __name__ == "__main__":
    raise SystemExit(main())

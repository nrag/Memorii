"""Reference-only security and capacity attacks for validated canonical closure."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from vcc_exp_001_member_span_inventory import JsonSpanScanner

MAX_ROOTS = 512
MAX_ROOT_BYTES = 2 * 1024 * 1024
MAX_MEMBER_PATHS = 32_768
MAX_OPERATION_CHARGED_BYTES = 16 * 1024 * 1024
MAX_PROCESS_RESERVED_BYTES = 64 * 1024 * 1024
PATH_BASE_CHARGE = 96


@dataclass
class Scope:
    operation: str
    generation: int
    fence: str
    capability: object
    active: bool = True


@dataclass(frozen=True)
class Entry:
    path: tuple[object, ...]
    begin: int
    end: int
    member_bytes: bytes
    member_type: str


@dataclass(frozen=True)
class Proof:
    scope: Scope
    capability: object
    operation: str
    generation: int
    fence: str
    writer: str | None
    concrete_type: str
    domain: bytes
    profile: str
    codec: str
    root_bytes: bytes
    root_sha256: str
    entries: tuple[Entry, ...]
    completed_stages: frozenset[str]


@dataclass(frozen=True)
class Request:
    scope: Scope
    writer: str | None
    concrete_type: str
    domain: bytes
    profile: str
    codec: str
    root_bytes: bytes
    path: tuple[object, ...]
    member_bytes: bytes
    required_stage: str


def _prefix(left: tuple[object, ...], right: tuple[object, ...]) -> bool:
    return len(left) <= len(right) and left == right[: len(left)]


def _verify_index(root: bytes, entries: tuple[Entry, ...]) -> tuple[bool, str]:
    seen_paths: set[tuple[object, ...]] = set()
    scanner_spans = {(begin, end) for _path, begin, end in JsonSpanScanner(root).scan()}
    for index, entry in enumerate(entries):
        if entry.path in seen_paths:
            return False, "duplicate_path"
        seen_paths.add(entry.path)
        if entry.begin < 0 or entry.end <= entry.begin or entry.end > len(root):
            return False, "span_bounds"
        if (entry.begin, entry.end) not in scanner_spans:
            return False, "span_not_canonical_subtree"
        if root[entry.begin : entry.end] != entry.member_bytes:
            return False, "member_bytes_mismatch"
        for sibling in entries[:index]:
            overlaps = entry.begin < sibling.end and sibling.begin < entry.end
            related = _prefix(entry.path, sibling.path) or _prefix(sibling.path, entry.path)
            if overlaps and not related:
                return False, "unrelated_span_overlap"
    return True, "valid"


def verify(proof: Proof, request: Request) -> tuple[bool, str]:
    if not proof.scope.active or not request.scope.active:
        return False, "scope_closed"
    if proof.scope is not request.scope or proof.capability is not request.scope.capability:
        return False, "foreign_capability"
    if (
        proof.operation != request.scope.operation
        or proof.generation != request.scope.generation
        or proof.fence != request.scope.fence
    ):
        return False, "stale_scope_binding"
    if proof.writer != request.writer:
        return False, "writer_scope_mismatch"
    if proof.concrete_type != request.concrete_type:
        return False, "type_mismatch"
    if proof.domain != request.domain:
        return False, "domain_mismatch"
    if proof.profile != request.profile:
        return False, "profile_mismatch"
    if proof.codec != request.codec:
        return False, "codec_mismatch"
    if proof.root_bytes != request.root_bytes:
        return False, "root_bytes_mismatch"
    if sha256(proof.root_bytes).hexdigest() != proof.root_sha256:
        return False, "root_digest_mismatch"
    valid, reason = _verify_index(proof.root_bytes, proof.entries)
    if not valid:
        return False, reason
    if request.required_stage not in proof.completed_stages:
        return False, "stage_missing"
    matches = [entry for entry in proof.entries if entry.path == request.path]
    if len(matches) != 1:
        return False, "path_mismatch"
    if matches[0].member_bytes != request.member_bytes:
        return False, "requested_member_mismatch"
    return True, "accepted"


class Arena:
    def __init__(self) -> None:
        self.roots = 0
        self.paths = 0
        self.charged_bytes = 0
        self.fallbacks = 0
        self.closed = False

    def admit(self, *, root_bytes: int, paths: int, metadata_bytes: int) -> tuple[bool, str]:
        if self.closed:
            self.fallbacks += 1
            return False, "closed_fallback"
        charge = root_bytes + metadata_bytes
        if root_bytes > MAX_ROOT_BYTES:
            self.fallbacks += 1
            return False, "root_limit_fallback"
        if self.roots + 1 > MAX_ROOTS:
            self.fallbacks += 1
            return False, "root_count_fallback"
        if self.paths + paths > MAX_MEMBER_PATHS:
            self.fallbacks += 1
            return False, "path_count_fallback"
        if self.charged_bytes + charge > MAX_OPERATION_CHARGED_BYTES:
            self.fallbacks += 1
            return False, "operation_bytes_fallback"
        self.roots += 1
        self.paths += paths
        self.charged_bytes += charge
        return True, "admitted"

    def close(self) -> None:
        self.roots = 0
        self.paths = 0
        self.charged_bytes = 0
        self.closed = True


class ProcessReservations:
    def __init__(self) -> None:
        self.reserved = 0

    def acquire(self) -> bool:
        if self.reserved + MAX_OPERATION_CHARGED_BYTES > MAX_PROCESS_RESERVED_BYTES:
            return False
        self.reserved += MAX_OPERATION_CHARGED_BYTES
        return True

    def release(self) -> None:
        if self.reserved < MAX_OPERATION_CHARGED_BYTES:
            raise RuntimeError("reservation underflow")
        self.reserved -= MAX_OPERATION_CHARGED_BYTES


def _path_charge(row: dict[str, Any]) -> int:
    path_bytes = len(json.dumps(row["path"], sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return PATH_BASE_CHARGE + path_bytes + len(row["member_type"].encode("utf-8"))


def _cell(name: str, actual: tuple[bool, str], expected: tuple[bool, str]) -> dict[str, Any]:
    return {
        "name": name,
        "accepted": actual[0],
        "reason": actual[1],
        "expected_accepted": expected[0],
        "expected_reason": expected[1],
        "passed": actual == expected,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path-proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path_document = json.loads(args.path_proof.read_text())

    root = encode_typed_value({"a": "alpha", "b": "beta"})
    spans = JsonSpanScanner(root).scan()
    alpha = next((begin, end) for _path, begin, end in spans if root[begin:end] == b'"alpha"')
    beta = next((begin, end) for _path, begin, end in spans if root[begin:end] == b'"beta"')
    scope = Scope("operation-a", 7, "fence-a", object())
    alpha_entry = Entry(("field", "a"), *alpha, b'"alpha"', "builtins.str")
    beta_entry = Entry(("field", "b"), *beta, b'"beta"', "builtins.str")
    proof = Proof(
        scope=scope,
        capability=scope.capability,
        operation=scope.operation,
        generation=scope.generation,
        fence=scope.fence,
        writer=None,
        concrete_type="ExampleContract",
        domain=b"example-domain-v1",
        profile="semantic-ingestion-canonical-profile-v1",
        codec="canonical-typed-value-v1",
        root_bytes=root,
        root_sha256=sha256(root).hexdigest(),
        entries=(alpha_entry, beta_entry),
        completed_stages=frozenset({"canonical", "semantic"}),
    )
    request = Request(
        scope=scope,
        writer=None,
        concrete_type=proof.concrete_type,
        domain=proof.domain,
        profile=proof.profile,
        codec=proof.codec,
        root_bytes=root,
        path=alpha_entry.path,
        member_bytes=alpha_entry.member_bytes,
        required_stage="semantic",
    )
    other_scope = Scope("operation-b", 7, "fence-a", object())
    closed_scope = Scope("operation-a", 7, "fence-a", object(), active=False)
    altered_root = root.replace(b"alpha", b"omega")
    overlap = replace(beta_entry, begin=alpha_entry.begin, end=alpha_entry.end, member_bytes=alpha_entry.member_bytes)

    cells = [
        _cell("valid_control", verify(proof, request), (True, "accepted")),
        _cell("substituted_root_bytes", verify(proof, replace(request, root_bytes=altered_root)), (False, "root_bytes_mismatch")),
        _cell("stale_claimed_root_digest", verify(replace(proof, root_bytes=altered_root), replace(request, root_bytes=altered_root)), (False, "root_digest_mismatch")),
        _cell("wrong_type", verify(proof, replace(request, concrete_type="OtherContract")), (False, "type_mismatch")),
        _cell("wrong_domain", verify(proof, replace(request, domain=b"other-domain")), (False, "domain_mismatch")),
        _cell("wrong_profile", verify(proof, replace(request, profile="profile-v2")), (False, "profile_mismatch")),
        _cell("wrong_codec", verify(proof, replace(request, codec="codec-v2")), (False, "codec_mismatch")),
        _cell("wrong_path", verify(proof, replace(request, path=("field", "missing"))), (False, "path_mismatch")),
        _cell("wrong_member_bytes", verify(proof, replace(request, member_bytes=b'"beta"')), (False, "requested_member_mismatch")),
        _cell("foreign_operation", verify(proof, replace(request, scope=other_scope)), (False, "foreign_capability")),
        _cell("forged_capability", verify(replace(proof, capability=object()), request), (False, "foreign_capability")),
        _cell("stale_generation", verify(replace(proof, generation=6), request), (False, "stale_scope_binding")),
        _cell("wrong_fence", verify(replace(proof, fence="fence-old"), request), (False, "stale_scope_binding")),
        _cell("closed_scope", verify(replace(proof, scope=closed_scope, capability=closed_scope.capability), replace(request, scope=closed_scope)), (False, "scope_closed")),
        _cell("missing_stage", verify(proof, replace(request, required_stage="writer_admission")), (False, "stage_missing")),
        _cell("malformed_span", verify(replace(proof, entries=(replace(alpha_entry, begin=-1), beta_entry)), request), (False, "span_bounds")),
        _cell("non_subtree_span", verify(replace(proof, entries=(replace(alpha_entry, end=alpha_entry.end + 1, member_bytes=root[alpha_entry.begin:alpha_entry.end + 1]), beta_entry)), request), (False, "span_not_canonical_subtree")),
        _cell("member_slice_substitution", verify(replace(proof, entries=(replace(alpha_entry, member_bytes=b'"omega"'), beta_entry)), request), (False, "member_bytes_mismatch")),
        _cell("duplicate_path", verify(replace(proof, entries=(alpha_entry, replace(beta_entry, path=alpha_entry.path))), request), (False, "duplicate_path")),
        _cell("unrelated_overlap", verify(replace(proof, entries=(alpha_entry, overlap)), request), (False, "unrelated_span_overlap")),
        _cell("writer_scope_required", verify(proof, replace(request, writer="writer-a")), (False, "writer_scope_mismatch")),
        _cell("cross_writer_reuse", verify(replace(proof, writer="writer-a"), replace(request, writer="writer-b")), (False, "writer_scope_mismatch")),
        _cell("concurrent_operation_isolation", verify(proof, replace(request, scope=Scope("operation-a", 7, "fence-a", object()))), (False, "foreign_capability")),
    ]

    identities = path_document["identities"]
    measured_roots = len(identities)
    measured_paths = sum(len(row["member_paths"]) for row in identities.values())
    measured_root_bytes = sum(int(row["canonical_bytes"]) for row in identities.values())
    measured_max_root = max(int(row["canonical_bytes"]) for row in identities.values())
    measured_metadata = sum(
        _path_charge(path)
        for identity in identities.values()
        for path in identity["member_paths"]
    )
    measured_charge = measured_root_bytes + measured_metadata
    arena = Arena()
    corpus_fit, corpus_reason = True, "admitted"
    for identity in identities.values():
        identity_paths = identity["member_paths"]
        accepted, reason = arena.admit(
            root_bytes=int(identity["canonical_bytes"]),
            paths=len(identity_paths),
            metadata_bytes=sum(_path_charge(path) for path in identity_paths),
        )
        if not accepted:
            corpus_fit, corpus_reason = False, reason
            break
    capacity_cells = [
        _cell("measured_corpus_fit", (corpus_fit, corpus_reason), (True, "admitted")),
    ]

    root_limit = Arena()
    before = (root_limit.roots, root_limit.paths, root_limit.charged_bytes)
    rejected = root_limit.admit(root_bytes=MAX_ROOT_BYTES + 1, paths=1, metadata_bytes=PATH_BASE_CHARGE)
    capacity_cells.append(_cell("root_byte_limit", rejected, (False, "root_limit_fallback")))
    capacity_cells.append(_cell("root_limit_no_eviction", ((root_limit.roots, root_limit.paths, root_limit.charged_bytes) == before, "unchanged"), (True, "unchanged")))

    root_count = Arena()
    for _ in range(MAX_ROOTS):
        accepted, _reason = root_count.admit(root_bytes=1, paths=0, metadata_bytes=0)
        if not accepted:
            raise RuntimeError("root-count setup failed")
    capacity_cells.append(_cell("root_count_limit", root_count.admit(root_bytes=1, paths=0, metadata_bytes=0), (False, "root_count_fallback")))

    path_limit = Arena()
    capacity_cells.append(_cell("path_count_limit", path_limit.admit(root_bytes=1, paths=MAX_MEMBER_PATHS + 1, metadata_bytes=0), (False, "path_count_fallback")))
    operation_limit = Arena()
    capacity_cells.append(_cell("operation_byte_limit", operation_limit.admit(root_bytes=1, paths=0, metadata_bytes=MAX_OPERATION_CHARGED_BYTES), (False, "operation_bytes_fallback")))

    reservations = ProcessReservations()
    first_four = [reservations.acquire() for _ in range(4)]
    fifth = reservations.acquire()
    capacity_cells.append(_cell("process_four_operation_limit", (all(first_four) and not fifth, "bounded"), (True, "bounded")))
    for _ in range(4):
        reservations.release()
    capacity_cells.append(_cell("process_reservations_released", (reservations.reserved == 0, "released"), (True, "released")))

    arena.close()
    capacity_cells.append(_cell("scope_close_clears_entries", ((arena.roots, arena.paths, arena.charged_bytes) == (0, 0, 0), "cleared"), (True, "cleared")))
    capacity_cells.append(_cell("closed_scope_fallback", arena.admit(root_bytes=1, paths=1, metadata_bytes=1), (False, "closed_fallback")))

    all_cells = cells + capacity_cells
    passed = all(cell["passed"] for cell in all_cells)
    output = {
        "schema": "memorii.semantic-ingestion.vcc-exp-003.v1",
        "experiment": "VCC-EXP-003",
        "evidence_stage": "reference_only_security_capacity_attacks",
        "production_implementation_changed": False,
        "tests_changed": False,
        "certifies_m3_1": False,
        "path_proof_sha256": sha256(args.path_proof.read_bytes()).hexdigest(),
        "limits": {
            "maximum_roots": MAX_ROOTS,
            "maximum_root_bytes": MAX_ROOT_BYTES,
            "maximum_member_paths": MAX_MEMBER_PATHS,
            "maximum_operation_charged_bytes": MAX_OPERATION_CHARGED_BYTES,
            "maximum_process_reserved_bytes": MAX_PROCESS_RESERVED_BYTES,
            "path_base_charge": PATH_BASE_CHARGE,
        },
        "measured_corpus": {
            "roots": measured_roots,
            "member_paths": measured_paths,
            "root_bytes": measured_root_bytes,
            "maximum_root_bytes": measured_max_root,
            "metadata_charge": measured_metadata,
            "operation_charge": measured_charge,
            "operation_headroom_bytes": MAX_OPERATION_CHARGED_BYTES - measured_charge,
        },
        "authority_and_scope_cells": cells,
        "capacity_cells": capacity_cells,
        "passed_cells": sum(cell["passed"] for cell in all_cells),
        "total_cells": len(all_cells),
        "passed": passed,
        "decision": (
            "all invalid evidence fails closed and the full measured corpus fits deterministic limits"
            if passed else
            "security or capacity attack matrix has a failing cell"
        ),
    }
    encoded = json.dumps(output, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    args.output.write_bytes(encoded)
    print(json.dumps({
        "passed": passed,
        "passed_cells": output["passed_cells"],
        "total_cells": output["total_cells"],
        "measured_corpus": output["measured_corpus"],
        "limits": output["limits"],
        "failed_cells": [cell for cell in all_cells if not cell["passed"]],
        "output_sha256": sha256(encoded).hexdigest(),
    }, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

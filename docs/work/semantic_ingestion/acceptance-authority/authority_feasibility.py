"""Bounded nonproduction model of the proposed SIA approval authority."""

from __future__ import annotations
import base64
import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PROFILE = "memorii.acceptance.ed25519.rfc8032.v1"
APPROVAL_PURPOSE = "semantic_ingestion_capability_baseline_approval"
STATUS_PURPOSE = "semantic_ingestion_capability_baseline_current_status"
RECEIPT_PURPOSE = "semantic_ingestion_capability_baseline_production_revocation"
BINDING = "sia.acceptance.authority.feasibility.v2"
RELEASE_DOMAIN = "memorii:sia-capability-baseline-approval-release:v1\\0"
SNAPSHOT_DOMAIN = "memorii:sia-capability-baseline-approval-snapshot:v1\\0"
KEY_DOMAIN = "memorii:sia-capability-baseline-approval-key-status:v1\\0"
CHECKPOINT_DOMAIN = "memorii:sia-capability-baseline-approval-status-checkpoint:v1\\0"
RECEIPT_DOMAIN = "memorii:sia-capability-baseline-approval-revocation-receipt:v1\\0"


class AuthorityRejected(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    max_input_bytes: int
    max_depth: int
    max_nodes: int
    max_string_bytes: int
    max_integer_digits: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise AuthorityRejected("bootstrap_limits")
        if self.max_depth > 64:
            raise AuthorityRejected("bootstrap_depth_configuration")


@dataclass(frozen=True)
class SignedBody:
    purpose: str
    coordinate: dict[str, str]
    body: dict[str, Any]
    digest: str
    signature: str


@dataclass(frozen=True)
class Pointer:
    body: dict[str, Any]
    digest: str


@dataclass(frozen=True)
class TrustAnchor:
    status_coordinate: dict[str, str]
    status_public_key: Ed25519PublicKey
    receipt_coordinate: dict[str, str]
    receipt_public_key: Ed25519PublicKey


def _string(v: str) -> bytes:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":")).encode()


def _ctv(v: Any) -> bytes:
    if v is None:
        return b"null"
    if type(v) is bool:
        return b"true" if v else b"false"
    if type(v) is int:
        return b'{"$type":"integer","value":"' + str(v).encode() + b'"}'
    if type(v) is str:
        return _string(v)
    if type(v) is bytes:
        return b'{"$type":"bytes","value":"' + base64.b64encode(v) + b'"}'
    if type(v) in (list, tuple):
        return (
            b'{"$type":"'
            + (b"list" if type(v) is list else b"tuple")
            + b'","items":['
            + b",".join(_ctv(x) for x in v)
            + b"]}"
        )
    if type(v) is dict and all(type(k) is str for k in v):
        return (
            b'{"$type":"map","entries":['
            + b",".join(
                b"[" + _ctv(k) + b"," + _ctv(x) + b"]"
                for k, x in sorted(v.items(), key=lambda x: _string(x[0]))
            )
            + b"]}"
        )
    raise AuthorityRejected("ctv_value")


def _lp(*p: bytes) -> bytes:
    return b"".join(len(x).to_bytes(8, "big") + x for x in p)


def _digest(domain: str, body: dict[str, Any]) -> str:
    return sha256(_lp(domain.encode(), BINDING.encode(), _ctv(body))).hexdigest()


def _message(
    purpose: str, coordinate: dict[str, str], body: dict[str, Any], digest: str
) -> bytes:
    return _ctv(
        {
            "purpose": purpose,
            "complete_binding": BINDING,
            "signer_coordinate": coordinate,
            "unsigned_content": _ctv(body),
            "digest": digest,
        }
    )


def _coordinate(ref: str, p: Ed25519PublicKey, purpose: str) -> dict[str, str]:
    return {
        "key_reference": ref,
        "signature_profile_id": PROFILE,
        "purpose": purpose,
        "public_key_fingerprint": sha256(p.public_bytes_raw()).hexdigest(),
    }


def _sign(
    purpose: str,
    domain: str,
    coordinate: dict[str, str],
    body: dict[str, Any],
    signer: Ed25519PrivateKey,
) -> SignedBody:
    d = _digest(domain, body)
    return SignedBody(
        purpose,
        coordinate,
        body,
        d,
        base64.b64encode(signer.sign(_message(purpose, coordinate, body, d))).decode(),
    )


def _verify(
    s: SignedBody,
    domain: str,
    purpose: str,
    coordinate: dict[str, str],
    p: Ed25519PublicKey,
) -> None:
    if (
        s.purpose != purpose
        or s.coordinate != coordinate
        or _digest(domain, s.body) != s.digest
    ):
        raise AuthorityRejected("signed_body")
    try:
        raw = base64.b64decode(s.signature, validate=True)
        if len(raw) != 64 or base64.b64encode(raw).decode() != s.signature:
            raise AuthorityRejected("signature")
        p.verify(raw, _message(purpose, coordinate, s.body, s.digest))
    except (InvalidSignature, ValueError) as e:
        raise AuthorityRejected("signature") from e


class _Scanner:
    """Closed JSON subset: object/array/string/int/bool/null, no floats/exponents."""

    def __init__(self, r: bytes, limits: Limits):
        self.r = r
        self.l = limits
        self.i = 0
        self.n = 0

    def fail(self, x: str) -> None:
        raise AuthorityRejected(x)

    def ws(self) -> None:
        while self.i < len(self.r) and self.r[self.i] in b" \t\r\n":
            self.i += 1

    def count(self) -> None:
        self.n += 1
        if self.n > self.l.max_nodes:
            self.fail("bootstrap_node_limit")

    def node(self, d: int) -> None:
        if d > self.l.max_depth:
            self.fail("bootstrap_depth_limit")
        self.count()
        self.ws()
        if self.i >= len(self.r):
            self.fail("bootstrap_syntax")
        c = self.r[self.i]
        if c == 34:
            self.string()
            return
        if c == 123:
            self.obj(d)
            return
        if c == 91:
            self.arr(d)
            return
        if self.r.startswith(b"true", self.i):
            self.i += 4
            return
        if self.r.startswith(b"false", self.i):
            self.i += 5
            return
        if self.r.startswith(b"null", self.i):
            self.i += 4
            return
        if c == 45 or 48 <= c <= 57:
            self.integer()
            return
        self.fail("bootstrap_subset")

    def string(self) -> None:
        self.i += 1
        size = 0
        while self.i < len(self.r):
            c = self.r[self.i]
            self.i += 1
            if c == 34:
                return
            if c < 32:
                self.fail("bootstrap_syntax")
            if c == 92:
                if self.i >= len(self.r):
                    self.fail("bootstrap_syntax")
                e = self.r[self.i]
                self.i += 1
                if e == 117:
                    x = self.r[self.i : self.i + 4]
                    if len(x) != 4 or any(
                        y not in b"0123456789abcdefABCDEF" for y in x
                    ):
                        self.fail("bootstrap_syntax")
                    scalar = int(x, 16)
                    self.i += 4
                    if 0xD800 <= scalar <= 0xDBFF:
                        if self.r[self.i : self.i + 2] != b"\\u":
                            self.fail("bootstrap_syntax")
                        low = self.r[self.i + 2 : self.i + 6]
                        if len(low) != 4 or any(y not in b"0123456789abcdefABCDEF" for y in low):
                            self.fail("bootstrap_syntax")
                        lower = int(low, 16)
                        if not 0xDC00 <= lower <= 0xDFFF:
                            self.fail("bootstrap_syntax")
                        scalar = 0x10000 + ((scalar - 0xD800) << 10) + lower - 0xDC00
                        self.i += 6
                    elif 0xDC00 <= scalar <= 0xDFFF:
                        self.fail("bootstrap_syntax")
                    size += len(chr(scalar).encode())
                elif e in b'"\\/bfnrt':
                    size += 1
                else:
                    self.fail("bootstrap_syntax")
            else:
                size += 1
            if size > self.l.max_string_bytes:
                self.fail("bootstrap_string_limit")
        self.fail("bootstrap_syntax")

    def integer(self) -> None:
        if self.r[self.i] == 45:
            self.i += 1
        start = self.i
        while self.i < len(self.r) and 48 <= self.r[self.i] <= 57:
            self.i += 1
        if self.i == start or self.i - start > self.l.max_integer_digits:
            self.fail("bootstrap_integer_limit")
        if self.i < len(self.r) and self.r[self.i] in b".eE":
            self.fail("bootstrap_subset")

    def arr(self, d: int) -> None:
        self.i += 1
        self.ws()
        if self.i < len(self.r) and self.r[self.i] == 93:
            self.i += 1
            return
        while True:
            self.node(d + 1)
            self.ws()
            if self.i >= len(self.r):
                self.fail("bootstrap_syntax")
            if self.r[self.i] == 93:
                self.i += 1
                return
            if self.r[self.i] != 44:
                self.fail("bootstrap_syntax")
            self.i += 1

    def obj(self, d: int) -> None:
        self.i += 1
        self.ws()
        if self.i < len(self.r) and self.r[self.i] == 125:
            self.i += 1
            return
        while True:
            self.ws()
            if self.i >= len(self.r) or self.r[self.i] != 34:
                self.fail("bootstrap_syntax")
            self.count()
            self.string()
            self.ws()
            if self.i >= len(self.r) or self.r[self.i] != 58:
                self.fail("bootstrap_syntax")
            self.i += 1
            self.node(d + 1)
            self.ws()
            if self.i >= len(self.r):
                self.fail("bootstrap_syntax")
            if self.r[self.i] == 125:
                self.i += 1
                return
            if self.r[self.i] != 44:
                self.fail("bootstrap_syntax")
            self.i += 1


def bounded_json(raw: bytes, limits: Limits) -> dict[str, Any]:
    if len(raw) > limits.max_input_bytes:
        raise AuthorityRejected("bootstrap_input_limit")
    s = _Scanner(raw, limits)
    s.node(1)
    s.ws()
    if s.i != len(raw):
        raise AuthorityRejected("bootstrap_syntax")
    try:
        v = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise AuthorityRejected("bootstrap_syntax") from e
    if type(v) is not dict:
        raise AuthorityRejected("json_object")
    return v


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthorityRejected("bootstrap_duplicate_key")
        result[key] = value
    return result


def issuance_snapshot(
    status: Ed25519PrivateKey,
    approval_keys: dict[str, Ed25519PublicKey],
    sp: Ed25519PublicKey,
) -> SignedBody:
    c = _coordinate("status", sp, STATUS_PURPOSE)
    b = {
        "authority_id": "model",
        "keys": [
            {
                "key_reference": reference,
                "public_key": base64.b64encode(public_key.public_bytes_raw()).decode(),
                "public_key_fingerprint": sha256(
                    public_key.public_bytes_raw()
                ).hexdigest(),
                "purpose": APPROVAL_PURPOSE,
            }
            for reference, public_key in sorted(approval_keys.items())
        ],
        "status_key": {
            "key_reference": "status",
            "fingerprint": c["public_key_fingerprint"],
            "purpose": STATUS_PURPOSE,
        },
    }
    return _sign(STATUS_PURPOSE, SNAPSHOT_DOMAIN, c, b, status)


def release(
    snapshot: SignedBody,
    signer: Ed25519PrivateKey,
    ap: Ed25519PublicKey,
    key_reference: str,
    name: str,
    sequence: int,
    epoch: int,
    state: str,
    supersedes: str | None,
    target: str = "baseline",
    dependency: str = "deps",
    policy: str = "policy",
    revoked_at: str | None = None,
    compromise_at: str | None = None,
) -> SignedBody:
    b = {
        "release_name": name,
        "capability_fingerprint": "capability",
        "issuance_trust_snapshot_digest": snapshot.digest,
        "acceptance_release_sequence": sequence,
        "acceptance_release_epoch": epoch,
        "target_baseline_digest": target,
        "dependency_coordinate": dependency,
        "policy_coordinate": policy,
        "lifecycle_state": state,
        "supersedes_release_digest": supersedes,
        "revoked_at": revoked_at,
        "compromise_effective_at": compromise_at,
    }
    return _sign(
        APPROVAL_PURPOSE,
        RELEASE_DOMAIN,
        _coordinate(key_reference, ap, APPROVAL_PURPOSE),
        b,
        signer,
    )


def key_state(
    snapshot: SignedBody,
    status: Ed25519PrivateKey,
    sp: Ed25519PublicKey,
    reference: str,
    state: str,
    sequence: int,
    predecessor: SignedBody | None,
) -> SignedBody:
    b = {
        "issuance_trust_snapshot_digest": snapshot.digest,
        "key_reference": reference,
        "state": state,
        "global_sequence": sequence,
        "predecessor_key_state_digest": None
        if predecessor is None
        else predecessor.digest,
    }
    return _sign(
        STATUS_PURPOSE, KEY_DOMAIN, _coordinate("status", sp, STATUS_PURPOSE), b, status
    )


def _snapshot_approval_keys(snapshot: SignedBody) -> dict[str, Ed25519PublicKey]:
    keys: dict[str, Ed25519PublicKey] = {}
    for declared in snapshot.body["keys"]:
        if (
            set(declared)
            != {"key_reference", "public_key", "public_key_fingerprint", "purpose"}
            or declared["purpose"] != APPROVAL_PURPOSE
            or declared["key_reference"] in keys
        ):
            raise AuthorityRejected("snapshot_key")
        try:
            raw = base64.b64decode(declared["public_key"], validate=True)
            public = Ed25519PublicKey.from_public_bytes(raw)
        except ValueError as exc:
            raise AuthorityRejected("snapshot_key") from exc
        if sha256(raw).hexdigest() != declared["public_key_fingerprint"]:
            raise AuthorityRejected("snapshot_key")
        keys[declared["key_reference"]] = public
    if not keys:
        raise AuthorityRejected("snapshot_key")
    return keys


def replay_release_registry(
    releases: tuple[SignedBody, ...], snapshot: SignedBody
) -> Pointer | None:
    if not releases:
        raise AuthorityRejected("release_empty")
    declared_keys = _snapshot_approval_keys(snapshot)
    previous = None
    active = None
    for seq, item in enumerate(releases, 1):
        reference = item.coordinate.get("key_reference")
        if reference not in declared_keys:
            raise AuthorityRejected("release_key")
        public = declared_keys[reference]
        _verify(
            item,
            RELEASE_DOMAIN,
            APPROVAL_PURPOSE,
            _coordinate(reference, public, APPROVAL_PURPOSE),
            public,
        )
        b = item.body
        if (
            b["issuance_trust_snapshot_digest"] != snapshot.digest
            or b["acceptance_release_sequence"] != seq
        ):
            raise AuthorityRejected("release_sequence")
        if previous is None:
            if (
                b["lifecycle_state"] != "active"
                or b["supersedes_release_digest"] is not None
                or b["acceptance_release_epoch"] != 1
                or b["revoked_at"] is not None
                or b["compromise_effective_at"] is not None
            ):
                raise AuthorityRejected("release_genesis")
            active = item
        else:
            p = previous.body
            if (
                b["supersedes_release_digest"] != previous.digest
                or b["capability_fingerprint"] != p["capability_fingerprint"]
            ):
                raise AuthorityRejected("release_predecessor")
            if p["lifecycle_state"] == "active":
                if (
                    b["lifecycle_state"] not in {"superseded", "revoked"}
                    or b["acceptance_release_epoch"] != p["acceptance_release_epoch"]
                ):
                    raise AuthorityRejected("release_active_transition")
                if any(
                    b[x] != p[x]
                    for x in (
                        "target_baseline_digest",
                        "dependency_coordinate",
                        "policy_coordinate",
                    )
                ):
                    raise AuthorityRejected("release_terminal_copy")
                if (
                    b["lifecycle_state"] == "superseded"
                    and (
                        b["revoked_at"] is not None
                        or b["compromise_effective_at"] is not None
                    )
                ) or (b["lifecycle_state"] == "revoked" and b["revoked_at"] is None):
                    raise AuthorityRejected("release_terminal_time")
                active = None
            else:
                if (
                    b["lifecycle_state"] != "active"
                    or b["acceptance_release_epoch"]
                    != p["acceptance_release_epoch"] + 1
                    or b["revoked_at"] is not None
                    or b["compromise_effective_at"] is not None
                ):
                    raise AuthorityRejected("release_terminal_transition")
                active = item
        previous = item
    if active is None:
        return None
    assert previous is not None
    b = {
        "release_digest": active.digest,
        "acceptance_release_epoch": active.body["acceptance_release_epoch"],
        "acceptance_release_sequence": active.body["acceptance_release_sequence"],
        "complete_chain_head_digest": previous.digest,
        "complete_chain_head_sequence": previous.body["acceptance_release_sequence"],
    }
    return Pointer(
        b, _digest("memorii:sia-capability-baseline-approval-active-pointer:v1\\0", b)
    )


def replay_key_ledger(
    records: tuple[SignedBody, ...],
    snapshot: SignedBody,
    head: SignedBody,
    sp: Ed25519PublicKey,
    selected: str,
) -> None:
    if not records or records[-1].digest != head.digest:
        raise AuthorityRejected("key_head")
    c = _coordinate("status", sp, STATUS_PURPOSE)
    heads = {}
    predecessor = None
    declared = {key["key_reference"] for key in snapshot.body["keys"]}
    for seq, item in enumerate(records, 1):
        _verify(item, KEY_DOMAIN, STATUS_PURPOSE, c, sp)
        b = item.body
        if b["key_reference"] not in declared or b["state"] not in {
            "active", "retired", "revoked", "compromised"
        }:
            raise AuthorityRejected("key_state_contract")
        prior = heads.get(b["key_reference"])
        if (
            b["issuance_trust_snapshot_digest"] != snapshot.digest
            or b["global_sequence"] != seq
        ):
            raise AuthorityRejected("key_sequence")
        if b["predecessor_key_state_digest"] != predecessor:
            raise AuthorityRejected("key_predecessor")
        if (prior is None and b["state"] != "active") or (
            prior is not None
            and (prior.body["state"] != "active" or b["state"] == "active")
        ):
            raise AuthorityRejected("key_state_transition")
        heads[b["key_reference"]] = item
        predecessor = item.digest
    if selected not in heads or heads[selected].body["state"] != "active":
        raise AuthorityRejected("key_not_active")


def current_checkpoint(
    pointer: Pointer | None,
    releases: tuple[SignedBody, ...],
    head: SignedBody,
    snapshot: SignedBody,
    status: Ed25519PrivateKey,
    sp: Ed25519PublicKey,
) -> SignedBody:
    a = (
        (None, None, None)
        if pointer is None
        else (
            pointer.digest,
            pointer.body["acceptance_release_epoch"],
            pointer.body["acceptance_release_sequence"],
        )
    )
    r = releases[-1]
    b = {
        "issuance_trust_snapshot_digest": snapshot.digest,
        "complete_chain_head_digest": r.digest,
        "complete_chain_head_sequence": r.body["acceptance_release_sequence"],
        "current_key_state_head_digest": head.digest,
        "current_key_state_sequence": head.body["global_sequence"],
        "active_pointer_digest": a[0],
        "active_release_epoch": a[1],
        "active_release_sequence": a[2],
    }
    return _sign(
        STATUS_PURPOSE,
        CHECKPOINT_DOMAIN,
        _coordinate("status", sp, STATUS_PURPOSE),
        b,
        status,
    )


def revocation_receipt(
    old: SignedBody,
    prior_production_epoch: int,
    advanced_production_epoch: int,
    signer: Ed25519PrivateKey,
    rp: Ed25519PublicKey,
) -> SignedBody:
    return _sign(
        RECEIPT_PURPOSE,
        RECEIPT_DOMAIN,
        _coordinate("receipt", rp, RECEIPT_PURPOSE),
        {
            "prior_release_digest": old.digest,
            "prior_production_epoch": prior_production_epoch,
            "advanced_production_epoch": advanced_production_epoch,
        },
        signer,
    )


@dataclass(frozen=True)
class InMemoryCurrentStatusProvider:
    checkpoint: SignedBody

    def load_current(self) -> SignedBody:
        return self.checkpoint


def verify_current_release(
    selected: SignedBody,
    snapshot: SignedBody,
    releases: tuple[SignedBody, ...],
    keys: tuple[SignedBody, ...],
    provider: InMemoryCurrentStatusProvider,
    anchor: TrustAnchor,
    receipts: tuple[SignedBody, ...],
) -> None:
    _verify(
        snapshot,
        SNAPSHOT_DOMAIN,
        STATUS_PURPOSE,
        anchor.status_coordinate,
        anchor.status_public_key,
    )
    checkpoint = provider.load_current()
    _verify(
        checkpoint,
        CHECKPOINT_DOMAIN,
        STATUS_PURPOSE,
        anchor.status_coordinate,
        anchor.status_public_key,
    )
    pointer = replay_release_registry(releases, snapshot)
    b = checkpoint.body
    if (
        b["issuance_trust_snapshot_digest"] != snapshot.digest
        or b["complete_chain_head_digest"] != releases[-1].digest
        or b["complete_chain_head_sequence"]
        != releases[-1].body["acceptance_release_sequence"]
    ):
        raise AuthorityRejected("checkpoint_chain_head")
    actual = (
        (None, None, None)
        if pointer is None
        else (
            pointer.digest,
            pointer.body["acceptance_release_epoch"],
            pointer.body["acceptance_release_sequence"],
        )
    )
    given = (
        b["active_pointer_digest"],
        b["active_release_epoch"],
        b["active_release_sequence"],
    )
    if any(x is None for x in given) != all(x is None for x in given):
        raise AuthorityRejected("checkpoint_active_group")
    if given != actual:
        raise AuthorityRejected("checkpoint_pointer")
    if (
        not keys
        or b["current_key_state_head_digest"] != keys[-1].digest
        or b["current_key_state_sequence"] != keys[-1].body["global_sequence"]
    ):
        raise AuthorityRejected("checkpoint_key_head")
    replay_key_ledger(
        keys,
        snapshot,
        keys[-1],
        anchor.status_public_key,
        selected.coordinate["key_reference"],
    )
    for old, new in zip(releases, releases[1:]):
        if old.body["lifecycle_state"] == "active" and new.body["lifecycle_state"] in {
            "superseded",
            "revoked",
        }:
            matches = [
                x for x in receipts if x.body.get("prior_release_digest") == old.digest
            ]
            if len(matches) != 1:
                raise AuthorityRejected("revocation_receipt")
            _verify(
                matches[0],
                RECEIPT_DOMAIN,
                RECEIPT_PURPOSE,
                anchor.receipt_coordinate,
                anchor.receipt_public_key,
            )
            if (
                matches[0].body["advanced_production_epoch"]
                <= matches[0].body["prior_production_epoch"]
            ):
                raise AuthorityRejected("revocation_receipt_epoch")
    if pointer is None or pointer.body["release_digest"] != selected.digest:
        raise AuthorityRejected("not_current")

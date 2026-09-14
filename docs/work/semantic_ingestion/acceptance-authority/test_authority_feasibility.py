import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from authority_feasibility import (
    APPROVAL_PURPOSE,
    CHECKPOINT_DOMAIN,
    RECEIPT_PURPOSE,
    RELEASE_DOMAIN,
    STATUS_PURPOSE,
    AuthorityRejected,
    InMemoryCurrentStatusProvider,
    Limits,
    TrustAnchor,
    _coordinate,
    _ctv,
    _sign,
    bounded_json,
    current_checkpoint,
    issuance_snapshot,
    key_state,
    release,
    replay_release_registry,
    revocation_receipt,
    verify_current_release,
)


def make_chain(terminal="superseded"):
    old = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    new = Ed25519PrivateKey.from_private_bytes(b"\x04" * 32)
    status = Ed25519PrivateKey.from_private_bytes(b"\x02" * 32)
    receipt = Ed25519PrivateKey.from_private_bytes(b"\x03" * 32)
    old_public, new_public = old.public_key(), new.public_key()
    sp, rp = status.public_key(), receipt.public_key()
    anchor = TrustAnchor(
        _coordinate("status", sp, STATUS_PURPOSE),
        sp,
        _coordinate("receipt", rp, RECEIPT_PURPOSE),
        rp,
    )
    snapshot = issuance_snapshot(status, {
        "old": old_public, "new": new_public,
        "unrelated": Ed25519PrivateKey.from_private_bytes(b"\x05" * 32).public_key(),
    }, sp)
    a = release(snapshot, old, old_public, "old", "A", 1, 1, "active", None)
    t = release(
        snapshot,
        old,
        old_public,
        "old",
        "T",
        2,
        1,
        terminal,
        a.digest,
        revoked_at="now" if terminal == "revoked" else None,
    )
    b = release(
        snapshot,
        new,
        new_public,
        "new",
        "B",
        3,
        2,
        "active",
        t.digest,
        target="replacement",
    )
    ka = key_state(snapshot, status, sp, "old", "active", 1, None)
    kn = key_state(snapshot, status, sp, "new", "active", 2, ka)
    ko = key_state(snapshot, status, sp, "old", "retired", 3, kn)
    kx = key_state(snapshot, status, sp, "unrelated", "active", 4, ko)
    releases = (a, t, b)
    keys = (ka, kn, ko, kx)
    pointer = replay_release_registry(releases, snapshot)
    checkpoint = current_checkpoint(pointer, releases, kx, snapshot, status, sp)
    return locals()


def check(c, checkpoint=None, keys=None, receipts=None):
    verify_current_release(
        c["b"],
        c["snapshot"],
        c["releases"],
        keys or c["keys"],
        InMemoryCurrentStatusProvider(checkpoint or c["checkpoint"]),
        c["anchor"],
        receipts if receipts is not None else (c["receipt_body"],),
    )


def test_current_verifier_reaches_a_terminal_b_with_rotation():
    c = make_chain()
    c["receipt_body"] = revocation_receipt(c["a"], 10, 11, c["receipt"], c["rp"])
    check(c)
    assert c["pointer"].body["release_digest"] == c["b"].digest


def test_terminal_is_zero_active_and_selected_terminal_fails():
    c = make_chain()
    c["receipt_body"] = revocation_receipt(c["a"], 10, 11, c["receipt"], c["rp"])
    rs = c["releases"][:2]
    assert replay_release_registry(rs, c["snapshot"]) is None
    cp = current_checkpoint(
        None, rs, c["keys"][1], c["snapshot"], c["status"], c["sp"]
    )
    with pytest.raises(AuthorityRejected, match="not_current"):
        verify_current_release(
            c["t"],
            c["snapshot"],
            rs,
            c["keys"][:2],
            InMemoryCurrentStatusProvider(cp),
            c["anchor"],
            (c["receipt_body"],),
        )


@pytest.mark.parametrize(
    "state,sequence,predecessor",
    [("active", 2, "a"), ("superseded", 3, "t"), ("revoked", 3, "t")],
)
def test_full_illegal_transition_table(state, sequence, predecessor):
    c = make_chain()
    bad = release(
        c["snapshot"],
        c["new"],
        c["new_public"],
        "new",
        "bad",
        sequence,
        3,
        state,
        c[predecessor].digest,
    )
    with pytest.raises(AuthorityRejected):
        replay_release_registry(c["releases"] + (bad,), c["snapshot"])


def test_terminal_copy_and_time_under_trusted_resigning():
    c = make_chain("revoked")
    body = {**c["t"].body, "policy_coordinate": "other"}
    bad = _sign(APPROVAL_PURPOSE, RELEASE_DOMAIN, c["t"].coordinate, body, c["old"])
    with pytest.raises(AuthorityRejected, match="terminal_copy"):
        replay_release_registry((c["a"], bad), c["snapshot"])
    body = {**c["t"].body, "revoked_at": None}
    bad = _sign(APPROVAL_PURPOSE, RELEASE_DOMAIN, c["t"].coordinate, body, c["old"])
    with pytest.raises(AuthorityRejected, match="terminal_time"):
        replay_release_registry((c["a"], bad), c["snapshot"])


def test_old_key_revocation_after_unrelated_and_revival():
    c = make_chain()
    c["receipt_body"] = revocation_receipt(c["a"], 10, 11, c["receipt"], c["rp"])
    revoked = key_state(
        c["snapshot"], c["status"], c["sp"], "new", "revoked", 5, c["keys"][-1]
    )
    cp = current_checkpoint(
        c["pointer"], c["releases"], revoked, c["snapshot"], c["status"], c["sp"]
    )
    with pytest.raises(AuthorityRejected, match="key_not_active"):
        check(c, cp, c["keys"] + (revoked,))
    revived = key_state(
        c["snapshot"], c["status"], c["sp"], "new", "active", 6, revoked
    )
    cp = current_checkpoint(
        c["pointer"], c["releases"], revived, c["snapshot"], c["status"], c["sp"]
    )
    with pytest.raises(AuthorityRejected, match="key_state_transition"):
        check(c, cp, c["keys"] + (revoked, revived))


def test_distinct_status_identity_and_tamper():
    c = make_chain()
    c["receipt_body"] = revocation_receipt(c["a"], 10, 11, c["receipt"], c["rp"])
    body = {**c["checkpoint"].body, "active_release_epoch": None}
    bad = _sign(
        STATUS_PURPOSE, CHECKPOINT_DOMAIN, c["checkpoint"].coordinate, body, c["status"]
    )
    with pytest.raises(AuthorityRejected, match="active_group"):
        check(c, bad)
    wrong = TrustAnchor(
        _coordinate("other", c["sp"], STATUS_PURPOSE),
        c["sp"],
        c["anchor"].receipt_coordinate,
        c["rp"],
    )
    with pytest.raises(AuthorityRejected, match="signed_body"):
        verify_current_release(
            c["b"],
            c["snapshot"],
            c["releases"],
            c["keys"],
            InMemoryCurrentStatusProvider(c["checkpoint"]),
            wrong,
            (c["receipt_body"],),
        )


def test_receipt_missing_substituted_stale():
    c = make_chain()
    for receipts in (
        (),
        (revocation_receipt(c["t"], 10, 11, c["receipt"], c["rp"]),),
        (revocation_receipt(c["a"], 10, 10, c["receipt"], c["rp"]),),
    ):
        with pytest.raises(AuthorityRejected, match="revocation_receipt"):
            check(c, receipts=receipts)


def test_exact_ctv_and_every_scanner_cap_boundary():
    assert (
        _ctv({"\n": 1, "A": 2})
        == b'{"$type":"map","entries":[["A",{"$type":"integer","value":"2"}],["\\n",{"$type":"integer","value":"1"}]]}'
    )
    assert (
        _ctv({"z": 1, "a": 2})
        == b'{"$type":"map","entries":[["a",{"$type":"integer","value":"2"}],["z",{"$type":"integer","value":"1"}]]}'
    )
    assert (
        _ctv({"outer": {"\n": 1, "A": 2}})
        == b'{"$type":"map","entries":[["outer",{"$type":"map","entries":[["A",{"$type":"integer","value":"2"}],["\\n",{"$type":"integer","value":"1"}]]}]]}'
    )

    # Each rejected byte stream exceeds only its named protected ceiling.
    cases = (
        (b'{"a":1}', Limits(6, 8, 20, 20, 20), "input"),
        (b'{"aaaa":1}', Limits(100, 8, 20, 3, 20), "string"),
        (b'{"a":123}', Limits(100, 8, 20, 20, 2), "integer"),
        (b'{"a":{"b":{"c":1}}}', Limits(100, 2, 20, 20, 20), "depth"),
        (b'{"a":1,"b":2,"c":3}', Limits(100, 8, 5, 20, 20), "node"),
        (b'{"a":"\\u0061\\u0062\\u0063\\u0064"}', Limits(100, 8, 20, 3, 20), "string"),
    )
    for raw, limits, reason in cases:
        with pytest.raises(AuthorityRejected, match="bootstrap_.*" + reason):
            bounded_json(raw, limits)
    for raw, reason in ((b'{"a":1} trailing', "syntax"), (b'{"a":1.0}', "subset")):
        with pytest.raises(AuthorityRejected, match="bootstrap_.*" + reason):
            bounded_json(raw, Limits(100, 8, 20, 20, 20))


@pytest.mark.parametrize("reference,state,prior,reason", [
    ("new", "unknown", -1, "key_state_contract"),
    ("undeclared", "active", -1, "key_state_contract"),
    ("new", "revoked", 1, "key_predecessor"),
])
def test_public_verifier_rejects_invalid_global_key_records(reference, state, prior, reason):
    c = make_chain()
    c["receipt_body"] = revocation_receipt(c["a"], 10, 11, c["receipt"], c["rp"])
    bad = key_state(c["snapshot"], c["status"], c["sp"], reference, state, 5, c["keys"][prior])
    cp = current_checkpoint(c["pointer"], c["releases"], bad, c["snapshot"], c["status"], c["sp"])
    with pytest.raises(AuthorityRejected, match=reason):
        check(c, cp, c["keys"] + (bad,))


def test_public_verifier_rejects_undeclared_release_signer():
    c = make_chain()
    c["receipt_body"] = revocation_receipt(c["a"], 10, 11, c["receipt"], c["rp"])
    bad = _sign(APPROVAL_PURPOSE, RELEASE_DOMAIN,
                _coordinate("undeclared", c["new_public"], APPROVAL_PURPOSE), c["b"].body, c["new"])
    c["b"] = bad
    c["releases"] = c["releases"][:2] + (bad,)
    with pytest.raises(AuthorityRejected, match="release_key"):
        check(c)


def test_status_fingerprint_is_checked_even_with_valid_signature():
    c = make_chain()
    c["receipt_body"] = revocation_receipt(c["a"], 10, 11, c["receipt"], c["rp"])
    coordinate = {**c["checkpoint"].coordinate, "public_key_fingerprint": "0" * 64}
    bad = _sign(STATUS_PURPOSE, CHECKPOINT_DOMAIN, coordinate, c["checkpoint"].body, c["status"])
    with pytest.raises(AuthorityRejected, match="signed_body"):
        check(c, bad)


def test_scanner_unicode_duplicates_and_protected_configuration():
    limits = Limits(100, 8, 20, 4, 20)
    assert bounded_json(b'{"a":"\\ud83d\\ude00"}', limits) == {"a": "\U0001f600"}
    for raw in (b'{"a":"\\ud83d"}', b'{"a":"\\ude00"}'):
        with pytest.raises(AuthorityRejected, match="bootstrap_syntax"):
            bounded_json(raw, limits)
    for raw in (b'{"a":1,"a":2}', b'{"a":1,"\\u0061":2}', b'{"b":{"a":1,"a":2}}'):
        with pytest.raises(AuthorityRejected, match="bootstrap_duplicate_key"):
            bounded_json(raw, limits)
    with pytest.raises(AuthorityRejected, match="bootstrap_string_limit"):
        bounded_json(b'{"a":"\\ud83d\\ude00"}', Limits(100, 8, 20, 3, 20))
    for depth in (True, 0, 65):
        with pytest.raises(AuthorityRejected, match="bootstrap_.*"):
            Limits(100, depth, 20, 4, 20)

import json
import sys
from pathlib import Path

import pytest

import authority_successor_feasibility

from authority_successor_feasibility import (
    Limits,
    ProtectedCurrentStatus,
    PublicVerifier,
    Rejected,
    bounded_object,
    reduce_key_history,
)


def raw(value):
    return json.dumps(value, separators=(",", ":")).encode()


def verifier(release=None, history=None, checkpoint=None, receipt=None):
    release = release or {
        "digest": "r2",
        "key": "new",
        "issued_at": 20,
        "expires_at": 80,
        "state": "active",
        "baseline_digest": "b",
        "sequence": 2,
        "epoch": 2,
    }
    history = history or {
        "keys": [
            {
                "key": "old",
                "valid_from": 0,
                "valid_until": None,
                "purposes": ["approval"],
            },
            {
                "key": "new",
                "valid_from": 10,
                "valid_until": 60,
                "purposes": ["approval"],
            },
        ],
        "events": [
            {
                "key": "old",
                "state": "active",
                "effective_at": 1,
                "sequence": 1,
                "previous": None,
            },
            {
                "key": "new",
                "state": "active",
                "effective_at": 10,
                "sequence": 2,
                "previous": "old:1",
            },
            {
                "key": "old",
                "state": "compromised",
                "effective_at": 16,
                "sequence": 3,
                "previous": "new:2",
            },
        ],
    }
    checkpoint = checkpoint or {
        "release_digest": "r2",
        "release_sequence": 2,
        "key_event_count": 3,
        "observed_at": 40,
        "receipt_digest": "receipt-r1",
    }
    receipt = receipt or {
        "withdrawn_release_digest": "r1",
        "withdrawal_requested_at": 18,
        "prior_production_epoch": 1,
        "advanced_production_epoch": 2,
        "completed_at": 19,
        "digest": "receipt-r1",
    }
    predecessor = {
        "active_release_digest": "r2",
        "active_epoch": 2,
        "active_sequence": 2,
        "key_head_sequence": 3,
        "receipt_withdrawn_digest": "r1",
        "receipt_digest": "receipt-r1",
        "receipt_prior_epoch": 1,
        "receipt_advanced_epoch": 2,
    }
    status = ProtectedCurrentStatus(
        raw(history), raw(checkpoint), raw(receipt), raw(predecessor)
    )
    return (
        PublicVerifier(status),
        raw(release),
        raw({"digest": "b", "capability": "cap"}),
    )


def test_public_byte_entry_scans_every_supplied_and_protected_byte_stream():
    v, release, baseline = verifier()
    assert v.verify(release, baseline, 40) == "r2"
    with pytest.raises(Rejected, match="byte_limit"):
        PublicVerifier(v._status, Limits(maximum_bytes=8)).verify(release, baseline, 40)


@pytest.mark.parametrize("raw", [b'{"a":1.0}', b'{"a":1e3}', b'{"a":"\\uD800"}'])
def test_predecode_scanner_rejects_before_general_json_load(monkeypatch, raw):
    def decoder_must_not_run(*args, **kwargs):
        raise AssertionError("json.loads was reached")

    monkeypatch.setattr(
        authority_successor_feasibility.json, "loads", decoder_must_not_run
    )
    with pytest.raises(Rejected):
        authority_successor_feasibility.bounded_object(raw, Limits())


@pytest.mark.parametrize(
    "raw,limits",
    [
        (b"{}", Limits(maximum_bytes=1)),
        (b'{"a":{"b":1}}', Limits(maximum_depth=2)),
        (b'{"a":1}', Limits(maximum_nodes=2)),
        (b'{"aaaa":1}', Limits(maximum_string_bytes=3)),
        (b'{"a":123}', Limits(maximum_integer_digits=2)),
    ],
)
def test_every_advertised_limit_rejects_one_over_before_decoder(
    monkeypatch, raw, limits
):
    monkeypatch.setattr(
        authority_successor_feasibility.json,
        "loads",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("decoder reached")
        ),
    )
    with pytest.raises(Rejected):
        bounded_object(raw, limits)


@pytest.mark.parametrize(
    "field,value",
    [("extra", 1), ("issued_at", True), ("key", ""), ("state", "revived")],
)
def test_release_shape_and_exact_types_are_closed(field, value):
    verifier_, release, baseline = verifier()
    body = json.loads(release)
    body[field] = value
    with pytest.raises(Rejected):
        verifier_.verify(raw(body), baseline, 40)


def test_issue_time_prevents_future_rotation_from_authorizing_old_issue():
    verifier_, release, baseline = verifier()
    body = json.loads(release)
    body["issued_at"] = 5
    with pytest.raises(Rejected, match="issue_key_not_active"):
        verifier_.verify(raw(body), baseline, 40)


def test_compromise_before_issue_and_reordered_history_fail():
    verifier_, release, baseline = verifier()
    history = json.loads(verifier_._status.current()[0])
    history["events"][1], history["events"][2] = (
        history["events"][2],
        history["events"][1],
    )
    broken = PublicVerifier(
        ProtectedCurrentStatus(
            raw(history),
            *verifier_._status.current()[1:],
            verifier_._status.predecessor(),
        )
    )
    with pytest.raises(Rejected, match="key_order"):
        broken.verify(release, baseline, 40)


def test_compromise_after_issue_blocks_current_evaluation():
    verifier_, release, baseline = verifier()
    history = json.loads(verifier_._status.current()[0])
    history["events"].append(
        {
            "key": "new",
            "state": "compromised",
            "effective_at": 35,
            "sequence": 4,
            "previous": "old:3",
        }
    )
    checkpoint = json.loads(verifier_._status.current()[1])
    checkpoint["key_event_count"] = 4
    predecessor = json.loads(verifier_._status.predecessor())
    predecessor["key_head_sequence"] = 4
    broken = PublicVerifier(
        ProtectedCurrentStatus(
            raw(history),
            raw(checkpoint),
            verifier_._status.current()[2],
            raw(predecessor),
        )
    )
    with pytest.raises(Rejected, match="issue_key_not_active"):
        broken.verify(release, baseline, 40)


def test_trusted_resigning_cannot_smuggle_missing_or_extra_modeled_fields():
    verifier_, release, baseline = verifier()
    body = json.loads(release)
    del body["epoch"]
    with pytest.raises(Rejected, match="release_shape"):
        verifier_.verify(raw(body), baseline, 40)


@pytest.mark.parametrize("issued_at", [10, 60])
def test_static_key_validity_has_inclusive_start_and_exclusive_end(issued_at):
    verifier_, release, baseline = verifier()
    body = json.loads(release)
    body["issued_at"] = issued_at
    if issued_at == 10:
        assert verifier_.verify(raw(body), baseline, 40) == "r2"
    else:
        history, checkpoint, receipt = verifier_._status.current()
        checkpoint_body = json.loads(checkpoint)
        checkpoint_body["observed_at"] = 60
        coherent = PublicVerifier(
            ProtectedCurrentStatus(
                history,
                raw(checkpoint_body),
                receipt,
                verifier_._status.predecessor(),
            )
        )
        with pytest.raises(Rejected, match="key_static_validity"):
            coherent.verify(raw(body), baseline, 60)


def test_unknown_unused_static_field_fails_before_result():
    verifier_, release, baseline = verifier()
    history = json.loads(verifier_._status.current()[0])
    history["keys"][0]["unused"] = "smuggled"
    broken = PublicVerifier(
        ProtectedCurrentStatus(
            raw(history),
            *verifier_._status.current()[1:],
            verifier_._status.predecessor(),
        )
    )
    with pytest.raises(Rejected, match="key_static_shape"):
        broken.verify(release, baseline, 40)


def test_rotation_ties_and_cutoffs_are_determinate_for_historical_and_future_keys():
    events = [
        {
            "key": "old",
            "state": "active",
            "effective_at": 10,
            "sequence": 1,
            "previous": None,
        },
        {
            "key": "new",
            "state": "active",
            "effective_at": 10,
            "sequence": 2,
            "previous": "old:1",
        },
        {
            "key": "old",
            "state": "retired",
            "effective_at": 10,
            "sequence": 3,
            "previous": "new:2",
        },
    ]
    assert reduce_key_history(events, 10, "new") == "active"
    with pytest.raises(Rejected, match="issue_key_not_active"):
        reduce_key_history(events, 10, "old")


def test_successor_byte_entry_composes_with_preserved_predecessor_lifecycle():
    predecessor = Path(__file__).parents[1] / "acceptance-authority"
    sys.path.insert(0, str(predecessor))
    try:
        from authority_feasibility import revocation_receipt
        from test_authority_feasibility import check, make_chain

        chain = make_chain()
        chain["receipt_body"] = revocation_receipt(
            chain["a"], 10, 11, chain["receipt"], chain["rp"]
        )

        def predecessor_result():
            check(chain)
            pointer = chain["pointer"].body
            return raw(
                {
                    "active_release_digest": pointer["release_digest"],
                    "active_epoch": pointer["acceptance_release_epoch"],
                    "active_sequence": pointer["acceptance_release_sequence"],
                    "key_head_sequence": chain["keys"][-1].body["global_sequence"],
                    "receipt_withdrawn_digest": chain["receipt_body"].body[
                        "prior_release_digest"
                    ],
                    "receipt_digest": chain["receipt_body"].digest,
                    "receipt_prior_epoch": chain["receipt_body"].body[
                        "prior_production_epoch"
                    ],
                    "receipt_advanced_epoch": chain["receipt_body"].body[
                        "advanced_production_epoch"
                    ],
                }
            )
    finally:
        sys.path.remove(str(predecessor))
    verifier_, release, baseline = verifier()
    release_body = json.loads(release)
    release_body["digest"] = chain["b"].digest
    release_body["epoch"] = chain["pointer"].body["acceptance_release_epoch"]
    release_body["sequence"] = chain["pointer"].body["acceptance_release_sequence"]
    history = json.loads(verifier_._status.current()[0])
    history["keys"].append(
        {
            "key": "unrelated",
            "valid_from": 0,
            "valid_until": None,
            "purposes": ["approval"],
        }
    )
    history["events"].append(
        {
            "key": "unrelated",
            "state": "active",
            "effective_at": 17,
            "sequence": 4,
            "previous": "old:3",
        }
    )
    checkpoint = json.loads(verifier_._status.current()[1])
    checkpoint["release_digest"] = chain["b"].digest
    checkpoint["release_sequence"] = chain["pointer"].body[
        "acceptance_release_sequence"
    ]
    checkpoint["key_event_count"] = 4
    checkpoint["receipt_digest"] = chain["receipt_body"].digest
    receipt = json.loads(verifier_._status.current()[2])
    receipt["withdrawn_release_digest"] = chain["receipt_body"].body[
        "prior_release_digest"
    ]
    receipt["digest"] = chain["receipt_body"].digest
    receipt["prior_production_epoch"] = chain["receipt_body"].body[
        "prior_production_epoch"
    ]
    receipt["advanced_production_epoch"] = chain["receipt_body"].body[
        "advanced_production_epoch"
    ]
    composed = PublicVerifier(
        ProtectedCurrentStatus(
            raw(history),
            raw(checkpoint),
            raw(receipt),
            predecessor_result=predecessor_result,
        )
    )
    assert composed.verify(raw(release_body), baseline, 40) == chain["b"].digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("active_release_digest", "other"),
        ("key_head_sequence", 2),
        ("receipt_withdrawn_digest", "other"),
    ],
)
def test_valid_but_different_predecessor_result_is_not_accepted(field, value):
    verifier_, release, baseline = verifier()
    predecessor = json.loads(verifier_._status.predecessor())
    predecessor[field] = value
    history, checkpoint, receipt = verifier_._status.current()
    broken = PublicVerifier(
        ProtectedCurrentStatus(history, checkpoint, receipt, raw(predecessor))
    )
    with pytest.raises(Rejected, match="predecessor_binding"):
        broken.verify(release, baseline, 40)


@pytest.mark.parametrize("sequence", [1, 4])
def test_key_sequence_gaps_and_duplicates_reject_before_cutoff(sequence):
    verifier_, release, baseline = verifier()
    history = json.loads(verifier_._status.current()[0])
    history["events"][1]["sequence"] = sequence
    broken = PublicVerifier(
        ProtectedCurrentStatus(
            raw(history),
            *verifier_._status.current()[1:],
            verifier_._status.predecessor(),
        )
    )
    with pytest.raises(Rejected, match="key_sequence"):
        broken.verify(release, baseline, 40)


@pytest.mark.parametrize("observed_at", [39, 41])
def test_checkpoint_must_cover_exact_evaluation_instant(observed_at):
    verifier_, release, baseline = verifier()
    history, checkpoint, receipt = verifier_._status.current()
    checkpoint_body = json.loads(checkpoint)
    checkpoint_body["observed_at"] = observed_at
    broken = PublicVerifier(
        ProtectedCurrentStatus(
            history, raw(checkpoint_body), receipt, verifier_._status.predecessor()
        )
    )
    with pytest.raises(Rejected, match="checkpoint_time"):
        broken.verify(release, baseline, 40)


@pytest.mark.parametrize("stream", ["history", "checkpoint", "receipt", "predecessor"])
def test_each_protected_stream_rejects_malformed_or_overlimit_bytes(stream):
    verifier_, release, baseline = verifier()
    history, checkpoint, receipt = verifier_._status.current()
    streams = {
        "history": history,
        "checkpoint": checkpoint,
        "receipt": receipt,
        "predecessor": verifier_._status.predecessor(),
    }
    streams[stream] = b"{" + b"x" * 5000
    broken = PublicVerifier(
        ProtectedCurrentStatus(
            streams["history"],
            streams["checkpoint"],
            streams["receipt"],
            streams["predecessor"],
        )
    )
    with pytest.raises(Rejected, match="byte_limit"):
        broken.verify(release, baseline, 40)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b"[]"])
def test_duplicate_keys_and_nonmap_roots_reject_at_byte_entry(raw):
    with pytest.raises(Rejected):
        bounded_object(raw, Limits())


def test_exact_byte_ceiling_is_accepted_and_one_over_rejects():
    raw_object = b'{"a":1}'
    assert bounded_object(raw_object, Limits(maximum_bytes=len(raw_object))) == {"a": 1}
    with pytest.raises(Rejected, match="byte_limit"):
        bounded_object(raw_object, Limits(maximum_bytes=len(raw_object) - 1))


@pytest.mark.parametrize(
    "raw,limits",
    [
        (b'{"a":{"b":1}}', Limits(maximum_depth=3)),
        (b'{"a":1}', Limits(maximum_nodes=3)),
        (b'{"aaa":1}', Limits(maximum_string_bytes=3)),
        (b'{"a":12}', Limits(maximum_integer_digits=2)),
    ],
)
def test_exact_nonbyte_ceilings_are_accepted(raw, limits):
    assert bounded_object(raw, limits)


@pytest.mark.parametrize("raw", [b'{"a":01}', b'{"a":00}', b'{"a":-01}', b'{"a":-0}'])
def test_integer_lexical_grammar_rejects_before_decoder(monkeypatch, raw):
    monkeypatch.setattr(
        authority_successor_feasibility.json,
        "loads",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("decoder reached")
        ),
    )
    with pytest.raises(Rejected, match="integer_grammar"):
        bounded_object(raw, Limits())


@pytest.mark.parametrize("stream", ["history", "checkpoint", "receipt", "predecessor"])
def test_each_protected_stream_rejects_malformed_bytes(stream):
    verifier_, release, baseline = verifier()
    history, checkpoint, receipt = verifier_._status.current()
    streams = {
        "history": history,
        "checkpoint": checkpoint,
        "receipt": receipt,
        "predecessor": verifier_._status.predecessor(),
    }
    streams[stream] = b'{"unterminated"'
    broken = PublicVerifier(
        ProtectedCurrentStatus(
            streams["history"],
            streams["checkpoint"],
            streams["receipt"],
            streams["predecessor"],
        )
    )
    with pytest.raises(Rejected):
        broken.verify(release, baseline, 40)


@pytest.mark.parametrize(
    "field,value",
    [
        ("digest", "other"),
        ("advanced_production_epoch", 1),
        ("advanced_production_epoch", 3),
        ("prior_production_epoch", 0),
    ],
)
def test_receipt_digest_and_epoch_substitution_reject(field, value):
    verifier_, release, baseline = verifier()
    history, checkpoint, receipt = verifier_._status.current()
    receipt_body = json.loads(receipt)
    receipt_body[field] = value
    broken = PublicVerifier(
        ProtectedCurrentStatus(
            history, checkpoint, raw(receipt_body), verifier_._status.predecessor()
        )
    )
    with pytest.raises(Rejected):
        broken.verify(release, baseline, 40)


@pytest.mark.parametrize(
    "valid_from,valid_until,accepted",
    [(20, 21, True), (19, 20, False), (21, 22, False), (20, None, True)],
)
def test_selected_key_static_interval_endpoints(valid_from, valid_until, accepted):
    verifier_, release, baseline = verifier()
    history, checkpoint, receipt = verifier_._status.current()
    body = json.loads(history)
    body["keys"][1].update(valid_from=valid_from, valid_until=valid_until)
    subject = PublicVerifier(
        ProtectedCurrentStatus(
            raw(body), checkpoint, receipt, verifier_._status.predecessor()
        )
    )
    if accepted:
        assert subject.verify(release, baseline, 40) == "r2"
    else:
        with pytest.raises(Rejected, match="key_static_validity"):
            subject.verify(release, baseline, 40)

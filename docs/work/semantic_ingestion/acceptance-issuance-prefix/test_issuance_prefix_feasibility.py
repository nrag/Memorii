"""Public-byte composition tests; the original 56 families run unchanged beside these."""
import json

import pytest

from issuance_prefix_feasibility import SNAPSHOT_PURPOSE, ComposedIssuanceVerifier, Rejected, base
from test_authority_successor_feasibility import raw, verifier


class FixtureCommittedLookup:
    """Previously issued fixtures; real prepare/publish composition is tested below."""

    def __init__(self, snapshots):
        self._snapshots = snapshots

    def load(self, snapshot_digest, release_digest):
        return self._snapshots.get(snapshot_digest) if release_digest == "r2" else None


def fixture(prefix_length=3, issued_at=20):
    preserved, release, baseline = verifier()
    release = json.loads(release)
    release["issued_at"] = issued_at
    release["acceptance_authority_snapshot_digest"] = "issuance"
    history = json.loads(preserved._status.current()[0])
    history["keys"][1]["purposes"].append(SNAPSHOT_PURPOSE)
    preserved._status._history_bytes = raw(history)
    events = history["events"][:prefix_length]
    snapshot = {"digest": "issuance", "keys": history["keys"], "events": events,
                "head_digest": f"{events[-1]['key']}:{prefix_length}", "head_sequence": prefix_length,
                "signing_key": "new"}
    return preserved._status, release, baseline, snapshot


def run(status, release, baseline, snapshot, limits=base.Limits()):
    return ComposedIssuanceVerifier(status, FixtureCommittedLookup({"issuance": raw(snapshot)}), limits).verify(raw(release), baseline, 40)


def test_protected_prefix_and_preserved_lifecycle_accept():
    assert run(*fixture()) == "r2"


def test_later_equal_time_activation_cannot_authorize_issuance():
    # Current history authorizes new at time 10; the release's prefix has only old.
    status, release, baseline, snapshot = fixture(prefix_length=1, issued_at=10)
    with pytest.raises(Rejected, match="issue_key_not_active"):
        run(status, release, baseline, snapshot)


def test_future_activation_in_prefix_cannot_authorize_earlier_issuance():
    with pytest.raises(Rejected, match="issue_key_not_active"):
        run(*fixture(prefix_length=2, issued_at=9))


@pytest.mark.parametrize("field,value,reason", [
    ("head_digest", "wrong", "issuance_head"),
    ("head_sequence", 2, "issuance_head"),
    ("head_sequence", True, "positive"),
    ("digest", "other", "issuance_snapshot_binding"),
])
def test_snapshot_coordinates_are_exact(field, value, reason):
    status, release, baseline, snapshot = fixture()
    snapshot[field] = value
    with pytest.raises(Rejected, match=reason):
        run(status, release, baseline, snapshot)


def test_missing_snapshot_is_not_replaced_with_current_history():
    status, release, baseline, _ = fixture()
    with pytest.raises(Rejected, match="issuance_snapshot_missing"):
        ComposedIssuanceVerifier(status, FixtureCommittedLookup({})).verify(raw(release), baseline, 40)


def test_current_history_cannot_replace_issuance_prefix():
    status, release, baseline, snapshot = fixture(prefix_length=2)
    snapshot["events"][0]["effective_at"] = 2
    with pytest.raises(Rejected, match="current_issuance_prefix"):
        run(status, release, baseline, snapshot)


def test_post_issuance_revocation_denies_current_use():
    status, release, baseline, snapshot = fixture(prefix_length=2)
    history = json.loads(status.current()[0])
    history["events"][2].update(key="new", state="revoked")
    status._history_bytes = raw(history)
    with pytest.raises(Rejected, match="issue_key_not_active"):
        run(status, release, baseline, snapshot)


def test_issuance_raw_bytes_obey_predecode_budget():
    status, release, baseline, snapshot = fixture()
    limits = base.Limits(maximum_bytes=len(raw(snapshot)) - 1)
    assert len(raw(release)) < limits.maximum_bytes
    with pytest.raises(Rejected, match="byte_limit"):
        run(status, release, baseline, snapshot, limits)


def test_full_future_prefix_is_validated_before_cutoff():
    status, release, baseline, snapshot = fixture()
    snapshot["events"][2]["effective_at"] = 30
    status._history_bytes = raw({"keys": snapshot["keys"], "events": snapshot["events"]})
    assert run(status, release, baseline, snapshot) == "r2"
    snapshot["events"][2]["sequence"] = 4
    with pytest.raises(Rejected, match="key_sequence"):
        run(status, release, baseline, snapshot)


def test_receipt_tamper_still_reaches_preserved_lifecycle_rejection():
    status, release, baseline, snapshot = fixture()
    receipt = json.loads(status.current()[2])
    receipt["prior_production_epoch"] = 99
    status._receipt_bytes = raw(receipt)
    with pytest.raises(Rejected, match="predecessor_binding"):
        run(status, release, baseline, snapshot)


@pytest.mark.parametrize("state", ["retired", "revoked", "compromised"])
def test_snapshot_signer_must_be_active_at_release_cutoff(state):
    status, release, baseline, snapshot = fixture()
    snapshot["events"][2].update(key="new", state=state)
    snapshot["head_digest"] = "new:3"
    with pytest.raises(Rejected, match="issue_key_not_active"):
        run(status, release, baseline, snapshot)


@pytest.mark.parametrize("mutation", ["different_signer", "wrong_purpose"])
def test_snapshot_signer_has_exact_identity_and_purpose(mutation):
    status, release, baseline, snapshot = fixture()
    if mutation == "different_signer":
        snapshot["signing_key"] = "old"
    else:
        snapshot["keys"][1]["purposes"].remove(SNAPSHOT_PURPOSE)
    with pytest.raises(Rejected, match="snapshot_signer_authorization"):
        run(status, release, baseline, snapshot)


@pytest.mark.parametrize("future", [False, True])
@pytest.mark.parametrize("at_issuance", [False, True])
def test_every_event_key_requires_a_declaration(future, at_issuance):
    status, release, baseline, snapshot = fixture(prefix_length=2)
    history = json.loads(status.current()[0])
    history["events"][2].update(key="undeclared", state="active", effective_at=30 if future else 16)
    status._history_bytes = raw(history)
    if at_issuance:
        snapshot.update(events=history["events"], head_digest="undeclared:3", head_sequence=3)
    with pytest.raises(Rejected, match="undeclared_event_key"):
        run(status, release, baseline, snapshot)


def test_repeated_activation_is_not_a_lifecycle_transition():
    status, release, baseline, snapshot = fixture()
    snapshot["events"][2].update(key="new", state="active")
    with pytest.raises(Rejected, match="repeated_activation"):
        run(status, release, baseline, snapshot)


def test_valid_current_history_can_extend_issuance_prefix():
    assert run(*fixture(prefix_length=2)) == "r2"


def test_coherent_current_truncation_still_cannot_remove_issuance_events():
    status, release, baseline, snapshot = fixture()
    history = json.loads(status.current()[0])
    history["events"] = history["events"][:2]
    checkpoint = json.loads(status.current()[1])
    checkpoint["key_event_count"] = 2
    predecessor = json.loads(status.predecessor())
    predecessor["key_head_sequence"] = 2
    status._history_bytes = raw(history)
    status._checkpoint_bytes = raw(checkpoint)
    status._predecessor_bytes = raw(predecessor)
    with pytest.raises(Rejected, match="current_issuance_prefix"):
        run(status, release, baseline, snapshot)


def test_current_nonselected_static_declaration_is_immutable():
    status, release, baseline, snapshot = fixture()
    history = json.loads(status.current()[0])
    history["keys"][0]["purposes"] = ["different-purpose"]
    status._history_bytes = raw(history)
    with pytest.raises(Rejected, match="current_issuance_prefix"):
        run(status, release, baseline, snapshot)


def test_legacy_release_cannot_fall_back_to_available_current_history():
    status, release, baseline, snapshot = fixture()
    del release["acceptance_authority_snapshot_digest"]
    with pytest.raises(Rejected, match="release_shape"):
        run(status, release, baseline, snapshot)


@pytest.mark.parametrize("field", ["extra", "digest", "keys", "events", "head_digest", "head_sequence", "signing_key"])
def test_snapshot_shape_is_closed_at_public_entry(field):
    status, release, baseline, snapshot = fixture()
    if field == "extra":
        snapshot[field] = "unknown"
    else:
        del snapshot[field]
    with pytest.raises(Rejected, match="issuance_snapshot_shape"):
        run(status, release, baseline, snapshot)


@pytest.mark.parametrize("input_name", ["release", "baseline", "history", "checkpoint", "receipt", "predecessor"])
def test_composed_public_entry_bounds_every_direct_byte_stream(input_name):
    status, release, baseline, snapshot = fixture()
    release_bytes = raw(release)
    excessive = b" " * 4097
    if input_name == "release":
        release_bytes = excessive
    elif input_name == "baseline":
        baseline = excessive
    else:
        setattr(status, "_" + input_name + "_bytes", excessive)
    with pytest.raises(Rejected, match="byte_limit"):
        ComposedIssuanceVerifier(status, FixtureCommittedLookup({"issuance": raw(snapshot)})).verify(release_bytes, baseline, 40)


@pytest.mark.parametrize("effective_at", [10, 16, 30])
def test_capture_to_publication_race_requires_new_complete_capture(effective_at):
    from issuance_prefix_feasibility import ProtectedIssuanceRepository

    status, release, _, snapshot = fixture(prefix_length=2, issued_at=10)
    repository = ProtectedIssuanceRepository(raw({"keys": snapshot["keys"], "events": snapshot["events"]}))
    token = repository.prepare(raw(release))
    later = json.loads(status.current()[0])
    later["events"][2]["effective_at"] = effective_at
    repository.advance_history(raw(later))
    with pytest.raises(Rejected, match="issuance_capture_stale"):
        repository.publish(token)
    assert repository.published("issuance") is None
    _, captured = repository.publish(repository.prepare(raw(release)))
    assert json.loads(captured)["head_sequence"] == 3


def test_equal_time_append_after_atomic_issuance_does_not_change_issuance_snapshot():
    from issuance_prefix_feasibility import ProtectedIssuanceRepository

    status, release, baseline, snapshot = fixture(prefix_length=2, issued_at=10)
    repository = ProtectedIssuanceRepository(raw({"keys": snapshot["keys"], "events": snapshot["events"]}))
    published_release, captured = repository.publish(repository.prepare(raw(release)))
    later = json.loads(status.current()[0])
    later["events"][2]["effective_at"] = 10
    repository.advance_history(raw(later))
    status._history_bytes = raw(later)
    assert repository.published("issuance") == (published_release, captured)
    assert ComposedIssuanceVerifier(status, repository).verify(published_release, baseline, 40) == "r2"


def test_fresh_prepare_cannot_overwrite_an_already_issued_snapshot_pair():
    from issuance_prefix_feasibility import ProtectedIssuanceRepository

    status, release, _, snapshot = fixture(prefix_length=2, issued_at=10)
    repository = ProtectedIssuanceRepository(raw({"keys": snapshot["keys"], "events": snapshot["events"]}))
    original = repository.publish(repository.prepare(raw(release)))
    repository.advance_history(status.current()[0])
    with pytest.raises(Rejected, match="immutable_issuance"):
        repository.publish(repository.prepare(raw(release)))
    assert repository.published("issuance") == original



def test_status_only_generation_change_invalidates_prepared_issuance():
    from issuance_prefix_feasibility import ProtectedIssuanceRepository

    status, release, _, _ = fixture()
    repository = ProtectedIssuanceRepository(status.current()[0])
    token = repository.prepare(raw(release))
    repository.advance_status_generation()
    with pytest.raises(Rejected, match="issuance_capture_stale"):
        repository.publish(token)
    assert repository.published("issuance") is None


def test_verifier_can_only_load_the_committed_release_snapshot_pair():
    from issuance_prefix_feasibility import ProtectedIssuanceRepository

    status, release, baseline, _ = fixture()
    repository = ProtectedIssuanceRepository(status.current()[0])
    token = repository.prepare(raw(release))
    verifier = ComposedIssuanceVerifier(status, repository)
    with pytest.raises(Rejected, match="issuance_snapshot_missing"):
        verifier.verify(raw(release), baseline, 40)
    repository.publish(token)
    assert verifier.verify(raw(release), baseline, 40) == "r2"
    release["digest"] = "different-release"
    with pytest.raises(Rejected, match="issuance_snapshot_missing"):
        verifier.verify(raw(release), baseline, 40)

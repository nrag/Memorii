from dataclasses import replace
from hashlib import sha256

import pytest

from ledger_feasibility import LedgerHead, ObservationLedger, SemanticPayload, replay


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _payload(source: str, fence: str, group: str | None, result: str, operations: tuple[str, ...] = ("op-a",)) -> SemanticPayload:
    return SemanticPayload(source, fence, group, operations, _digest(result))


def test_interleaved_group_and_source_entries_use_one_cas_chain() -> None:
    ledger = ObservationLedger()
    a_group = ledger.append(expected_head=ledger.head, terminal_kind="group", stable_identity="group:a", payload=_payload("a", "fa", "ga", "ra"), result_locator="locator:a")
    b_group = ledger.append(expected_head=ledger.head, terminal_kind="group", stable_identity="group:b", payload=_payload("b", "fb", "gb", "rb"), result_locator="locator:b")
    a_final = ledger.append(expected_head=ledger.head, terminal_kind="source_finalization", stable_identity="final:a", payload=_payload("a", "fa", None, "rfa"), result_locator="terminal:a")
    b_final = ledger.append(expected_head=ledger.head, terminal_kind="source_finalization", stable_identity="final:b", payload=_payload("b", "fb", None, "rfb"), result_locator="terminal:b")
    assert replay(ledger.entries, expected_head=ledger.head) == ledger.head
    assert [entry.generation for entry in (a_group, b_group, a_final, b_final)] == [1, 2, 3, 4]


def test_stale_cas_has_no_partial_write_and_retry_or_lost_ack_reloads() -> None:
    ledger = ObservationLedger()
    stale = ledger.head
    entry = ledger.append(expected_head=stale, terminal_kind="group", stable_identity="group:a", payload=_payload("a", "fa", "ga", "ra"), result_locator="locator:a")
    payload_b = _payload("b", "fb", "gb", "rb")
    before_failure = (ledger.head, ledger.entries)
    with pytest.raises(ValueError, match="stale"):
        ledger.append(expected_head=stale, terminal_kind="group", stable_identity="group:b", payload=payload_b, result_locator="locator:b")
    assert (ledger.head, ledger.entries) == before_failure
    assert ledger.entries == (entry,)
    retried = ledger.append(expected_head=ledger.head, terminal_kind="group", stable_identity="group:b", payload=payload_b, result_locator="locator:b")
    assert retried.generation == 2
    assert retried.revision_before == entry.revision_after
    assert replay(ledger.entries, expected_head=ledger.head) == ledger.head
    assert ledger.append(expected_head=stale, terminal_kind="group", stable_identity="group:a", payload=entry.payload, result_locator="locator:a") == entry
    before_failure = (ledger.head, ledger.entries)
    with pytest.raises(ValueError, match="changed"):
        ledger.append(expected_head=ledger.head, terminal_kind="group", stable_identity="group:a", payload=_payload("a", "fa", "ga", "changed"), result_locator="locator:a")
    assert (ledger.head, ledger.entries) == before_failure


@pytest.mark.parametrize("mutator", [
    lambda entries: entries[:-1],
    lambda entries: (entries[1], entries[0]),
    lambda entries: (*entries, entries[0]),
])
def test_replay_rejects_missing_reordered_or_duplicate_entries(mutator) -> None:
    ledger = ObservationLedger()
    ledger.append(expected_head=ledger.head, terminal_kind="group", stable_identity="group:a", payload=_payload("a", "fa", "ga", "ra"), result_locator="locator:a")
    ledger.append(expected_head=ledger.head, terminal_kind="source_finalization", stable_identity="final:a", payload=_payload("a", "fa", None, "rfa"), result_locator="terminal:a")
    with pytest.raises(ValueError):
        replay(mutator(ledger.entries), expected_head=ledger.head)


def test_replay_rejects_frozen_entry_corruption() -> None:
    ledger = ObservationLedger()
    entry = ledger.append(expected_head=ledger.head, terminal_kind="group", stable_identity="group:a", payload=_payload("a", "fa", "ga", "ra"), result_locator="locator:a")
    corrupt = replace(entry)
    object.__setattr__(corrupt, "final_delta_digest", "0" * 64)
    with pytest.raises(ValueError):
        replay((corrupt,), expected_head=ledger.head)


def test_zero_operation_source_finalization_is_valid_but_group_is_not() -> None:
    ledger = ObservationLedger()
    zero = _payload("a", "fa", None, "rfa", ())
    assert ledger.append(expected_head=ledger.head, terminal_kind="source_finalization", stable_identity="final:a", payload=zero, result_locator="terminal:a").generation == 1
    before_failure = (ledger.head, ledger.entries)
    with pytest.raises(ValueError, match="group payload"):
        ledger.append(expected_head=ledger.head, terminal_kind="group", stable_identity="group:a", payload=_payload("a", "fa", "ga", "ra", ()), result_locator="locator:a")
    assert (ledger.head, ledger.entries) == before_failure


@pytest.mark.parametrize("kind,payload", [
    ("unknown", _payload("a", "fa", None, "r")),
    ("source_finalization", _payload("a", "fa", "ga", "r")),
])
def test_invalid_terminal_kind_or_shape_is_rejected(kind, payload) -> None:
    with pytest.raises(ValueError):
        ObservationLedger().append(expected_head=LedgerHead(0, "genesis", None), terminal_kind=kind, stable_identity="x", payload=payload, result_locator="locator")


def test_append_requires_head_and_rejects_caller_assigned_coordinates() -> None:
    ledger = ObservationLedger()
    common = dict(terminal_kind="group", stable_identity="group:a", payload=_payload("a", "fa", "ga", "ra"), result_locator="locator:a")
    before = (ledger.head, ledger.entries)
    with pytest.raises(TypeError, match="expected_head"):
        ledger.append(**common)
    for key in ("revision_after", "final_delta_digest"):
        with pytest.raises(TypeError, match=key):
            ledger.append(expected_head=ledger.head, **common, **{key: "a" * 64})
    assert (ledger.head, ledger.entries) == before


@pytest.mark.parametrize("generation", [True, 1.5, "1"])
def test_head_rejects_noninteger_generation(generation) -> None:
    with pytest.raises(ValueError, match="head"):
        LedgerHead(generation, "a" * 64, "b" * 64)


def test_replay_revalidates_nested_payload_shape() -> None:
    ledger = ObservationLedger()
    entry = ledger.append(expected_head=ledger.head, terminal_kind="group", stable_identity="group:a", payload=_payload("a", "fa", "ga", "ra"), result_locator="locator:a")
    broken_payload = replace(entry.payload)
    object.__setattr__(broken_payload, "operation_ids", (1,))
    broken_entry = replace(entry)
    object.__setattr__(broken_entry, "payload", broken_payload)
    with pytest.raises(ValueError, match="payload"):
        replay((broken_entry,), expected_head=ledger.head)


def test_group_final_result_follows_assignment_without_changing_semantic_payload() -> None:
    first = ObservationLedger()
    second = ObservationLedger()
    second.append(expected_head=second.head, terminal_kind="source_finalization", stable_identity="final:earlier", payload=_payload("earlier", "f-earlier", None, "earlier", ()), result_locator="terminal:earlier")
    payload = _payload("a", "fa", "ga", "ra")
    commitment = payload.commitment()
    a = first.append(expected_head=first.head, terminal_kind="group", stable_identity="group:a", payload=payload, result_locator="locator:a")
    b = second.append(expected_head=second.head, terminal_kind="group", stable_identity="group:a", payload=payload, result_locator="locator:a")
    assert a.payload_commitment == b.payload_commitment == commitment
    assert a.revision_after != b.revision_after
    assert a.final_delta_digest != b.final_delta_digest
    assert a.result_digest != b.result_digest
    assert a.result_digest != payload.precommit_result_digest
    assert replay(first.entries, expected_head=first.head) == first.head
    assert replay(second.entries, expected_head=second.head) == second.head


@pytest.mark.parametrize("change", ["result_locator", "terminal_kind"])
def test_duplicate_identity_rejects_changed_immutable_coordinates(change) -> None:
    ledger = ObservationLedger()
    original = _payload("a", "fa", "ga", "ra")
    ledger.append(expected_head=ledger.head, terminal_kind="group", stable_identity="same", payload=original, result_locator="locator:a")
    before = (ledger.head, ledger.entries)
    if change == "result_locator":
        with pytest.raises(ValueError, match="changed content"):
            ledger.append(expected_head=ledger.head, terminal_kind="group", stable_identity="same", payload=original, result_locator="locator:other")
    else:
        with pytest.raises(ValueError, match="changed content"):
            ledger.append(expected_head=ledger.head, terminal_kind="source_finalization", stable_identity="same", payload=replace(original, transaction_group_id=None), result_locator="locator:a")
    assert (ledger.head, ledger.entries) == before


def test_replay_checks_contiguity_separately_from_expected_tail() -> None:
    ledger = ObservationLedger()
    for source in ("a", "b"):
        ledger.append(expected_head=ledger.head, terminal_kind="source_finalization", stable_identity="final:" + source, payload=_payload(source, "f" + source, None, source, ()), result_locator="terminal:" + source)
    with pytest.raises(ValueError, match="not contiguous"):
        replay(tuple(reversed(ledger.entries)))
    with pytest.raises(ValueError, match="does not reach persisted head"):
        replay(ledger.entries[:-1], expected_head=ledger.head)


def test_source_result_precedes_assignment_under_different_heads() -> None:
    first, second = ObservationLedger(), ObservationLedger()
    second.append(expected_head=second.head, terminal_kind="source_finalization", stable_identity="final:earlier", payload=_payload("earlier", "f-earlier", None, "earlier", ()), result_locator="terminal:earlier")
    payload = _payload("a", "fa", None, "ra", ())
    a = first.append(expected_head=first.head, terminal_kind="source_finalization", stable_identity="final:a", payload=payload, result_locator="terminal:a")
    b = second.append(expected_head=second.head, terminal_kind="source_finalization", stable_identity="final:a", payload=payload, result_locator="terminal:a")
    assert a.payload_commitment == b.payload_commitment == payload.commitment()
    assert a.result_digest == b.result_digest == payload.precommit_result_digest
    assert a.revision_after != b.revision_after
    assert a.final_delta_digest != b.final_delta_digest

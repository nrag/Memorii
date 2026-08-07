"""Focused closed-CTV collection regressions."""

from __future__ import annotations

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    decode_typed_value,
    encode_typed_value,
)


@pytest.mark.parametrize("factory", (frozenset, set))
def test_ctv_map_collection_round_trip_preserves_canonical_bytes(factory) -> None:
    raw = b'{"$type":"frozenset","items":[]}'
    assert decode_typed_value(raw) == frozenset()
    # Maps cannot be created by native set syntax, so use the hand-authored CTV member form.
    member = (
        b'{"$type":"map","entries":['
        b'["items",{"$type":"list","items":["value"]}],'
        b'["outer",{"$type":"map","entries":[["inner","value"]]}],'
        b'["tags",{"$type":"set","items":["tag"]}]'
        b"]}"
    )
    raw = b'{"$type":"' + (b"frozenset" if factory is frozenset else b"set") + b'","items":[' + member + b"]}"
    decoded = decode_typed_value(raw)
    assert isinstance(decoded, factory)
    assert encode_typed_value(decoded) == raw
    mapped = next(iter(decoded))
    assert hash(mapped) == hash(mapped)
    with pytest.raises(TypeError):
        mapped["outer"] = "mutated"
    assert mapped["outer"]["inner"] == "value"
    with pytest.raises(TypeError):
        mapped["outer"]["inner"] = "mutated"
    with pytest.raises(TypeError):
        mapped["items"].append("mutated")
    with pytest.raises(TypeError):
        mapped["tags"].add("mutated")
    for wrapped in (mapped, mapped["items"], mapped["tags"]):
        with pytest.raises((AttributeError, TypeError)):
            object.__setattr__(wrapped, "_values", ())
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(mapped, "injected", "mutated")
    assert mapped in decoded
    assert encode_typed_value(decoded) == raw


def test_ctv_ordinary_maps_remain_mutable_dicts_and_collection_order_rejects() -> None:
    ordinary = decode_typed_value(encode_typed_value({"plain": "map"}))
    assert type(ordinary) is dict
    ordinary["next"] = "value"
    member_a = b'{"$type":"map","entries":[["a","one"]]}'
    member_b = b'{"$type":"map","entries":[["b","two"]]}'
    reversed_raw = (
        b'{"$type":"frozenset","items":['
        + member_b
        + b"," + member_a + b"]}"
    )
    with pytest.raises(CanonicalTypedValueError, match="canonical"):
        decode_typed_value(reversed_raw)
    duplicate_raw = (
        b'{"$type":"set","items":['
        + member_a
        + b"," + member_a + b"]}"
    )
    with pytest.raises(CanonicalTypedValueError, match="canonical"):
        decode_typed_value(duplicate_raw)


def test_ctv_set_members_are_composed_immutable_wrappers_for_every_container_tag() -> None:
    map_member = decode_typed_value(
        b'{"$type":"frozenset","items":[{"$type":"map","entries":[["key","value"]]}]}'
    )
    mapped = next(iter(map_member))
    with pytest.raises(TypeError):
        dict.__setitem__(mapped, "key", "mutated")
    list_member_raw = b'{"$type":"frozenset","items":[{"$type":"list","items":["value"]}]}'
    list_member = next(iter(decode_typed_value(list_member_raw)))
    with pytest.raises(TypeError):
        list.append(list_member, "mutated")
    assert encode_typed_value(frozenset({list_member})) == list_member_raw
    tuple_set_raw = b'{"$type":"frozenset","items":[{"$type":"tuple","items":[{"$type":"set","items":["tag"]}]}]}'
    tuple_set_member = next(iter(decode_typed_value(tuple_set_raw)))
    with pytest.raises(TypeError):
        set.add(tuple_set_member[0], "mutated")
    assert encode_typed_value(frozenset({tuple_set_member})) == tuple_set_raw


def test_ctv_tag_distinct_collection_members_do_not_collapse_by_builtin_equality() -> None:
    raw = (
        b'{"$type":"frozenset","items":['
        b'{"$type":"frozenset","items":["tag"]},'
        b'{"$type":"list","items":["value"]},'
        b'{"$type":"set","items":["tag"]},'
        b'{"$type":"tuple","items":["value"]}'
        b"]}"
    )
    decoded = decode_typed_value(raw)
    assert len(decoded) == 4
    assert encode_typed_value(decoded) == raw


def test_ctv_wrapper_equality_and_hashing_remain_tag_sensitive() -> None:
    list_raw = b'{"$type":"frozenset","items":[{"$type":"list","items":["value"]}]}'
    list_member = next(iter(decode_typed_value(list_raw)))
    equal_list_member = next(iter(decode_typed_value(list_raw)))
    assert list_member == equal_list_member
    assert hash(list_member) == hash(equal_list_member)
    assert list_member != ("value",)
    assert list_member != ("value",)
    set_raw = b'{"$type":"frozenset","items":[{"$type":"set","items":["tag"]}]}'
    set_member = next(iter(decode_typed_value(set_raw)))
    assert set_member != frozenset({"tag"})
    assert frozenset({"tag"}) != set_member
    map_raw = b'{"$type":"frozenset","items":[{"$type":"map","entries":[["key","value"]]}]}'
    map_member = next(iter(decode_typed_value(map_raw)))
    assert map_member != (("key", "value"),)
    assert map_member != (("key", "value"),)
    assert encode_typed_value(frozenset({list_member, set_member, map_member})) == (
        b'{"$type":"frozenset","items":['
        b'{"$type":"list","items":["value"]},'
        b'{"$type":"map","entries":[["key","value"]]},'
        b'{"$type":"set","items":["tag"]}'
        b"]}"
    )


@pytest.mark.parametrize("tag", (b"set", b"frozenset"))
def test_ctv_bool_integer_collisions_preserve_each_encoded_member(tag: bytes) -> None:
    raw = b'{"$type":"' + tag + b'","items":[false,true,{"$type":"integer","value":"0"},{"$type":"integer","value":"1"}]}'
    decoded = decode_typed_value(raw)
    assert len(decoded) == 4
    assert encode_typed_value(decoded) == raw


def test_ctv_nested_tuple_and_map_bool_integer_collisions_are_tag_aware() -> None:
    raw = (
        b'{"$type":"frozenset","items":['
        b'{"$type":"map","entries":[["value",true]]},'
        b'{"$type":"map","entries":[["value",{"$type":"integer","value":"1"}]]},'
        b'{"$type":"tuple","items":[true]},'
        b'{"$type":"tuple","items":[{"$type":"integer","value":"1"}]}'
        b"]}"
    )
    decoded = decode_typed_value(raw)
    assert len(decoded) == 4
    assert encode_typed_value(decoded) == raw


def test_ctv_nested_set_and_frozenset_bool_integer_collisions_are_tag_aware() -> None:
    raw = (
        b'{"$type":"frozenset","items":['
        b'{"$type":"frozenset","items":[false,{"$type":"integer","value":"0"}]},'
        b'{"$type":"set","items":[true,{"$type":"integer","value":"1"}]}'
        b"]}"
    )
    decoded = decode_typed_value(raw)
    assert len(decoded) == 2
    assert encode_typed_value(decoded) == raw

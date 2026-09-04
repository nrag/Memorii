"""Conflict-replan delivery coordinate contract proof."""

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    derive_composite_child_delivery_id,
    derive_conflict_replan_delivery_id,
    is_reserved_composite_delivery_id,
    is_reserved_conflict_replan_delivery_id,
)
from memorii.core.provider.classifier import make_event
from memorii.core.provider.models import ProviderEvent, ProviderOperation


def test_replan_coordinate_is_domain_separated_and_deterministic() -> None:
    first = derive_conflict_replan_delivery_id("event:one")
    second = derive_conflict_replan_delivery_id("event:one")
    other = derive_conflict_replan_delivery_id("event:two")
    assert first == second
    assert first != other
    assert first.startswith("conflict-replan:v1:")
    assert is_reserved_conflict_replan_delivery_id(first)
    assert not is_reserved_composite_delivery_id(first)
    # The coordinate never embeds the public parent id: a leaked parent string
    # would make the internal coordinate guessable by a host.
    assert "event:one" not in first


def test_replan_coordinate_is_distinct_from_composite_children() -> None:
    parent = "event:one"
    assert derive_conflict_replan_delivery_id(parent) != (
        derive_composite_child_delivery_id(parent, "clarification-replan")
    )


def test_public_provider_events_reject_reserved_replan_coordinates() -> None:
    reserved = derive_conflict_replan_delivery_id("event:one")
    with pytest.raises(ValueError, match="reserved conflict-replan coordinate"):
        ProviderEvent(
            event_id=reserved,
            operation=ProviderOperation.MEMORY_WRITE_USER,
            content="text",
        )


def test_replan_coordinate_does_not_change_the_public_event() -> None:
    event = make_event(
        event_id="event:one",
        operation=ProviderOperation.MEMORY_WRITE_USER,
        content="text",
    )
    derived = derive_conflict_replan_delivery_id(event.event_id)
    assert event.event_id == "event:one"
    assert derived != event.event_id

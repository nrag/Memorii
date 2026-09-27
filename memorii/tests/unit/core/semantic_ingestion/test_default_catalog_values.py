"""Closed literal-value behavior for the default catalog."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from memorii.core.semantic_ingestion.default_catalog_values import (
    DEFAULT_CATALOG_VALUE_POLICIES,
    CatalogLocalDate,
    CatalogMoney,
    CatalogStatusText,
    CatalogTimeInterval,
    CatalogValuePolicyDeclaration,
)


def test_local_date_retains_date_and_source_calendar_without_timezone_conversion() -> None:
    value = CatalogLocalDate(value=date(2026, 10, 3), source_calendar="gregorian")

    assert value.model_dump(mode="json") == {
        "value": "2026-10-03", "source_calendar": "gregorian",
    }


def test_time_interval_requires_explicit_open_bounds_and_aware_datetimes() -> None:
    start = datetime(2026, 10, 3, 9, tzinfo=UTC)
    end = datetime(2026, 10, 3, 10, tzinfo=UTC)

    assert CatalogTimeInterval(
        start=start, end=end, start_bound="closed", end_bound="exclusive",
    ).end == end
    assert CatalogTimeInterval(
        start=None, end=end, start_bound="open", end_bound="exclusive",
    ).start is None
    with pytest.raises(ValueError, match="timezone-aware"):
        CatalogTimeInterval(
            start=datetime(2026, 10, 3, 9), end=end,
            start_bound="closed", end_bound="exclusive",
        )
    with pytest.raises(ValueError, match="inconsistent"):
        CatalogTimeInterval(
            start=None, end=end, start_bound="closed", end_bound="exclusive",
        )
    with pytest.raises(ValueError, match="later than start"):
        CatalogTimeInterval(
            start=end, end=start, start_bound="closed", end_bound="exclusive",
        )


@pytest.mark.parametrize("amount", ("1e3", "01.00", "NaN", "-0", "1."))
def test_money_rejects_noncanonical_decimal_forms(amount: str) -> None:
    with pytest.raises(ValueError, match="canonical"):
        CatalogMoney(decimal_amount=amount, currency="USD")


@pytest.mark.parametrize("currency", ("usd", "US", "USDD", "123"))
def test_money_requires_iso_4217_shaped_currency(currency: str) -> None:
    with pytest.raises(ValueError, match="canonical"):
        CatalogMoney(decimal_amount="12.50", currency=currency)


def test_money_preserves_exact_decimal_and_currency() -> None:
    assert CatalogMoney(decimal_amount="12.50", currency="USD").model_dump() == {
        "decimal_amount": "12.50", "currency": "USD",
    }


@pytest.mark.parametrize(
    ("policy", "source", "canonical"),
    (
        ("work_item_status", "Completed", "done"),
        ("work_item_status", "to   do", "todo"),
        ("opportunity_stage", "Closed Won", "won"),
        ("opportunity_stage", "NEGOTIATING", "negotiation"),
    ),
)
def test_status_text_uses_only_versioned_canonical_values_and_aliases(
    policy: str, source: str, canonical: str,
) -> None:
    result = CatalogStatusText.parse(value_policy_id=policy, source_text=source)
    assert result.canonical_value == canonical


def test_status_text_rejects_unknown_or_cross_policy_values() -> None:
    with pytest.raises(ValueError, match="unresolved"):
        CatalogStatusText.parse(value_policy_id="work_item_status", source_text="almost done")
    with pytest.raises(ValueError, match="unresolved"):
        CatalogStatusText.parse(value_policy_id="opportunity_stage", source_text="blocked")


def test_status_policy_digest_changes_with_alias_or_vocabulary() -> None:
    current = DEFAULT_CATALOG_VALUE_POLICIES["work_item_status"]
    changed_alias = CatalogValuePolicyDeclaration.create(
        value_policy_id="work_item_status", codec_id="status_text_v1",
        canonical_values=current.canonical_values,
        aliases=(*current.aliases, ("finished", "done")),
    )
    changed_vocabulary = CatalogValuePolicyDeclaration.create(
        value_policy_id="work_item_status", codec_id="status_text_v1",
        canonical_values=(*current.canonical_values, "paused"),
        aliases=current.aliases,
    )

    assert changed_alias.policy_digest != current.policy_digest
    assert changed_vocabulary.policy_digest != current.policy_digest


def test_status_value_rejects_stale_policy_binding() -> None:
    with pytest.raises(ValueError, match="canonical"):
        CatalogStatusText(
            value_policy_id="work_item_status",
            value_policy_digest="0" * 64,
            canonical_value="done",
        )


def test_status_value_decodes_with_its_historical_policy_after_active_policy_changes() -> None:
    historical = DEFAULT_CATALOG_VALUE_POLICIES["work_item_status"]
    value = CatalogStatusText.parse(
        value_policy_id="work_item_status", source_text="completed",
    )
    active = CatalogValuePolicyDeclaration.create(
        value_policy_id="work_item_status", codec_id="status_text_v1",
        canonical_values=(*historical.canonical_values, "paused"),
        aliases=(*historical.aliases, ("on hold", "paused")),
    )

    decoded = CatalogStatusText.decode(
        value.model_dump(mode="json"), historical_policies=(active, historical),
    )

    assert decoded == value
    with pytest.raises(ValueError, match="canonical"):
        CatalogStatusText.decode(
            {**value.model_dump(mode="json"), "value_policy_digest": "0" * 64},
            historical_policies=(active, historical),
        )


def test_caller_created_status_policy_cannot_authorize_current_value_creation() -> None:
    current = DEFAULT_CATALOG_VALUE_POLICIES["work_item_status"]
    unselected = CatalogValuePolicyDeclaration.create(
        value_policy_id="work_item_status", codec_id="status_text_v1",
        canonical_values=(*current.canonical_values, "paused"),
        aliases=(*current.aliases, ("on hold", "paused")),
    )

    with pytest.raises(ValueError, match="canonical"):
        CatalogStatusText(
            value_policy_id="work_item_status",
            value_policy_digest=unselected.policy_digest,
            canonical_value="paused",
        )
    with pytest.raises(ValueError, match="unresolved"):
        CatalogStatusText.parse(
            value_policy_id="work_item_status", source_text="on hold",
        )

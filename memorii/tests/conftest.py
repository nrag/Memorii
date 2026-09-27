"""Test selection controls shared by the Memorii test suite."""

from __future__ import annotations

import os

import pytest

_INSTALLED_CATALOG_MARKER = "default_catalog_installed"
_INSTALLED_CATALOG_SHARD_OPTION = "--default-catalog-installed-shard"
_INSTALLED_CATALOG_SHARD_ENV = "MEMORII_DEFAULT_CATALOG_INSTALLED_SHARD"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("memorii")
    group.addoption(
        _INSTALLED_CATALOG_SHARD_OPTION,
        action="store",
        default=os.environ.get(_INSTALLED_CATALOG_SHARD_ENV),
        metavar="INDEX/TOTAL",
        help=(
            "run one 1-indexed shard of the opt-in installed default-catalog "
            "matrix (for example: 1/4); defaults from "
            f"{_INSTALLED_CATALOG_SHARD_ENV}"
        ),
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keep multi-minute installed rows out of ordinary unit-suite runs."""
    raw_shard = config.getoption("default_catalog_installed_shard")
    shard = _parse_installed_catalog_shard(raw_shard) if raw_shard else None
    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if item.get_closest_marker(_INSTALLED_CATALOG_MARKER) is None:
            selected.append(item)
            continue
        if shard is not None and _is_installed_catalog_shard_member(item, *shard):
            selected.append(item)
        else:
            deselected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


def _parse_installed_catalog_shard(value: object) -> tuple[int, int]:
    if not isinstance(value, str):
        raise pytest.UsageError(
            f"{_INSTALLED_CATALOG_SHARD_OPTION} must have form INDEX/TOTAL"
        )
    parts = value.split("/", maxsplit=1)
    if len(parts) != 2:
        raise pytest.UsageError(
            f"{_INSTALLED_CATALOG_SHARD_OPTION} must have form INDEX/TOTAL"
        )
    try:
        index, total = (int(part) for part in parts)
    except ValueError as exc:
        raise pytest.UsageError(
            f"{_INSTALLED_CATALOG_SHARD_OPTION} must have form INDEX/TOTAL"
        ) from exc
    if total < 1 or not 1 <= index <= total:
        raise pytest.UsageError(
            f"{_INSTALLED_CATALOG_SHARD_OPTION} requires 1 <= INDEX <= TOTAL"
        )
    return index, total


def _is_installed_catalog_shard_member(
    item: pytest.Item, index: int, total: int,
) -> bool:
    row = getattr(item, "callspec", None)
    parameters = getattr(row, "params", {})
    catalog_row = parameters.get("row")
    relation_id = getattr(catalog_row, "relation_id", None)
    if not isinstance(relation_id, str):
        raise pytest.UsageError(
            "default_catalog_installed tests must be parametrized with a row"
        )
    # Stable relation ordering makes independent CI/manual processes disjoint.
    from memorii.core.semantic_ingestion.default_catalog_corpus import (
        load_default_catalog_acceptance_corpus,
    )

    relation_ids = tuple(
        sorted(catalog_row.relation_id for catalog_row in load_default_catalog_acceptance_corpus().rows)
    )
    return relation_ids.index(relation_id) % total == index - 1

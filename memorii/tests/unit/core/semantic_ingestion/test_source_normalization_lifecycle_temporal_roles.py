"""Role-specific lifecycle temporal authority selection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from memorii.core.semantic_ingestion.source_normalization_stage import (
    _lifecycle_temporal_consensus_by_construction_role,
)


def _core(*roles: str) -> object:
    return SimpleNamespace(
        source_alignment=SimpleNamespace(
            temporal_attachment_consensus=tuple(
                SimpleNamespace(
                    operation_id="operation", temporal_role=role, consensus_digest=role,
                )
                for role in roles
            )
        )
    )


@pytest.mark.parametrize(
    ("kind", "roles", "expected"),
    (
        ("correction", ("corrected", "replacement"), ("replacement", "transition")),
        ("retraction", ("retracted",), ("transition",)),
    ),
)
def test_lifecycle_authority_uses_each_canonical_temporal_role_once(
    kind: str, roles: tuple[str, ...], expected: tuple[str, ...],
) -> None:
    selected = _lifecycle_temporal_consensus_by_construction_role(
        core=_core(*roles), operation_id="operation", kind=kind,
    )
    assert tuple(role for role, _consensus in selected) == expected
    assert tuple(consensus.temporal_role for _role, consensus in selected) == (
        ("replacement", "corrected") if kind == "correction" else ("retracted",)
    )


@pytest.mark.parametrize(
    ("kind", "roles"),
    (("correction", ("replacement",)), ("retraction", ("replacement",))),
)
def test_lifecycle_authority_denies_missing_canonical_temporal_role(
    kind: str, roles: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="temporal consensus"):
        _lifecycle_temporal_consensus_by_construction_role(
            core=_core(*roles), operation_id="operation", kind=kind,
        )

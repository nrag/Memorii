from __future__ import annotations

from itertools import combinations

import pytest
from memorii.core.provider import factory as provider_factory
from memorii.core.work_state.service import WorkStateService


def test_production_factory_constructs_only_source_admission_dependencies() -> None:
    work_states = WorkStateService()
    service = provider_factory.build_provider_memory_service_from_env(
        work_state_service=work_states,
    )
    assert service._memory_evolution_service is None
    assert not hasattr(service, "_evolution_coordinator")


def test_production_factory_exposes_no_reconciliation_path() -> None:
    service = provider_factory.build_provider_memory_service_from_env()
    assert service.reconcile_memory_evolution() == []


@pytest.mark.parametrize(
    "present",
    tuple(
        frozenset(value)
        for size in range(1, 4)
        for value in combinations(
            (
                "identity_lineage_atomic_store",
                "identity_lineage_tenant_partition_id",
                "identity_lineage_grant_provider",
                "authenticated_ingress_resolver",
            ),
            size,
        )
    ),
)
def test_identity_lineage_factory_rejects_every_partial_dependency_set(
    present: frozenset[str],
) -> None:
    store = type(
        "Store",
        (),
        {
            "semantic_replay_state": lambda self: object(),
            "lineage_audit_scope_event_ids": lambda self, **kwargs: frozenset(),
        },
    )()
    values = {
        "identity_lineage_atomic_store": store,
        "identity_lineage_tenant_partition_id": "tenant",
        "identity_lineage_grant_provider": lambda _: None,
        "authenticated_ingress_resolver": object(),
    }

    with pytest.raises(ValueError, match="audit composition is incomplete"):
        provider_factory.build_provider_memory_service_from_env(
            **{key: value for key, value in values.items() if key in present}
        )

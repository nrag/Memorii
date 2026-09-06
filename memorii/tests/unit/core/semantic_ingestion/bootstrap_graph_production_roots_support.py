"""Shared construction helpers for the split production-root suites.

Moved verbatim from the former monolithic production-roots module;
symbols carry public names because the family modules and the V3
process runner import them across module boundaries.
"""



from __future__ import annotations

from pathlib import Path

from memorii.core.filesystem_storage.bundle import (
    build_filesystem_provider as _production_filesystem_provider,
)
from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.provider.factory import (
    build_provider_memory_service_from_env as _production_factory_provider,
)
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.bootstrap_graph_host import (
    BootstrapGraphHostBundleBuilder,
    ScenarioBootstrapGraphHostBundle,
)
from memorii.core.semantic_ingestion.contracts import (
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
)
from memorii.integrations.hermes_provider import (
    HermesMemoryProvider as _ProductionHermesMemoryProvider,
)
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphAuthorityProviderV3,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    _built_in_local_capability,
    _v3_normalization_host_builder,
)

GRAPH_SCENARIO_BEHAVIOR = {
    "initial_attempt": "normal_success",
    "successor_attempt": "resolved_conflict",
    "reused_committed": "reused_committed",
    "reused_final": "reused_final",
    "reused_unfinished": "reused_unfinished",
    "replacement": "resolved_conflict",
    "epoch_zero": "normal_success",
    "lease_renewed": "lease_renewed",
    "lease_reclaimed": "lease_reclaimed",
    "writer_changed": "writer_changed",
    "writer_unavailable": "writer_unavailable",
    "pre_cas_scope_revoked": "scope_revoked",
    "unrelated_conflict": "unrelated_conflict",
    "related_conflict": "resolved_conflict",
    "partial_commit": "partial_commit",
    "durable_retry": "durable_retry",
    "finalized_failure": "exhausted_conflict",
    "success_finalization": "normal_success",
    "terminal_locator": "terminal_locator",
    "lost_ack": "lost_ack",
    "reopen": "normal_success",
    "mixed_version": "mixed_version",
    "rollback": "rollback",
    "coordinator_removed": "coordinator_removed",
    "authority_omitted": "authority_omitted",
    # These rows retain the native V3 progress closure as the observable.
    # They deliberately reuse the production boundary behaviors rather than
    # introduce a scenario-only implementation path.
    "source_progress_initial": "normal_success",
    "source_progress_related_conflict": "real_related_conflict",
    "source_progress_lost_ack": "lost_ack",
    "source_progress_reclaimed_lease": "lease_reclaimed",
}


class RemovedBootstrapGraphHostBundleBuilder:
    """Build the private negative-test host with no graph coordinator authority."""

    def build(self, *, atomic_store: object) -> ScenarioBootstrapGraphHostBundle:
        return ScenarioBootstrapGraphHostBundle(
            atomic_store=atomic_store,
            authority_provider=None,
        )


def provider_service(**kwargs) -> ProviderMemoryService:
    graph_builder = kwargs.pop("bootstrap_graph_host_bundle_builder", None)
    if graph_builder is None:
        return ProviderMemoryService(**kwargs)
    kwargs["host_bootstrap_capability"] = _built_in_local_capability(
        scenario_test=True
    )
    return ProviderMemoryService._from_scenario_test_host(
        bootstrap_graph_host_bundle_builder=graph_builder,
        **kwargs,
    )


def build_provider_memory_service_from_env(**kwargs) -> ProviderMemoryService:
    graph_builder = kwargs.pop("bootstrap_graph_host_bundle_builder", None)
    if graph_builder is None:
        return _production_factory_provider(**kwargs)
    return provider_service(
        bootstrap_graph_host_bundle_builder=graph_builder,
        **kwargs,
    )


def build_filesystem_provider(storage_root, **kwargs) -> ProviderMemoryService:
    graph_builder = kwargs.pop("bootstrap_graph_host_bundle_builder", None)
    if graph_builder is None:
        return _production_filesystem_provider(storage_root, **kwargs)
    # The graph-host composition must keep the filesystem root's durable
    # memory plane: a reopened service over the same root reloads the
    # retained recovery and graph terminal instead of starting empty.
    if "memory_plane" not in kwargs:
        kwargs["memory_plane"] = MemoryPlaneService(
            record_store=JsonlMemoryPlaneStore(Path(storage_root) / "memory_plane")
        )
    return provider_service(
        bootstrap_graph_host_bundle_builder=graph_builder,
        **kwargs,
    )


def hermes_provider(*, service=None, **kwargs):
    graph_builder = kwargs.pop("bootstrap_graph_host_bundle_builder", None)
    if service is not None:
        return _ProductionHermesMemoryProvider(service=service)
    if graph_builder is None:
        return _ProductionHermesMemoryProvider(**kwargs)
    return _ProductionHermesMemoryProvider(
        service=provider_service(
            bootstrap_graph_host_bundle_builder=graph_builder,
            **kwargs,
        )
    )


def graph_host_bundle_builders() -> tuple[object, BootstrapGraphHostBundleBuilder]:
    normalization, _calls = _v3_normalization_host_builder(
        proposal=ProviderSemanticProposal(abstained=True)
    )
    graph = BootstrapGraphHostBundleBuilder(
        authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
            successful_calls=[]
        )
    )
    return normalization, graph


def graph_fact_proposal(group_count: int = 1) -> ProviderSemanticProposal:
    assertion = "Atlas owner is Bob."
    facts = (
        ProviderFact(
            local_id="owner", predicate_id="owner_is", subject_entity_ref="atlas",
            object=ProviderEntityObject(entity_ref="bob"),
            assertion_quote=assertion, predicate_anchor_quote="owner",
            polarity="positive", commitment="asserted",
        ),
        ProviderFact(
            local_id="owned-by", predicate_id="owner_is", subject_entity_ref="bob",
            object=ProviderEntityObject(entity_ref="atlas"),
            assertion_quote=assertion, predicate_anchor_quote="Bob",
            polarity="positive", commitment="asserted",
        ),
        ProviderFact(
            local_id="managed-by", predicate_id="owner_is", subject_entity_ref="atlas",
            object=ProviderEntityObject(entity_ref="bob"),
            assertion_quote=assertion, predicate_anchor_quote="owner",
            polarity="positive", commitment="asserted",
        ),
    )
    return ProviderSemanticProposal(
        mentions=(
            ProviderMention(
                local_id="atlas", mention_quote="Atlas",
                mention_context_quote=assertion,
            ),
            ProviderMention(
                local_id="bob", mention_quote="Bob",
                mention_context_quote=assertion,
            ),
        ),
        facts=facts[:group_count],
        abstained=False,
    )

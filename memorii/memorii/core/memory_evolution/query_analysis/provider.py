"""Prompt-backed structured query provider."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.predicates import PredicateRegistry
from memorii.core.memory_evolution.query_analysis.contracts import (
    StructuredQueryProviderError,
    StructuredQueryVisibleContext,
    VisibleAnchorCatalogEntry,
    VisibleEntityCatalogEntry,
    VisiblePredicateCatalogEntry,
)
from memorii.core.memory_evolution.query_analysis.validation import query_scope_kind
from memorii.core.memory_evolution.query_graph import GraphConstraintOperator
from memorii.core.memory_evolution.temporal_contracts import (
    TemporalAnchorCatalog,
    TemporalEntityCandidate,
    TemporalInterpretationProposal,
)
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.prompts.runtime_manifest import PromptOwner


class PromptBackedStructuredQueryAnalysisProvider:
    """Model-facing semantic parser whose output remains an untrusted proposal."""

    prompt_ref = "structured_query_analysis:v1"

    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        predicate_registry: PredicateRegistry | None = None,
    ) -> None:
        self._runner = runner
        self._contract = registry.load(
            self.prompt_ref,
            owner=PromptOwner.STRUCTURED_QUERY_ANALYSIS_PROVIDER,
        )
        self._predicates = predicate_registry or PredicateRegistry()

    def __call__(
        self,
        *,
        query: str,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        request_scope: MemoryScope,
    ) -> TemporalInterpretationProposal:
        context = self._visible_context(
            language=language,
            reference_time=reference_time,
            entity_candidates=entity_candidates,
            anchor_catalog=anchor_catalog,
            request_scope=request_scope,
        )
        request_digest = hashlib.sha256(
            json.dumps(
                {"query": query, "context": context.model_dump(mode="json")},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:20]
        result = self._runner.run(
            contract=self._contract,
            variables={"query": query, "context_json": context.model_dump(mode="json")},
            request_id=f"structured-query:{request_digest}",
            metadata={"language": language, "scope_kind": context.scope_kind.value},
        )
        if not result.success or result.output is None:
            raise StructuredQueryProviderError(
                f"structured query provider failed with {result.failure_mode or 'unknown_failure'}"
            )
        return TemporalInterpretationProposal.model_validate(result.output)

    def _visible_context(
        self,
        *,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        request_scope: MemoryScope,
    ) -> StructuredQueryVisibleContext:
        return StructuredQueryVisibleContext(
            language=language,
            reference_time=reference_time,
            scope_kind=query_scope_kind(request_scope),
            entities=[
                VisibleEntityCatalogEntry(
                    entity_id=candidate.entity_id,
                    names=list(candidate.names),
                    entity_type=candidate.entity_type,
                )
                for candidate in entity_candidates
                if request_scope.can_read(candidate.scope)
            ],
            temporal_anchors=[
                VisibleAnchorCatalogEntry(anchor_id=anchor.anchor_id, names=list(anchor.names))
                for anchor in anchor_catalog.anchors
                if request_scope.can_read(anchor.scope)
            ],
            predicates=[
                VisiblePredicateCatalogEntry(
                    predicate_id=policy.predicate_id,
                    description=policy.description,
                    value_type=policy.value_type.value,
                )
                for policy in sorted(self._predicates.all(), key=lambda item: item.predicate_id)
            ],
            graph_operators=sorted(operator.value for operator in GraphConstraintOperator),
        )

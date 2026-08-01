from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memorii.core.benchmark.memory_evolution_runtime.ingestion import (
    IngestionContext,
    ingest_surface_observation,
)
from memorii.core.benchmark.memory_evolution_runtime.ingestion_oracle import (
    audit_ingestion_prefix,
)
from memorii.core.benchmark.memory_evolution_sim import LatentGraphScenario
from memorii.core.memory_evolution.extraction import models_from_llm_output
from memorii.core.memory_evolution.extraction_contracts import (
    MemoryExtractionProposal,
)
from memorii.core.memory_evolution.models import (
    ExtractionRun,
    ExtractionRunStatus,
    FinalExtractionSource,
    ProviderAttemptStatus,
    SourceObservation,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.domain.enums import SourceType
from tests.support.memory_evolution_provider_harness import (
    MemoryEvolutionProviderHarness as ProviderMemoryService,
)

_FIXTURE = Path(__file__).parents[3] / "fixtures" / "memory_evolution_runtime" / "captured_ingestion_proposals.json"
_LONG_HORIZON_FIXTURE = (
    Path(__file__).parents[3] / "fixtures" / "memory_evolution_runtime" / "captured_long_horizon_replay.json"
)


class _RecordedProposalExtractor:
    provider = "recorded_artifact"
    model = "recorded-model"
    prompt_hash = "recorded-prompt"

    def __init__(self, proposals: dict[str, dict[str, object] | None]) -> None:
        self._proposals = proposals

    def extract(
        self,
        observations: list[SourceObservation],
    ) -> MemoryExtractionProposal:
        if not observations:
            return MemoryExtractionProposal(
                run=ExtractionRun(
                    extraction_run_id="replay:abstention",
                    provider=self.provider,
                    model=self.model,
                    prompt_hash=self.prompt_hash,
                    input_source_ids=[],
                    status=ExtractionRunStatus.ABSTAINED,
                    provider_attempt_status=ProviderAttemptStatus.NOT_ATTEMPTED,
                    final_output_source=FinalExtractionSource.NONE,
                )
            )
        if len(observations) != 1:
            raise AssertionError("recorded replay expects at most one source observation")
        observation = observations[0]
        event_id = observation.source_id.removeprefix("tx:benchmark:runtime:")
        if event_id not in self._proposals:
            raise AssertionError(f"missing recorded proposal for {event_id}")
        output = self._proposals[event_id]
        run_id = f"replay:{event_id}"
        if output is None:
            return MemoryExtractionProposal(
                run=ExtractionRun(
                    extraction_run_id=run_id,
                    provider=self.provider,
                    model=self.model,
                    prompt_hash=self.prompt_hash,
                    input_source_ids=[observation.source_id],
                    status=ExtractionRunStatus.ABSTAINED,
                    provider_attempt_status=ProviderAttemptStatus.SUCCEEDED,
                    final_output_source=FinalExtractionSource.PRIMARY,
                )
            )
        return models_from_llm_output(
            run_id=run_id,
            provider=self.provider,
            model=self.model,
            prompt_hash=self.prompt_hash,
            observations=observations,
            output=output,
        )


@dataclass(frozen=True)
class _ReplayDivergence:
    scenario_id: str
    event_id: str
    issues: tuple[str, ...]

    def describe(self) -> str:
        return f"{self.scenario_id}:{self.event_id}:" + ",".join(self.issues)


def _cases() -> dict[str, dict[str, Any]]:
    rows = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return {str(row["case_id"]): row for row in rows}


def _compile(*, source_id: str, text: str, proposal: dict[str, object]):
    observation = SourceObservation(
        source_id=source_id,
        text=text,
        source_type=SourceType.USER,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return models_from_llm_output(
        run_id=f"run:{source_id}",
        provider="recorded",
        model="recorded-model",
        prompt_hash="recorded-prompt",
        observations=[observation],
        output=proposal,
    )


def test_captured_project_proposal_reproduces_identity_undercoverage() -> None:
    case = _cases()["accepted_identity_incomplete_project"]

    proposal = _compile(
        source_id=str(case["source_id"]),
        text=str(case["source_text"]),
        proposal=dict(case["captured_proposal"]),
    )
    run = proposal.run
    entities = proposal.entities

    assert run.status == ExtractionRunStatus.SUCCEEDED
    assert len(entities) == 1
    assert "atlas billing migration" not in {
        entities[0].normalized_name,
        *(alias.casefold() for alias in entities[0].aliases),
    }


def test_captured_anaphoric_owner_proposal_fails_closed() -> None:
    case = _cases()["anaphoric_service_owner"]

    proposal = _compile(
        source_id=str(case["source_id"]),
        text=str(case["source_text"]),
        proposal=dict(case["captured_proposal"]),
    )
    run = proposal.run
    claims = proposal.claims

    assert run.status == ExtractionRunStatus.PARTIAL
    assert all(claim.claim_key.predicate_id != "owner" for claim in claims)
    assert any("relation semantics are not grounded" in error for error in run.errors)


def test_corrected_surfaces_and_proposals_satisfy_typed_ingestion_contracts() -> None:
    for case in _cases().values():
        proposal = _compile(
            source_id=str(case["source_id"]),
            text=str(case["corrected_source_text"]),
            proposal=dict(case["corrected_proposal"]),
        )
        run = proposal.run
        entities = proposal.entities
        claims = proposal.claims

        assert run.status == ExtractionRunStatus.SUCCEEDED
        assert entities
        assert claims
        assert all(claim.claim_key.predicate_id != "semantic_fact" for claim in claims)


def _proposal_map(
    payload: dict[str, Any],
    *,
    corrected: bool,
) -> dict[str, dict[str, object] | None]:
    proposals = {
        str(item["event_id"]): (
            _with_explicit_world_semantics(dict(item["structured_proposal"]))
            if corrected and item["structured_proposal"] is not None
            else item["structured_proposal"]
        )
        for item in payload["proposals"]
    }
    if corrected:
        proposals.update(
            {
                str(item["event_id"]): _with_explicit_world_semantics(
                    dict(item["structured_proposal"])
                )
                for item in payload["proposal_corrections"]
            }
        )
    return proposals


def _with_explicit_world_semantics(proposal: dict[str, object]) -> dict[str, object]:
    """Version captured corrected proposals without changing production legacy handling."""

    claims = proposal.get("claims")
    if not isinstance(claims, list):
        return proposal
    typed_claims: list[object] = []
    for claim in claims:
        if not isinstance(claim, dict):
            typed_claims.append(claim)
            continue
        typed_claims.append(
            {
                **claim,
                "semantic_context": {
                    "assertion_mode": "world_assertion",
                    "epistemic_status": "asserted",
                    "polarity": "positive",
                    "modality": "assertion",
                    "attribution_source_id": claim.get("source_id"),
                    "attribution_speaker_id": None,
                    "reported_source_id": None,
                    "belief_holder_entity_ref": None,
                },
            }
        )
    return {**proposal, "claims": typed_claims}


def _replay_long_horizon_prefixes(
    payload: dict[str, Any],
    *,
    proposals: dict[str, dict[str, object] | None],
    corrected_source_text: dict[str, str] | None = None,
) -> list[_ReplayDivergence]:
    scenarios = [LatentGraphScenario.model_validate(item) for item in payload["scenarios"]]
    assert sum(len(scenario.observations) for scenario in scenarios) == 130
    assert len(proposals) == 130

    divergences: list[_ReplayDivergence] = []
    for scenario in scenarios:
        memory_plane = MemoryPlaneService()
        provider = ProviderMemoryService(
            memory_plane=memory_plane,
            memory_evolution_extractor=_RecordedProposalExtractor(proposals),
        )
        context = IngestionContext()
        source_id_to_event_id: dict[str, str] = {}
        before_ids: set[str] = set()
        ordered = sorted(
            scenario.observations,
            key=lambda item: (item.timestamp, item.event_id),
        )
        if corrected_source_text:
            ordered = [
                observation.model_copy(
                    update={"text": corrected_source_text.get(observation.event_id, observation.text)}
                )
                for observation in ordered
            ]
        for index, observation in enumerate(ordered, start=1):
            ingestion = ingest_surface_observation(
                provider=provider,
                memory_plane=memory_plane,
                observation=observation,
                context=context,
                before_ids=before_ids,
            )
            source_id_to_event_id.update(ingestion.source_id_to_event_id)
            before_ids = {record.memory_id for record in memory_plane.list_records()}
            audit = audit_ingestion_prefix(
                scenario=scenario,
                observations=ordered[:index],
                snapshot=provider.memory_evolution_service.retrieve_graph_snapshot(),
                source_id_to_event_id=source_id_to_event_id,
            )
            if not audit.passed:
                divergences.append(
                    _ReplayDivergence(
                        scenario_id=scenario.scenario_id,
                        event_id=observation.event_id,
                        issues=tuple(f"{issue.code}[{issue.expected!r}->{issue.actual!r}]" for issue in audit.issues),
                    )
                )
                break

    return divergences


def test_raw_captured_long_horizon_proposals_reproduce_pre_contract_divergences() -> None:
    payload: dict[str, Any] = json.loads(_LONG_HORIZON_FIXTURE.read_text(encoding="utf-8"))

    divergences = _replay_long_horizon_prefixes(
        payload,
        proposals=_proposal_map(payload, corrected=False),
    )
    issue_codes = {issue.partition("[")[0] for divergence in divergences for issue in divergence.issues}

    assert len(divergences) == 10
    assert issue_codes >= {
        "ingestion_claim_predicate_mismatch",
        "ingestion_missing_expected_relation",
        "ingestion_unexpected_observed_claim",
        "ingestion_unexpected_observed_entity",
    }


def test_contract_corrected_long_horizon_proposals_match_every_ingestion_prefix() -> None:
    payload: dict[str, Any] = json.loads(_LONG_HORIZON_FIXTURE.read_text(encoding="utf-8"))
    correction_ids = [str(item["event_id"]) for item in payload["proposal_corrections"]]
    assert len(correction_ids) == 30
    assert len(set(correction_ids)) == len(correction_ids)

    divergences = _replay_long_horizon_prefixes(
        payload,
        proposals=_proposal_map(payload, corrected=True),
        corrected_source_text={
            str(item["event_id"]): str(item["corrected_source_text"])
            for item in payload["proposal_corrections"]
            if item.get("corrected_source_text")
        },
    )

    assert not divergences, "\n".join(divergence.describe() for divergence in divergences)

"""Run scenario fixtures through public ingress and emit stable semantic evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memorii.core.memory_evolution.extraction import EnglishRuleMemoryExtractor
from memorii.core.memory_evolution.extraction_contracts import MemoryExtractionProposal
from memorii.core.memory_evolution.models import SourceObservation
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService

from validate_scenario_first import compare_proposal, render, validate


ROOT = Path(__file__).parents[4]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tool_pins() -> dict[str, str]:
    paths = {
        "checker": Path(__file__).with_name("validate_scenario_first.py"),
        "extractor": ROOT
        / "memorii"
        / "memorii"
        / "core"
        / "memory_evolution"
        / "extraction.py",
        "ingress_runner": Path(__file__),
        "provider_composition": ROOT
        / "memorii"
        / "memorii"
        / "core"
        / "provider"
        / "service.py",
        "renderer": Path(__file__).with_name("validate_scenario_first.py"),
    }
    return {name: _sha(path.read_bytes()) for name, path in sorted(paths.items())}


def _stable_proposal_projection(proposal: MemoryExtractionProposal) -> dict[str, Any]:
    """Select semantic evidence rather than modifying a raw persisted dump."""
    return {
        "run": {
            "status": proposal.run.status.value,
            "provider_attempt_status": proposal.run.provider_attempt_status.value,
            "fallback_outcome": proposal.run.fallback_outcome.value,
            "final_output_source": proposal.run.final_output_source.value,
            "failure_code": proposal.run.failure_code.value
            if proposal.run.failure_code
            else None,
            "validation_summary": proposal.run.validation_summary,
        },
        "entities": [
            {
                "normalized_name": entity.normalized_name,
                "entity_type": entity.entity_type.value,
                "scope": entity.scope.model_dump(mode="json"),
                "evidence_spans": [
                    span.model_dump(mode="json") for span in entity.evidence_spans
                ],
                "confidence": entity.confidence,
            }
            for entity in proposal.entities
        ],
        "claims": [
            {
                "claim_key": claim.claim_key.model_dump(mode="json"),
                "object_value": claim.object_value,
                "object_entity_id": claim.object_entity_id,
                "qualifiers": claim.qualifiers,
                "semantic_context": claim.semantic_context.model_dump(mode="json"),
                "valid_from": claim.valid_from.isoformat().replace("+00:00", "Z")
                if claim.valid_from
                else None,
                "valid_to": claim.valid_to.isoformat().replace("+00:00", "Z")
                if claim.valid_to
                else None,
                "evidence_spans": [
                    span.model_dump(mode="json") for span in claim.evidence_spans
                ],
                "confidence": claim.confidence.model_dump(mode="json"),
            }
            for claim in proposal.claims
        ],
    }


class OracleLeakSpy:
    provider = "scenario_ingress_spy"
    model = None
    prompt_hash = None

    def __init__(self) -> None:
        self._delegate = EnglishRuleMemoryExtractor()
        self.observations: list[dict[str, Any]] = []
        self.proposals: list[MemoryExtractionProposal] = []

    def extract(
        self, observations: list[SourceObservation]
    ) -> MemoryExtractionProposal:
        for observation in observations:
            dumped = observation.model_dump(mode="json")
            if {
                "scenario",
                "expectation",
                "classification",
                "claims",
                "entities",
                "oracle",
            } & set(dumped):
                raise AssertionError("scenario truth leaked into SourceObservation")
            self.observations.append(dumped)
        proposal = self._delegate.extract(observations)
        self.proposals.append(proposal)
        return proposal


def run(
    world: Any, *, scenario_bytes: bytes, design_bytes: bytes, registry_bytes: bytes
) -> dict[str, Any]:
    scenarios = validate(world)
    spy = OracleLeakSpy()
    service = ProviderMemoryService(
        memory_plane=MemoryPlaneService(),
        memory_evolution_extractor=spy,
        now_provider=lambda: datetime(2026, 7, 30, tzinfo=UTC),
    )
    runs: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for scenario in scenarios:
        proposals: list[MemoryExtractionProposal] = []
        source_id_map: dict[str, str] = {}
        observations = render(scenario)
        by_id = {item.source_id: item for item in observations}
        for observation in observations:
            scope = "\0".join(
                value or ""
                for value in (
                    observation.user_id,
                    observation.session_id,
                    observation.task_id,
                )
            )
            event_id = (
                "sf-"
                + _sha(
                    (
                        scope + "\0" + observation.source_id + "\0" + observation.text
                    ).encode("utf-8")
                )[:24]
            )
            service.sync_event(
                operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
                content=observation.text,
                operation_id=event_id,
                session_id=observation.session_id,
                task_id=observation.task_id,
                user_id=observation.user_id,
                language=observation.language,
                speaker_id=observation.speaker_id,
                timestamp=observation.timestamp,
            )
            proposal = spy.proposals[-1]
            projection = _stable_proposal_projection(proposal)
            proposals.append(proposal)
            evidence.append(projection)
            source_id_map[f"tx:{event_id}"] = observation.source_id
            rendered = observation.text.encode("utf-8")
            runs.append(
                {
                    "rendered_source_id": observation.source_id,
                    "provider_event_id": event_id,
                    "rendered_bytes_base64": base64.b64encode(rendered).decode("ascii"),
                    "source_span_map": [
                        {
                            "source_id": observation.source_id,
                            "byte_start": 0,
                            "byte_end": len(rendered),
                        }
                    ],
                    "projection_digest": _sha(_canonical(projection)),
                    "comparator_result": "pending",
                }
            )
        combined = (
            EnglishRuleMemoryExtractor()
            .extract([])
            .model_copy(
                update={
                    "run": proposals[-1].run,
                    "entities": [
                        item for proposal in proposals for item in proposal.entities
                    ],
                    "claims": [
                        item for proposal in proposals for item in proposal.claims
                    ],
                    "actions": [
                        item for proposal in proposals for item in proposal.actions
                    ],
                }
            )
        )
        result = compare_proposal(
            scenario, combined, source_id_map=source_id_map, observations=by_id
        )
        for row in runs[-len(proposals) :]:
            row["comparator_result"] = result
    if any(
        row["comparator_result"] not in {"match", "ambiguous", "abstain"}
        for row in runs
    ):
        raise AssertionError("scenario did not preserve its declared semantic result")
    return {
        "format": "memorii-sia-scenario-ingress-run-v2",
        "projection_policy": "scenario_semantic_persisted_projection",
        "projection_version": 1,
        "extractor_identity": "memorii.core.memory_evolution.extraction.EnglishRuleMemoryExtractor",
        "composition_identity": "memorii.core.provider.service.ProviderMemoryService.sync_event",
        "tool_pins": _tool_pins(),
        "oracle_spy_observation_count": len(spy.observations),
        "runs": runs,
        "stable_evidence": evidence,
        "scenario_sha256": _sha(scenario_bytes),
        "design_sha256": _sha(design_bytes),
        "registry_sha256": _sha(registry_bytes),
        "ctv_authority_sha256": _sha(
            Path(__file__).with_name("ctv-binding-authority-v2.json").read_bytes()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_file", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    scenario = args.scenario_file.read_bytes()
    args.output.write_bytes(
        _canonical(
            run(
                json.loads(scenario),
                scenario_bytes=scenario,
                design_bytes=args.design.read_bytes(),
                registry_bytes=args.registry.read_bytes(),
            )
        )
        + b"\n"
    )


if __name__ == "__main__":
    main()

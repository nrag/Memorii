from __future__ import annotations

import copy
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VECTORS = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors"
sys.path.insert(0, str(VECTORS))

import run_scenario_ingress as runner
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.semantic_analysis.source_contracts import PreparedSource
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.semantic_ingestion import contracts
from memorii.core.semantic_ingestion.canonical_evidence_arena import (
    CanonicalEvidenceArena,
    current_canonical_evidence_arena,
)
from tests.fixtures.semantic_ingestion.scenario_fixture_authority import (
    build_scenario_test_provider_service,
)


class _AuthorizedPreparedSourceMapping(dict[str, object]):
    pass


@dataclass(frozen=True)
class _RegisteredMapping:
    mapping: _AuthorizedPreparedSourceMapping
    prepared: PreparedSource
    producer_proxy: object
    arena: CanonicalEvidenceArena
    nonce: str


class _ReferenceIssuer:
    def __init__(self) -> None:
        self._capability = object()
        self._proxies: dict[int, object] = {}
        self._mappings: dict[int, _RegisteredMapping] = {}
        self.shortcut_hits = 0
        self.fallbacks = 0
        self._closed = False

    def register_proxy(self, proxy: object) -> None:
        self._proxies[id(proxy)] = proxy

    def issue(self, proxy: object, prepared: PreparedSource) -> object:
        arena = current_canonical_evidence_arena()
        if (
            self._closed
            or self._proxies.get(id(proxy)) is not proxy
            or arena is None
            or not arena.snapshot().reservation_acquired
        ):
            self.fallbacks += 1
            return prepared
        mapping = _AuthorizedPreparedSourceMapping(prepared.model_dump(mode="python"))
        self._mappings[id(mapping)] = _RegisteredMapping(
            mapping=mapping,
            prepared=prepared,
            producer_proxy=proxy,
            arena=arena,
            nonce=arena.nonce,
        )
        return _ProducedPreparedSource(mapping)

    def consume(self, value: object) -> PreparedSource | None:
        if self._closed or not isinstance(value, _AuthorizedPreparedSourceMapping):
            return None
        registration = self._mappings.pop(id(value), None)
        arena = current_canonical_evidence_arena()
        if (
            registration is None
            or registration.mapping is not value
            or self._proxies.get(id(registration.producer_proxy)) is not registration.producer_proxy
            or arena is None
            or registration.arena is not arena
            or registration.nonce != arena.nonce
            or not arena.snapshot().reservation_acquired
        ):
            raise ValueError("prepared source validation capability is stale or substituted")
        self.shortcut_hits += 1
        return registration.prepared

    def close(self) -> None:
        self._mappings.clear()
        self._proxies.clear()
        self._closed = True


class _ProducedPreparedSource:
    def __init__(self, mapping: _AuthorizedPreparedSourceMapping) -> None:
        self._mapping = mapping

    def model_dump(self, *, mode: str) -> _AuthorizedPreparedSourceMapping:
        if mode != "python":
            raise ValueError("reference producer supports only the production Python dump")
        return self._mapping


class _TrustedProducerProxy:
    def __init__(
        self,
        producer: Callable[[object], PreparedSource],
        issuer: _ReferenceIssuer,
        captured_requests: list[object] | None = None,
    ) -> None:
        self._producer = producer
        self._issuer = issuer
        self._captured_requests = captured_requests
        issuer.register_proxy(self)

    def __call__(self, request: object) -> object:
        if self._captured_requests is not None:
            self._captured_requests.append(request)
        return self._issuer.issue(self, self._producer(request))


def _scenario_material() -> tuple[object, object, str]:
    world = json.loads((VECTORS / "scenario-first-v1.json").read_text(encoding="utf-8"))
    scenario = runner.validate(world)[0]
    observation = runner.render(scenario)[0]
    operation_id = runner._opaque_event_id(ordinal=0, source_bytes=observation.text.encode("utf-8"))
    return observation, runner._host_ingress(ordinal=0), operation_id


def _service() -> object:
    return build_scenario_test_provider_service(
        memory_plane=MemoryPlaneService(),
        now_provider=lambda: datetime(2026, 7, 30, tzinfo=UTC),
    )


def _preparation(service: object) -> object:
    return service._provider_ingestion._semantic_runtime.text_preparation_service


def _run(service: object, observation: object, ingress: object, operation_id: str) -> tuple[float, bytes, int]:
    content_calls = 0
    original_digest = contracts.contract_digest

    def counted(domain: bytes, value: object) -> str:
        nonlocal content_calls
        frame = sys._getframe(1)
        if frame.f_code.co_name == "validate_content_digest":
            content_calls += 1
        return original_digest(domain, value)

    contracts.contract_digest = counted
    started = time.perf_counter()
    try:
        result = service.sync_event(
            operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
            content=observation.text,
            operation_id=operation_id,
            session_id=runner._PUBLIC_SCOPE[1],
            task_id=runner._PUBLIC_SCOPE[2],
            user_id=runner._PUBLIC_SCOPE[0],
            language="en",
            speaker_id="scenario-speaker",
            timestamp=observation.timestamp,
            authenticated_host_ingress=ingress,
        )
    finally:
        contracts.contract_digest = original_digest
    records = sorted(service._memory_plane.list_records(), key=lambda record: record.memory_id)
    output = encode_typed_value(
        {
            "result": result.model_dump(mode="python"),
            "records": tuple(record.model_dump(mode="python") for record in records),
        }
    )
    return time.perf_counter() - started, output, content_calls


def _must_reject(name: str, action: Callable[[], object], rejected: list[str]) -> None:
    try:
        action()
    except (TypeError, ValueError):
        rejected.append(name)
        return
    raise RuntimeError(f"VBP-EXP-002 accepted attack: {name}")


def main() -> None:
    observation, ingress, operation_id = _scenario_material()
    original_validate = PreparedSource.model_validate
    issuer = _ReferenceIssuer()

    @classmethod
    def reference_validate(cls: type[PreparedSource], value: object, *args: object, **kwargs: object) -> PreparedSource:
        consumed = issuer.consume(value)
        if consumed is not None:
            return consumed
        issuer.fallbacks += 1
        return original_validate(value, *args, **kwargs)

    legacy_service = _service()
    legacy_elapsed, legacy_output, legacy_content_calls = _run(
        legacy_service, observation, ingress, operation_id
    )

    PreparedSource.model_validate = reference_validate
    try:
        reference_service = _service()
        preparation = _preparation(reference_service)
        captured: list[object] = []
        trusted_proxy = _TrustedProducerProxy(preparation._producer, issuer, captured)
        preparation._producer = trusted_proxy
        reference_elapsed, reference_output, reference_content_calls = _run(
            reference_service, observation, ingress, operation_id
        )
        if reference_output != legacy_output:
            raise RuntimeError("reference capability changed production-shaped output bytes")

        if not captured:
            raise RuntimeError("production request capture failed")
        production_request = captured[0]

        rejected: list[str] = []
        valid = trusted_proxy._producer(production_request)
        forged = valid.model_copy(update={"preparation_fingerprint": "f" * 64})
        constructed = PreparedSource.model_construct(**forged.model_dump(mode="python"))

        preparation._producer = lambda _: forged
        _must_reject("injected_forged_producer", lambda: preparation.prepare(production_request), rejected)
        preparation._producer = lambda _: constructed
        _must_reject("injected_constructed_producer", lambda: preparation.prepare(production_request), rejected)

        copied_proxy = copy.copy(trusted_proxy)
        preparation._producer = copied_proxy
        before_copy_fallback = issuer.fallbacks
        preparation.prepare(production_request)
        if issuer.fallbacks <= before_copy_fallback:
            raise RuntimeError("copied producer did not execute legacy fallback")

        preparation._producer = trusted_proxy
        before_context_fallback = issuer.fallbacks
        preparation.prepare(production_request)
        if issuer.fallbacks <= before_context_fallback:
            raise RuntimeError("missing operation context did not execute legacy fallback")

        reservations = [CanonicalEvidenceArena() for _ in range(64)]
        try:
            saturated_legacy_service = _service()
            (
                saturated_legacy_elapsed,
                saturated_legacy_output,
                saturated_legacy_content_calls,
            ) = _run(saturated_legacy_service, observation, ingress, operation_id)
            saturated_service = _service()
            saturated_preparation = _preparation(saturated_service)
            saturated_proxy = _TrustedProducerProxy(saturated_preparation._producer, issuer)
            saturated_preparation._producer = saturated_proxy
            saturated_elapsed, saturated_output, saturated_content_calls = _run(
                saturated_service, observation, ingress, operation_id
            )
        finally:
            for arena in reservations:
                arena.close()
        if (
            saturated_output != saturated_legacy_output
            or saturated_content_calls != saturated_legacy_content_calls
        ):
            raise RuntimeError(
                "saturation fallback changed output or validation accounting: "
                f"output_equal={saturated_output == saturated_legacy_output}, "
                f"legacy_content_calls={saturated_legacy_content_calls}, "
                f"saturated_content_calls={saturated_content_calls}, "
                f"legacy_sha256={sha256(saturated_legacy_output).hexdigest()}, "
                f"saturated_sha256={sha256(saturated_output).hexdigest()}"
            )
    finally:
        PreparedSource.model_validate = original_validate
        issuer.close()

    result = {
        "schema": "memorii.semantic-ingestion.validation-boundary.preparation-capability.v1",
        "experiment": "VBP-EXP-002",
        "evidence_stage": "reference_only_feasibility",
        "certifies_m3_1": False,
        "decision": "REFERENCE_EDGE_SECURITY_AND_EQUIVALENCE_PASS",
        "legacy_elapsed_seconds": legacy_elapsed,
        "reference_elapsed_seconds": reference_elapsed,
        "saturation_elapsed_seconds": saturated_elapsed,
        "legacy_content_validation_calls": legacy_content_calls,
        "reference_content_validation_calls": reference_content_calls,
        "saturation_content_validation_calls": saturated_content_calls,
        "removed_content_validation_calls": legacy_content_calls - reference_content_calls,
        "output_sha256": sha256(legacy_output).hexdigest(),
        "reference_output_identical": reference_output == legacy_output,
        "saturation_output_identical": saturated_output == legacy_output,
        "shortcut_hits": issuer.shortcut_hits,
        "fallbacks": issuer.fallbacks,
        "rejected_attacks": rejected,
        "production_implementation_changed": False,
    }
    output = Path(__file__).with_name("evidence") / "vbp-exp-002-preparation-capability-v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


def _service_with_preparation_proxy(service: object, proxy: object) -> object:
    # The helper returns the same production service; it exists only to make the
    # capture call explicit without constructing a fixture-owned service path.
    _preparation(service)._producer = proxy
    return service


if __name__ == "__main__":
    main()

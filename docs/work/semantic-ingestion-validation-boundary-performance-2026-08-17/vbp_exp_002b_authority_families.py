from __future__ import annotations

import asyncio
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from typing import Callable

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
WORK = ROOT / "docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17"
sys.path.insert(0, str(WORK))

import vbp_exp_002_preparation_capability as base
from memorii.core.memory_evolution.semantic_analysis.source_contracts import PreparedSource
from memorii.core.semantic_ingestion.canonical_evidence_arena import CanonicalEvidenceArena


class _DumpCarrier:
    def __init__(self, value: dict[str, object]) -> None:
        self._value = value

    def model_dump(self, *, mode: str) -> dict[str, object]:
        if mode != "python":
            raise ValueError("unexpected dump mode")
        return self._value


class _PreparedSourceSubclass(PreparedSource):
    pass


class _ObservedIssuer(base._ReferenceIssuer):
    def __init__(self) -> None:
        super().__init__()
        self.consume_sites: list[tuple[str, bool]] = []

    def consume(self, value: object) -> PreparedSource | None:
        registered = id(value) in self._mappings
        self.consume_sites.append((sys._getframe(2).f_code.co_name, registered))
        return super().consume(value)


def _reject(name: str, action: Callable[[], object], passed: list[str]) -> None:
    try:
        action()
    except (TypeError, ValueError):
        passed.append(name)
        return
    raise RuntimeError(f"attack did not reject: {name}")


def _issued_mapping(
    issuer: base._ReferenceIssuer,
    proxy: base._TrustedProducerProxy,
    prepared: PreparedSource,
    arena: CanonicalEvidenceArena,
) -> object:
    with arena:
        produced = issuer.issue(proxy, prepared)
        if not isinstance(produced, base._ProducedPreparedSource):
            raise RuntimeError("authority was unavailable in an active reserved arena")
        return produced.model_dump(mode="python")


def main() -> None:
    observation, ingress, operation_id = base._scenario_material()
    issuer = _ObservedIssuer()
    original_validate = PreparedSource.model_validate

    @classmethod
    def reference_validate(
        cls: type[PreparedSource], value: object, *args: object, **kwargs: object
    ) -> PreparedSource:
        consumed = issuer.consume(value)
        if consumed is not None:
            return consumed
        issuer.fallbacks += 1
        return original_validate(value, *args, **kwargs)

    captured: list[object] = []
    PreparedSource.model_validate = reference_validate
    try:
        service = base._service()
        preparation = base._preparation(service)
        proxy = base._TrustedProducerProxy(preparation._producer, issuer, captured)
        preparation._producer = proxy
        _, production_output, _ = base._run(service, observation, ingress, operation_id)
        if not captured:
            raise RuntimeError("production request was not captured")
        request = captured[0]
        prepared = proxy._producer(request)
        pristine = prepared.model_dump(mode="python")

        passed: list[str] = []

        nested = copy.deepcopy(pristine)
        nested_context = nested["semantic_context"]
        if not isinstance(nested_context, dict):
            raise RuntimeError("semantic context did not dump as a mapping")
        nested_context["source_id"] = "substituted-source"
        preparation._producer = lambda _: _DumpCarrier(nested)
        _reject("nested_mutation", lambda: preparation.prepare(request), passed)

        sibling = _DumpCarrier(copy.deepcopy(pristine))
        preparation._producer = lambda _: sibling
        before_sibling = issuer.fallbacks
        sibling_result = preparation.prepare(request)
        if sibling_result != prepared or issuer.fallbacks <= before_sibling:
            raise RuntimeError("sibling producer did not take complete validation fallback")
        passed.append("sibling_type_full_validation")

        subclass_value = _PreparedSourceSubclass(**copy.deepcopy(pristine))
        preparation._producer = lambda _: subclass_value
        before_subclass = issuer.fallbacks
        subclass_result = preparation.prepare(request)
        if subclass_result != prepared or issuer.fallbacks <= before_subclass:
            raise RuntimeError("PreparedSource subclass did not take complete validation fallback")
        passed.append("subclass_full_validation")

        copied_mapping = dict(pristine)
        before_serialized = issuer.fallbacks
        serialized_result = PreparedSource.model_validate(copied_mapping)
        if serialized_result != prepared or issuer.fallbacks <= before_serialized:
            raise RuntimeError("serialized mapping retained private authority")
        passed.append("serialization_loses_authority")

        same_arena = CanonicalEvidenceArena()
        with same_arena:
            produced = issuer.issue(proxy, prepared)
            mapping = produced.model_dump(mode="python")
            if issuer.consume(mapping) is not prepared:
                raise RuntimeError("same-operation authority was not consumable")
            _reject("one_use_replay_rejected", lambda: issuer.consume(mapping), passed)

        source_arena = CanonicalEvidenceArena()
        cross_operation_mapping = _issued_mapping(issuer, proxy, prepared, source_arena)
        target_arena = CanonicalEvidenceArena()
        with target_arena:
            _reject(
                "wrong_operation",
                lambda: issuer.consume(cross_operation_mapping),
                passed,
            )

        later_arena = CanonicalEvidenceArena()
        later_mapping = _issued_mapping(issuer, proxy, prepared, later_arena)
        _reject("later_invocation", lambda: issuer.consume(later_mapping), passed)

        failure_arena = CanonicalEvidenceArena()
        failure_mapping: object | None = None
        try:
            with failure_arena:
                produced = issuer.issue(proxy, prepared)
                failure_mapping = produced.model_dump(mode="python")
                raise RuntimeError("synthetic operation failure")
        except RuntimeError as error:
            if str(error) != "synthetic operation failure":
                raise
        if failure_mapping is None:
            raise RuntimeError("failure mapping was not issued")
        _reject("exception_teardown", lambda: issuer.consume(failure_mapping), passed)

        cancellation_arena = CanonicalEvidenceArena()
        cancellation_mapping: object | None = None
        try:
            with cancellation_arena:
                produced = issuer.issue(proxy, prepared)
                cancellation_mapping = produced.model_dump(mode="python")
                raise asyncio.CancelledError
        except asyncio.CancelledError:
            pass
        if cancellation_mapping is None:
            raise RuntimeError("cancellation mapping was not issued")
        _reject(
            "cancellation_teardown",
            lambda: issuer.consume(cancellation_mapping),
            passed,
        )

        copied_proxy = copy.copy(proxy)
        owner_arena = CanonicalEvidenceArena()
        with owner_arena:
            if issuer.issue(copied_proxy, prepared) is not prepared:
                raise RuntimeError("copied owner received authority")
        passed.append("wrong_owner_full_validation")

        other_issuer = _ObservedIssuer()
        purpose_arena = CanonicalEvidenceArena()
        purpose_mapping = _issued_mapping(issuer, proxy, prepared, purpose_arena)
        _reject(
            "wrong_purpose_no_authority",
            lambda: other_issuer.consume(purpose_mapping),
            passed,
        )
        other_issuer.close()
        _reject(
            "wrong_purpose_original_context_closed",
            lambda: issuer.consume(purpose_mapping),
            passed,
        )

        def isolated(_: int) -> bool:
            arena = CanonicalEvidenceArena()
            with arena:
                produced = issuer.issue(proxy, prepared)
                if not isinstance(produced, base._ProducedPreparedSource):
                    return False
                return issuer.consume(produced.model_dump(mode="python")) is prepared

        with ThreadPoolExecutor(max_workers=8) as pool:
            if not all(pool.map(isolated, range(16))):
                raise RuntimeError("concurrent operation authority was not isolated")
        passed.append("concurrent_operation_isolation")

        reservations = [CanonicalEvidenceArena() for _ in range(64)]
        try:
            if not all(arena.snapshot().reservation_acquired for arena in reservations):
                raise RuntimeError("exact process capacity was unavailable")
            first_above = CanonicalEvidenceArena()
            try:
                if first_above.snapshot().reservation_acquired:
                    raise RuntimeError("first-above process capacity acquired authority")
                with first_above:
                    if issuer.issue(proxy, prepared) is not prepared:
                        raise RuntimeError("capacity fallback issued private authority")
            finally:
                first_above.close()
        finally:
            for arena in reservations:
                arena.close()
        passed.extend(("exact_process_capacity", "first_above_capacity_fallback"))

        registered_sites = [site for site, registered in issuer.consume_sites if registered]
        if "prepare" not in registered_sites:
            raise RuntimeError("production preparation did not consume authority")
        if any(site in {"publish", "load"} for site in registered_sites):
            raise RuntimeError("persistence or reload consumed runtime authority")
        passed.append("persistence_reload_no_authority")

        if issuer._mappings:
            raise RuntimeError("authority registrations survived completed attacks")
    finally:
        PreparedSource.model_validate = original_validate
        issuer.close()

    result = {
        "schema": "memorii.semantic-ingestion.validation-boundary.authority-families.v1",
        "experiment": "VBP-EXP-002B",
        "decision": "FAMILY_ATTACKS_PASS",
        "evidence_stage": "reference_only_feasibility",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "production_output_sha256": sha256(production_output).hexdigest(),
        "passed_families": passed,
        "registered_consume_sites": registered_sites,
        "consume_sites": issuer.consume_sites,
    }
    evidence = WORK / "evidence/vbp-exp-002b-authority-families-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

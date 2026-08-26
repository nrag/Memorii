from __future__ import annotations

import argparse
import cProfile
import contextvars
import json
import os
import random
import statistics
import subprocess
import sys
import time
import weakref
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pydantic import BaseModel

ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
VBP_WORK = ROOT / "docs/work/semantic-ingestion-validation-boundary-performance-2026-08-17"
DEBUG_WORK = ROOT / "docs/work/semantic-ingestion-canonical-evidence-production-performance-2026-08-16"
sys.path.insert(0, str(VBP_WORK))

import vbp_exp_002_preparation_capability as base
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.semantic_analysis.source_contracts import PreparedSource
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion import contracts
from tests.unit.core.semantic_ingestion import test_semantic_provider_composition as fixture

MODES = ("safe_reference", "persisted_reload", "rollback")
SAMPLES = 3
SEED = 20260817
CHILD_TIMEOUT_SECONDS = 120
COUNTERFACTUAL_CHILD_TIMEOUT_SECONDS = 300
NORMALIZATION_RELOAD_BUNDLE_MAX_BYTES = 33_554_432
FAMILY_COMPLETE_PROOF_MAX_ENTRIES = 512
FAMILY_COMPLETE_PROOF_MAX_ROOT_BYTES = 2_097_152
FAMILY_COMPLETE_PROOF_MAX_CHARGED_BYTES = 33_554_432
_HIERARCHICAL_CLOSURE_PROOF_ACTIVE = contextvars.ContextVar(
    "pbd_exp_012_hierarchical_closure_proof_active", default=False
)
RECONSTRUCTION_TRACE_FAMILIES = frozenset(
    {
        "memorii.core.semantic_ingestion.contracts.SemanticProjectionTextArtifact",
        "memorii.core.semantic_ingestion.contracts.SegmentLocalTextArtifact",
        "memorii.core.semantic_ingestion.contracts.RetainedSourceTextArtifact",
        "memorii.core.semantic_ingestion.contracts.ProjectionTextSpan",
        "memorii.core.semantic_ingestion.contracts.SegmentLocalTextSpan",
        "memorii.core.semantic_ingestion.contracts.VerbatimTextArtifactMappingProof",
        "memorii.core.semantic_ingestion.contracts.RetainedSourceTextSpan",
    }
)


class _ReferenceDigestCounterfactual:
    """Bounded reuse for the exact immutable model reference validated once."""

    MAX_ENTRIES = 128
    MAX_CHARGED_BYTES = 1_048_576
    ENTRY_CHARGE = 512

    def __init__(self) -> None:
        self._entries: dict[
            tuple[int, type[BaseModel], bytes],
            tuple[BaseModel, str, object, int],
        ] = {}
        self.charged_bytes = 0
        self.hits = 0
        self.misses = 0
        self.admissions = 0
        self.capacity_fallbacks = 0
        self.coherence_rejections = 0

    def _shape(self, value: object) -> object:
        if isinstance(value, BaseModel):
            return (
                "model",
                id(value),
                type(value),
                tuple(
                    (name, self._shape(getattr(value, name)))
                    for name in type(value).model_fields
                ),
            )
        if isinstance(value, tuple):
            return ("tuple", id(value), tuple(self._shape(item) for item in value))
        if isinstance(value, frozenset):
            return (
                "frozenset",
                id(value),
                tuple(sorted((self._shape(item) for item in value), key=repr)),
            )
        if isinstance(value, (list, dict, set, bytearray)):
            raise TypeError("mutable value is not reference-cache eligible")
        try:
            hash(value)
        except TypeError as error:
            raise TypeError("unhashable value is not reference-cache eligible") from error
        return ("scalar", type(value), value)

    def lookup(self, owner: BaseModel, domain: bytes, declared: str) -> str | None:
        key = (id(owner), type(owner), domain)
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        admitted_owner, admitted_digest, admitted_shape, _charge = entry
        if admitted_owner is not owner or admitted_digest != declared:
            self.coherence_rejections += 1
            return None
        try:
            current_shape = self._shape(owner)
        except TypeError:
            self.coherence_rejections += 1
            return None
        if current_shape != admitted_shape:
            self.coherence_rejections += 1
            return None
        self.hits += 1
        return admitted_digest

    def admit(self, owner: BaseModel, domain: bytes, declared: str) -> None:
        key = (id(owner), type(owner), domain)
        if key in self._entries:
            return
        try:
            shape = self._shape(owner)
        except TypeError:
            self.coherence_rejections += 1
            return
        charge = self.ENTRY_CHARGE + len(domain) + len(declared)
        if (
            len(self._entries) >= self.MAX_ENTRIES
            or self.charged_bytes + charge > self.MAX_CHARGED_BYTES
        ):
            self.capacity_fallbacks += 1
            return
        self._entries[key] = (owner, declared, shape, charge)
        self.charged_bytes += charge
        self.admissions += 1

    def snapshot(self) -> dict[str, int]:
        return {
            "entries": len(self._entries),
            "charged_bytes": self.charged_bytes,
            "hits": self.hits,
            "misses": self.misses,
            "admissions": self.admissions,
            "capacity_fallbacks": self.capacity_fallbacks,
            "coherence_rejections": self.coherence_rejections,
        }


class _CountingProducer:
    def __init__(self, producer: object) -> None:
        self._producer = producer
        self.calls = 0

    def __call__(self, request: object) -> PreparedSource:
        self.calls += 1
        return self._producer(request)


def _accepted_proposal() -> contracts.ProviderSemanticProposal:
    text = "Atlas owner is Bob."
    return contracts.ProviderSemanticProposal(
        mentions=(
            contracts.ProviderMention(
                local_id="atlas", mention_quote="Atlas", mention_context_quote=text
            ),
            contracts.ProviderMention(
                local_id="bob", mention_quote="Bob", mention_context_quote=text
            ),
        ),
        facts=(
            contracts.ProviderFact(
                local_id="atlas-owner",
                predicate_id="owner_is",
                subject_entity_ref="atlas",
                object=contracts.ProviderEntityObject(entity_ref="bob"),
                assertion_quote=text,
                predicate_anchor_quote="owner",
                polarity="positive",
                commitment="asserted",
                temporal_qualifier_quotes=(),
            ),
        ),
        abstained=False,
    )


def _service() -> tuple[object, object, dict[str, int]]:
    builder, lane_calls = fixture._v3_normalization_host_builder(
        proposal=_accepted_proposal()
    )
    service = ProviderMemoryService(
        memory_plane=fixture.MemoryPlaneService(),
        now_provider=lambda: fixture.TEST_NOW,
        host_bootstrap_capability=fixture._built_in_local_capability(),
        host_bootstrap_material_verifier=(
            fixture.DeterministicTestHostBootstrapMaterialVerifier()
        ),
        source_normalization_host_bundle_builder=builder,
    )
    runtime = service._provider_ingestion._semantic_runtime
    if runtime is None:
        raise RuntimeError("current built-in V3 fixture did not install a semantic runtime")
    return service, runtime, lane_calls


def _execute(
    service: object,
    *,
    measure_evidence: bool = False,
    reference_counterfactual: bool = False,
    trace_reconstruction: bool = False,
    trace_validation_floor: bool = False,
) -> tuple[
    float,
    bytes,
    int,
    dict[str, str],
    dict[str, dict[str, float | int]],
    dict[str, object],
    dict[str, int],
    dict[str, object],
    dict[str, object],
]:
    content_calls = 0
    content_families: dict[str, dict[str, float | int]] = {}
    evidence_entries: dict[tuple[str, str], dict[str, int]] = {}
    original_digest = contracts.contract_digest
    digest_counterfactual = _ReferenceDigestCounterfactual()
    digest_computations = 0
    hierarchical_proof_covered_digest_validations = 0
    object_slots: dict[int, tuple[weakref.ReferenceType[BaseModel], int]] = {}
    next_object_token = 0
    reconstruction_rows: dict[str, dict[str, object]] = {}
    validation_floor_rows: dict[tuple[str, str], dict[str, object]] = {}

    def reconstruction_stack(caller: object) -> tuple[str, ...]:
        frames: list[str] = []
        frame = caller.f_back
        while frame is not None and len(frames) < 16:
            filename = frame.f_code.co_filename
            function = frame.f_code.co_name
            if filename == str(Path(__file__).resolve()):
                if function.startswith("observed_"):
                    frames.append(f"reference_harness:{function}")
            elif filename.startswith(str(ROOT)):
                relative = Path(filename).relative_to(ROOT)
                frames.append(f"{relative}:{function}")
            frame = frame.f_back
        return tuple(frames)

    def reconstruction_origin(stack: tuple[str, ...]) -> str:
        joined = "\n".join(stack)
        if "source_admission.py:build_verbatim_step_one_material" in joined:
            return "admission_explicit_construction"
        if "source_admission.py:build_step_one_material_from_governance" in joined:
            return "admission_explicit_construction"
        if "source_preparation.py:" in joined:
            return "step2_explicit_construction"
        if "linguistic_adapters.py:" in joined or "duckling_adapter.py:" in joined:
            return "linguistic_explicit_construction"
        if "contracts.py:decode_semantic_contract" in joined:
            return "semantic_envelope_decode"
        if "contracts.py:encode_semantic_contract" in joined:
            return "semantic_envelope_revalidation"
        if "reference_harness:observed_graph_execute" in joined:
            return "graph_execution_reconstruction"
        if "reference_harness:observed_normalize" in joined:
            return "normalization_reconstruction"
        if "reference_harness:observed_bootstrap_publish" in joined:
            return "bootstrap_publication_reconstruction"
        if "reference_harness:observed_semantic_publish" in joined:
            return "semantic_publication_reconstruction"
        if "reference_harness:observed_repository_load" in joined:
            return "repository_reload_reconstruction"
        return "other_production_reconstruction"

    def record_reconstruction(
        *, owner: BaseModel, family: str, declared: str, caller: object
    ) -> None:
        nonlocal next_object_token
        slot = object_slots.get(id(owner))
        if slot is None or slot[0]() is not owner:
            next_object_token += 1
            object_token = next_object_token
            object_slots[id(owner)] = (weakref.ref(owner), object_token)
        else:
            object_token = slot[1]
        row = reconstruction_rows.setdefault(
            family,
            {
                "validations": 0,
                "content_instances": {},
                "stack_sites": Counter(),
                "origins": Counter(),
                "first_events": [],
            },
        )
        row["validations"] = int(row["validations"]) + 1
        content_instances = row["content_instances"]
        assert isinstance(content_instances, dict)
        content_instances.setdefault(declared, set()).add(object_token)
        stack = reconstruction_stack(caller)
        origin = reconstruction_origin(stack)
        stack_sites = row["stack_sites"]
        origins = row["origins"]
        assert isinstance(stack_sites, Counter)
        assert isinstance(origins, Counter)
        stack_sites[stack] += 1
        origins[origin] += 1
        events = row["first_events"]
        assert isinstance(events, list)
        if len(events) < 24:
            events.append(
                {
                    "object_token": object_token,
                    "content_digest": declared,
                    "origin": origin,
                    "stack": stack,
                }
            )

    def record_validation_floor(
        *, owner: BaseModel, family: str, declared: str, caller: object
    ) -> None:
        stack = reconstruction_stack(caller)
        joined = "\n".join(stack)
        codec_kind = "none"
        root_family: str | None = None
        frame = caller.f_back
        while frame is not None:
            if frame.f_code.co_name == "encode_semantic_contract":
                codec_kind = "encode"
                root = frame.f_locals.get("value")
                if isinstance(root, BaseModel):
                    root_family = f"{type(root).__module__}.{type(root).__qualname__}"
                break
            if frame.f_code.co_name == "decode_semantic_contract":
                codec_kind = "decode"
                expected = frame.f_locals.get("expected_type")
                if isinstance(expected, type):
                    root_family = f"{expected.__module__}.{expected.__qualname__}"
                break
            frame = frame.f_back
        direct_root = root_family == family
        writer_boundary = "memory_evolution/writer_admission.py:" in joined
        persisted_boundary = codec_kind == "decode" and any(
            marker in joined
            for marker in (
                "memory_evolution/atomic_store.py:",
                "semantic_ingestion/source_normalization_repository.py:",
                "semantic_ingestion/bootstrap_graph_repository.py:",
                "semantic_ingestion/persistence.py:",
                "semantic_ingestion/transaction_group_plan_repository.py:",
            )
        )
        if writer_boundary and codec_kind == "decode":
            context = "writer_admission_decode"
        elif persisted_boundary:
            context = "persisted_decode"
        elif codec_kind == "encode" and any(
            marker in joined
            for marker in (
                "memory_evolution/atomic_store.py:",
                "semantic_ingestion/source_normalization_repository.py:",
                "semantic_ingestion/bootstrap_graph_repository.py:",
                "semantic_ingestion/persistence.py:",
            )
        ):
            context = "persistence_encode"
        elif codec_kind == "encode":
            context = "in_process_encode"
        elif any(item.endswith(":create") for item in stack):
            context = "explicit_construction"
        else:
            context = "in_process_rebuild"
        if "writer_admission.py:_is_bootstrap_graph_v3_group_commit_write" in joined:
            boundary_event = "writer_admission:graph_group_commit"
        elif "writer_admission.py:_is_bootstrap_graph_v3_authority_write" in joined:
            boundary_event = "writer_admission:graph_transaction_authority"
        elif "atomic_store.py:reload_bootstrap_recovery_replay_v3" in joined:
            boundary_event = "normalization_generation:recovery_replay"
        elif "atomic_store.py:reload_bootstrap_semantic_reduction_authority_v3" in joined:
            boundary_event = "normalization_generation:semantic_reduction_authority"
        elif "atomic_store.py:reload_bootstrap_graph_normalization_authority_v3" in joined:
            boundary_event = "normalization_generation:graph_normalization_authority"
        elif "source_normalization_repository.py:publish_and_reload" in joined:
            boundary_event = "normalization_generation:publication_reload"
        elif "atomic_store.py:_bootstrap_graph_v3_authority_from_record" in joined:
            boundary_event = "graph_authority_record:reload"
        elif "atomic_store.py:commit_or_reload_bootstrap_graph_group_v3" in joined:
            boundary_event = "graph_group_commit:atomic_reload"
        elif "bootstrap_graph_repository.py:commit_or_reload" in joined:
            boundary_event = "graph_group_commit:repository_reload"
        elif "atomic_store.py:persist_bootstrap_graph_terminal_v3" in joined:
            boundary_event = "graph_terminal:persistence_reload"
        elif "bootstrap_graph_repository.py:persist_and_reload" in joined:
            boundary_event = "graph_terminal:repository_reload"
        elif context in {"writer_admission_decode", "persisted_decode"}:
            boundary_event = "other_persisted_boundary"
        else:
            boundary_event = "none"
        identity_key = (family, declared)
        row = validation_floor_rows.get(identity_key)
        if row is None:
            row = {
                "validations": 0,
                "contexts": Counter(),
                "root_families": Counter(),
                "boundary_events": Counter(),
                "direct_boundary_root": False,
                "boundary_member": False,
                "canonical_bytes": len(
                    encode_typed_value(contracts.canonical_contract_value(owner))
                ),
                "first_stack": stack,
            }
            validation_floor_rows[identity_key] = row
        row["validations"] = int(row["validations"]) + 1
        contexts = row["contexts"]
        roots = row["root_families"]
        boundary_events = row["boundary_events"]
        assert isinstance(contexts, Counter)
        assert isinstance(roots, Counter)
        assert isinstance(boundary_events, Counter)
        contexts[context] += 1
        if direct_root and boundary_event != "none":
            boundary_events[boundary_event] += 1
        if root_family is not None:
            roots[root_family] += 1
        if direct_root and context in {"writer_admission_decode", "persisted_decode"}:
            row["direct_boundary_root"] = True
        if not direct_root and context in {"writer_admission_decode", "persisted_decode"}:
            row["boundary_member"] = True

    def counted(domain: bytes, value: object) -> str:
        nonlocal content_calls, digest_computations
        nonlocal hierarchical_proof_covered_digest_validations
        caller = sys._getframe(1)
        if caller.f_code.co_name == "validate_content_digest":
            content_calls += 1
            owner = caller.f_locals.get("self")
            family = (
                f"{type(owner).__module__}.{type(owner).__qualname__}"
                if owner is not None
                else caller.f_code.co_qualname
            )
            row = content_families.setdefault(family, {"calls": 0})
            row["calls"] = int(row["calls"]) + 1
            digest_field = getattr(type(owner), "_digest_field", None)
            declared = (
                getattr(owner, digest_field, None)
                if isinstance(digest_field, str)
                else None
            )
            if (
                reference_counterfactual
                and isinstance(owner, BaseModel)
                and isinstance(declared, str)
            ):
                cached = digest_counterfactual.lookup(owner, domain, declared)
                if cached is not None:
                    return cached
            if (
                _HIERARCHICAL_CLOSURE_PROOF_ACTIVE.get()
                and isinstance(owner, BaseModel)
                and isinstance(declared, str)
            ):
                hierarchical_proof_covered_digest_validations += 1
                return declared
            digest_computations += 1
            computed = original_digest(domain, value)
            if (
                trace_reconstruction
                and family in RECONSTRUCTION_TRACE_FAMILIES
                and isinstance(owner, BaseModel)
                and isinstance(declared, str)
                and computed == declared
            ):
                record_reconstruction(
                    owner=owner,
                    family=family,
                    declared=declared,
                    caller=caller,
                )
            if (
                trace_validation_floor
                and isinstance(owner, BaseModel)
                and isinstance(declared, str)
                and computed == declared
            ):
                record_validation_floor(
                    owner=owner,
                    family=family,
                    declared=declared,
                    caller=caller,
                )
            if (
                reference_counterfactual
                and isinstance(owner, BaseModel)
                and isinstance(declared, str)
                and computed == declared
            ):
                digest_counterfactual.admit(owner, domain, declared)
            if measure_evidence and computed == declared and isinstance(declared, str):
                key = (family, declared)
                entry = evidence_entries.get(key)
                if entry is None:
                    canonical_bytes = encode_typed_value(
                        contracts.canonical_contract_value(owner)
                    )
                    evidence_entries[key] = {
                        "validations": 1,
                        "canonical_bytes": len(canonical_bytes),
                    }
                else:
                    entry["validations"] += 1
            return computed
        return original_digest(domain, value)

    contracts.contract_digest = counted
    started = time.perf_counter()
    try:
        result = service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN,
            content="Atlas owner is Bob.",
            operation_id="semantic-ingestion-accepted",
            task_id="task:one",
            user_id="user:alice",
            authenticated_host_ingress=fixture._host_ingress(),
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
    evidence_families: dict[str, dict[str, int]] = {}
    for (family, _digest), entry in evidence_entries.items():
        family_row = evidence_families.setdefault(
            family,
            {
                "validations": 0,
                "unique_entries": 0,
                "repeat_validations": 0,
                "canonical_bytes": 0,
                "maximum_repetitions": 0,
            },
        )
        validations = entry["validations"]
        family_row["validations"] += validations
        family_row["unique_entries"] += 1
        family_row["repeat_validations"] += validations - 1
        family_row["canonical_bytes"] += entry["canonical_bytes"]
        family_row["maximum_repetitions"] = max(
            family_row["maximum_repetitions"], validations
        )
    repeated = sorted(
        (
            {
                "family": family,
                "content_digest": digest,
                **entry,
            }
            for (family, digest), entry in evidence_entries.items()
        ),
        key=lambda row: int(row["validations"]),
        reverse=True,
    )
    evidence_measurement = {
        "total_validations": sum(
            entry["validations"] for entry in evidence_entries.values()
        ),
        "unique_entries": len(evidence_entries),
        "repeat_validations": sum(
            entry["validations"] - 1 for entry in evidence_entries.values()
        ),
        "peak_entries_without_eviction": len(evidence_entries),
        "peak_canonical_bytes_without_eviction": sum(
            entry["canonical_bytes"] for entry in evidence_entries.values()
        ),
        "maximum_entry_bytes": max(
            (entry["canonical_bytes"] for entry in evidence_entries.values()),
            default=0,
        ),
        "families": dict(
            sorted(
                evidence_families.items(),
                key=lambda item: item[1]["repeat_validations"],
                reverse=True,
            )
        ),
        "most_repeated_entries": repeated[:50],
    }
    reconstruction_trace: dict[str, object] = {}
    for family, row in reconstruction_rows.items():
        content_instances = row["content_instances"]
        stack_sites = row["stack_sites"]
        origins = row["origins"]
        assert isinstance(content_instances, dict)
        assert isinstance(stack_sites, Counter)
        assert isinstance(origins, Counter)
        instance_counts = {
            digest: len(tokens) for digest, tokens in content_instances.items()
        }
        reconstruction_trace[family] = {
            "validations": row["validations"],
            "unique_content_identities": len(content_instances),
            "unique_object_instances": sum(instance_counts.values()),
            "equal_content_reconstructions": sum(
                max(0, count - 1) for count in instance_counts.values()
            ),
            "maximum_instances_per_content_identity": max(
                instance_counts.values(), default=0
            ),
            "origins": dict(origins.most_common()),
            "stack_sites": [
                {"validations": count, "stack": stack}
                for stack, count in stack_sites.most_common(30)
            ],
            "first_events": row["first_events"],
        }
    validation_floor_trace: dict[str, object] = {}
    floor_class_counts: Counter[str] = Counter()
    floor_class_validations: Counter[str] = Counter()
    boundary_root_families: Counter[str] = Counter()
    boundary_event_rows: dict[str, dict[str, object]] = {}
    in_process_role_counts: Counter[str] = Counter()
    in_process_role_validations: Counter[str] = Counter()
    for (family, digest), row in validation_floor_rows.items():
        if row["direct_boundary_root"]:
            classification = "mandatory_boundary_root"
        elif row["boundary_member"]:
            classification = "aggregate_coverable_candidate"
        else:
            classification = "in_process_only_candidate"
        floor_class_counts[classification] += 1
        floor_class_validations[classification] += int(row["validations"])
        roots = row["root_families"]
        contexts = row["contexts"]
        boundary_events = row["boundary_events"]
        assert isinstance(roots, Counter)
        assert isinstance(contexts, Counter)
        assert isinstance(boundary_events, Counter)
        if classification == "mandatory_boundary_root":
            boundary_root_families[family] += 1
            for event, count in boundary_events.items():
                event_row = boundary_event_rows.setdefault(
                    event, {"validations": 0, "identities": set()}
                )
                event_row["validations"] = int(event_row["validations"]) + count
                identities = event_row["identities"]
                assert isinstance(identities, set)
                identities.add((family, digest))
        if classification == "in_process_only_candidate":
            if contexts.get("explicit_construction", 0):
                in_process_role = "necessary_operation_derived_candidate"
            elif contexts.get("in_process_rebuild", 0):
                in_process_role = "reconstruction_only_candidate"
            else:
                in_process_role = "preexisting_static_reusable_candidate"
            in_process_role_counts[in_process_role] += 1
            in_process_role_validations[in_process_role] += int(row["validations"])
        else:
            in_process_role = None
        validation_floor_trace[f"{family}:{digest}"] = {
            "family": family,
            "content_digest": digest,
            "classification": classification,
            "validations": row["validations"],
            "canonical_bytes": row["canonical_bytes"],
            "contexts": dict(contexts.most_common()),
            "root_families": dict(roots.most_common()),
            "boundary_events": dict(boundary_events.most_common()),
            "in_process_role": in_process_role,
            "first_stack": row["first_stack"],
        }
    boundary_event_summary = {
        event: {
            "validations": row["validations"],
            "unique_identities": len(row["identities"]),
            "repeat_same_identity_validations": int(row["validations"])
            - len(row["identities"]),
        }
        for event, row in sorted(boundary_event_rows.items())
    }
    writer_required_occurrences = sum(
        int(row["validations"])
        for event, row in boundary_event_rows.items()
        if event.startswith("writer_admission:")
    )
    nonwriter_event_identity_floor = sum(
        len(row["identities"])
        for event, row in boundary_event_rows.items()
        if not event.startswith("writer_admission:")
    )
    validation_floor_census = {
        "unique_content_identities": len(validation_floor_rows),
        "total_validations": sum(
            int(row["validations"]) for row in validation_floor_rows.values()
        ),
        "repeat_validations": sum(
            int(row["validations"]) - 1 for row in validation_floor_rows.values()
        ),
        "classification_identity_counts": dict(floor_class_counts),
        "classification_validation_counts": dict(floor_class_validations),
        "mandatory_boundary_root_families": dict(
            boundary_root_families.most_common()
        ),
        "boundary_events": boundary_event_summary,
        "writer_required_occurrences": writer_required_occurrences,
        "nonwriter_event_identity_floor": nonwriter_event_identity_floor,
        "in_process_role_identity_counts": dict(in_process_role_counts),
        "in_process_role_validation_counts": dict(in_process_role_validations),
        "conservative_security_adjusted_floor": (
            writer_required_occurrences
            + nonwriter_event_identity_floor
            + sum(in_process_role_counts.values())
        ),
        "identities": validation_floor_trace,
    }
    return (
        time.perf_counter() - started,
        output,
        content_calls,
        dict(result.blocked_reasons),
        content_families,
        evidence_measurement,
        {
            **digest_counterfactual.snapshot(),
            "digest_computations": digest_computations,
            "hierarchical_proof_covered_digest_validations": (
                hierarchical_proof_covered_digest_validations
            ),
        },
        reconstruction_trace,
        validation_floor_census,
    )


def _child(
    mode: str,
    *,
    trace_only: bool = False,
    profile_enabled: bool = False,
    measure_evidence: bool = False,
    reference_counterfactual: bool = False,
    trace_reconstruction: bool = False,
    normalization_reload_counterfactual: bool = False,
    trace_validation_floor: bool = False,
    hierarchical_closure_counterfactual: bool = False,
    family_complete_closure_counterfactual: bool = False,
) -> None:
    service, runtime, lane_calls = _service()
    ingestion = service._provider_ingestion
    preparation = runtime.text_preparation_service
    repository = runtime.prepared_source_repository
    atomic_store = runtime.atomic_store
    pipeline = runtime.pipeline
    graph_bundle = runtime.bootstrap_graph_host_bundle
    if graph_bundle is None:
        raise RuntimeError("current built-in V3 fixture did not install a graph host bundle")
    normalization_bundle = runtime.source_normalization_host_bundle
    if normalization_bundle is None:
        raise RuntimeError("current built-in V3 fixture did not install a normalization host bundle")
    normalization_owner = normalization_bundle.execution_owner
    normalization_stage = normalization_owner._bootstrap_v3_stage
    normalization_interpreter = normalization_owner._bootstrap_v3_interpreter
    if normalization_interpreter is None:
        raise RuntimeError("current built-in V3 fixture did not install a V3 interpreter")

    issuer = base._ReferenceIssuer()
    original_validate = PreparedSource.model_validate
    validation_sites: list[tuple[str, bool]] = []

    @classmethod
    def reference_validate(
        cls: type[PreparedSource], value: object, *args: object, **kwargs: object
    ) -> PreparedSource:
        registered = id(value) in issuer._mappings
        validation_sites.append((sys._getframe(1).f_code.co_name, registered))
        consumed = issuer.consume(value)
        return consumed if consumed is not None else original_validate(value, *args, **kwargs)

    PreparedSource.model_validate = reference_validate
    counting = _CountingProducer(preparation._producer)
    preparation._producer = base._TrustedProducerProxy(counting, issuer)

    semantic_context = contextvars.ContextVar("pbd_exp_005_semantic_context", default=False)
    original_run_semantic = type(ingestion)._run_semantic_ingestion
    original_prepare_publish = type(preparation).prepare_and_publish
    original_repository_load = type(repository).load
    original_bootstrap_publish = type(atomic_store).publish_bootstrap_prepared_source_if_absent
    original_semantic_publish = type(atomic_store).publish_prepared_source
    original_recover_normalization = type(
        atomic_store
    ).recover_bootstrap_v3_source_normalization
    original_pipeline_run = type(pipeline).run
    original_graph_execute = type(graph_bundle).execute
    original_normalize = type(normalization_owner).normalize_after_recovery_claim
    original_stage_normalize = type(normalization_stage).normalize
    original_interpret = type(normalization_interpreter).interpret
    reduction_authority_type = contracts.BootstrapSemanticReductionAuthorityMemberV3
    original_reduction_authority_create = reduction_authority_type.create
    repository_load_calls = 0
    bootstrap_publish_calls = 0
    semantic_publish_calls = 0
    persisted_reload_hits = 0
    pipeline_run_calls = 0
    graph_execute_calls = 0
    graph_outcomes: list[dict[str, object]] = []
    normalization_outcomes: list[dict[str, object]] = []
    normalization_boundary_events: list[dict[str, object]] = []
    reduction_authority_clause_diagnostics: list[dict[str, object]] = []
    pipeline_run_identities: list[dict[str, object]] = []
    installed_identities: dict[str, object] = {}
    normalization_reload_bundle: dict[str, object] | None = None
    hierarchical_closure_proof: dict[str, object] | None = None
    normalization_reload_metrics = {
        "calls": 0,
        "full_validations": 0,
        "admissions": 0,
        "hits": 0,
        "coherence_checks": 0,
        "coherence_rejections": 0,
        "capacity_fallbacks": 0,
        "retained_members": 0,
        "retained_payload_bytes": 0,
    }
    hierarchical_closure_metrics = {
        "calls": 0,
        "full_admission_validations": 0,
        "admissions": 0,
        "proof_covered_revalidations": 0,
        "coherence_checks": 0,
        "coherence_rejections": 0,
        "capacity_fallbacks": 0,
        "retained_members": 0,
        "retained_payload_bytes": 0,
    }
    original_encode_contract = contracts.encode_semantic_contract
    original_decode_contract = contracts.decode_semantic_contract
    family_complete_entries: dict[tuple[str, type[BaseModel], bytes], None] = {}
    family_complete_metrics = {
        "entries": 0,
        "charged_bytes": 0,
        "encode_hits": 0,
        "encode_misses": 0,
        "decode_hits": 0,
        "decode_misses": 0,
        "admissions": 0,
        "capacity_fallbacks": 0,
        "writer_scoped_hits": 0,
    }

    def codec_proof_scope() -> str:
        frame = sys._getframe(1)
        while frame is not None:
            filename = frame.f_code.co_filename
            function = frame.f_code.co_name
            if filename.endswith("memory_evolution/writer_admission.py"):
                return f"writer:{function}:{id(frame)}"
            if filename.endswith("source_normalization_stage.py"):
                return "normalization:construction"
            if filename.endswith("source_normalization_repository.py"):
                return f"normalization:repository:{function}"
            if filename.endswith("bootstrap_graph_repository.py"):
                return f"graph:repository:{function}"
            if filename.endswith("memory_evolution/atomic_store.py"):
                return f"atomic_store:{function}"
            if filename.endswith("semantic_ingestion/persistence.py"):
                return f"semantic_persistence:{function}"
            frame = frame.f_back
        return "operation:in_process"

    def proof_lookup(
        *, scope: str, concrete_type: type[BaseModel], canonical_bytes: bytes
    ) -> bool:
        return (scope, concrete_type, canonical_bytes) in family_complete_entries

    def proof_admit(
        *, scope: str, concrete_type: type[BaseModel], canonical_bytes: bytes
    ) -> None:
        immutable_bytes = bytes(canonical_bytes)
        key = (scope, concrete_type, immutable_bytes)
        if key in family_complete_entries:
            return
        charge = len(immutable_bytes) + len(scope) + 512
        if (
            len(immutable_bytes) > FAMILY_COMPLETE_PROOF_MAX_ROOT_BYTES
            or len(family_complete_entries) >= FAMILY_COMPLETE_PROOF_MAX_ENTRIES
            or family_complete_metrics["charged_bytes"] + charge
            > FAMILY_COMPLETE_PROOF_MAX_CHARGED_BYTES
        ):
            family_complete_metrics["capacity_fallbacks"] += 1
            return
        family_complete_entries[key] = None
        family_complete_metrics["entries"] = len(family_complete_entries)
        family_complete_metrics["charged_bytes"] += charge
        family_complete_metrics["admissions"] += 1

    def proof_encode(value: BaseModel) -> bytes:
        scope = codec_proof_scope()
        kind = contracts._CONTRACT_KINDS.get(type(value))
        if kind is None:
            return original_encode_contract(value)
        candidate = encode_typed_value(
            {
                "schema": "memorii.semantic-ingestion.contract-envelope.v1",
                "kind": kind,
                "payload": contracts.canonical_contract_value(value),
            }
        )
        hit = proof_lookup(
            scope=scope,
            concrete_type=type(value),
            canonical_bytes=candidate,
        )
        family_complete_metrics["encode_hits" if hit else "encode_misses"] += 1
        token = None
        if hit:
            token = _HIERARCHICAL_CLOSURE_PROOF_ACTIVE.set(True)
            if scope.startswith("writer:"):
                family_complete_metrics["writer_scoped_hits"] += 1
        try:
            encoded = original_encode_contract(value)
        finally:
            if token is not None:
                _HIERARCHICAL_CLOSURE_PROOF_ACTIVE.reset(token)
        proof_admit(
            scope=scope,
            concrete_type=type(value),
            canonical_bytes=encoded,
        )
        return encoded

    def proof_decode(
        raw: bytes,
        expected_type: type[BaseModel],
        *,
        max_nodes: int | None = None,
        max_depth: int | None = None,
    ) -> BaseModel:
        scope = codec_proof_scope()
        immutable_raw = bytes(raw)
        hit = proof_lookup(
            scope=scope,
            concrete_type=expected_type,
            canonical_bytes=immutable_raw,
        )
        family_complete_metrics["decode_hits" if hit else "decode_misses"] += 1
        token = None
        if hit:
            token = _HIERARCHICAL_CLOSURE_PROOF_ACTIVE.set(True)
            if scope.startswith("writer:"):
                family_complete_metrics["writer_scoped_hits"] += 1
        try:
            decoded = original_decode_contract(
                immutable_raw,
                expected_type,
                max_nodes=max_nodes,
                max_depth=max_depth,
            )
        finally:
            if token is not None:
                _HIERARCHICAL_CLOSURE_PROOF_ACTIVE.reset(token)
        proof_admit(
            scope=scope,
            concrete_type=expected_type,
            canonical_bytes=immutable_raw,
        )
        return decoded

    patched_codec_bindings: list[tuple[object, str, object]] = []
    if family_complete_closure_counterfactual:
        for module in tuple(sys.modules.values()):
            if module is None or not getattr(module, "__name__", "").startswith("memorii"):
                continue
            if getattr(module, "encode_semantic_contract", None) is original_encode_contract:
                patched_codec_bindings.append(
                    (module, "encode_semantic_contract", original_encode_contract)
                )
                setattr(module, "encode_semantic_contract", proof_encode)
            if getattr(module, "decode_semantic_contract", None) is original_decode_contract:
                patched_codec_bindings.append(
                    (module, "decode_semantic_contract", original_decode_contract)
                )
                setattr(module, "decode_semantic_contract", proof_decode)

    def member_identity(members: tuple[object, ...]) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                member.member_id,
                member.kind,
                member.payload_digest,
                sha256(member.canonical_payload).hexdigest(),
                len(member.canonical_payload),
            )
            for member in members
        )

    def observed_recover_normalization(
        self: object, *, recovery_key_digest: str
    ) -> object:
        nonlocal normalization_reload_bundle, hierarchical_closure_proof
        if self is not atomic_store:
            return original_recover_normalization(
                self, recovery_key_digest=recovery_key_digest
            )
        normalization_reload_metrics["calls"] += 1
        hierarchical_closure_metrics["calls"] += 1
        proof = hierarchical_closure_proof
        if hierarchical_closure_counterfactual and proof is not None:
            hierarchical_closure_metrics["coherence_checks"] += 1
            try:
                record = self._memory_plane.get_record(
                    "semantic_ingestion:bootstrap-v3-recovery:" + recovery_key_digest
                )
                content = record.content
                namespace = str(content["namespace_id"])
                generation = int(content["publication_artifact_generation"])
                control = self._control_by_operation_fence_id(namespace)
                current_members = self._read_generation_members(control, generation)
                coherent = (
                    record.source_kind
                    == "semantic_ingestion_bootstrap_v3_recovery_index"
                    and content["schema_version"] == 3
                    and content["state"] == "found"
                    and content["kind"] == "found"
                    and content["recovery_key_digest"] == recovery_key_digest
                    and recovery_key_digest == proof["recovery_key_digest"]
                    and namespace == proof["namespace_id"]
                    and generation == proof["generation"]
                    and str(content["atomic_request_digest"])
                    == proof["atomic_request_digest"]
                    and str(content["result_digest"]) == proof["result_digest"]
                    and member_identity(current_members) == proof["member_identity"]
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                coherent = False
            if coherent:
                token = _HIERARCHICAL_CLOSURE_PROOF_ACTIVE.set(True)
                try:
                    result = original_recover_normalization(
                        self, recovery_key_digest=recovery_key_digest
                    )
                finally:
                    _HIERARCHICAL_CLOSURE_PROOF_ACTIVE.reset(token)
                if result is not None:
                    hierarchical_closure_metrics[
                        "proof_covered_revalidations"
                    ] += 1
                    return result
            hierarchical_closure_metrics["coherence_rejections"] += 1
        bundle = normalization_reload_bundle
        if normalization_reload_counterfactual and bundle is not None:
            normalization_reload_metrics["coherence_checks"] += 1
            try:
                record = self._memory_plane.get_record(
                    "semantic_ingestion:bootstrap-v3-recovery:" + recovery_key_digest
                )
                content = record.content
                namespace = str(content["namespace_id"])
                generation = int(content["publication_artifact_generation"])
                control = self._control_by_operation_fence_id(namespace)
                current_members = self._read_generation_members(control, generation)
                current_identity = member_identity(current_members)
                coherent = (
                    record.source_kind
                    == "semantic_ingestion_bootstrap_v3_recovery_index"
                    and content["schema_version"] == 3
                    and content["state"] == "found"
                    and content["kind"] == "found"
                    and content["recovery_key_digest"] == recovery_key_digest
                    and recovery_key_digest == bundle["recovery_key_digest"]
                    and namespace == bundle["namespace_id"]
                    and generation == bundle["generation"]
                    and str(content["atomic_request_digest"])
                    == bundle["atomic_request_digest"]
                    and str(content["result_digest"]) == bundle["result_digest"]
                    and current_identity == bundle["member_identity"]
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                coherent = False
            if coherent:
                normalization_reload_metrics["hits"] += 1
                return bundle["result"]
            normalization_reload_metrics["coherence_rejections"] += 1
        normalization_reload_metrics["full_validations"] += 1
        result = original_recover_normalization(
            self, recovery_key_digest=recovery_key_digest
        )
        if hierarchical_closure_counterfactual and hierarchical_closure_proof is None:
            hierarchical_closure_metrics["full_admission_validations"] += 1
        if (
            normalization_reload_counterfactual
            and normalization_reload_bundle is None
            and result is not None
        ):
            generation, atomic_request_digest, result_digest, members = result
            retained_payload_bytes = sum(
                len(member.canonical_payload) for member in members
            )
            if retained_payload_bytes <= NORMALIZATION_RELOAD_BUNDLE_MAX_BYTES:
                record = self._memory_plane.get_record(
                    "semantic_ingestion:bootstrap-v3-recovery:" + recovery_key_digest
                )
                normalization_reload_bundle = {
                    "recovery_key_digest": recovery_key_digest,
                    "namespace_id": str(record.content["namespace_id"]),
                    "generation": generation,
                    "atomic_request_digest": atomic_request_digest,
                    "result_digest": result_digest,
                    "member_identity": member_identity(members),
                    "result": result,
                }
                normalization_reload_metrics["admissions"] += 1
                normalization_reload_metrics["retained_members"] = len(members)
                normalization_reload_metrics["retained_payload_bytes"] = (
                    retained_payload_bytes
                )
            else:
                normalization_reload_metrics["capacity_fallbacks"] += 1
        if (
            hierarchical_closure_counterfactual
            and hierarchical_closure_proof is None
            and result is not None
        ):
            generation, atomic_request_digest, result_digest, members = result
            retained_payload_bytes = sum(
                len(member.canonical_payload) for member in members
            )
            if retained_payload_bytes <= NORMALIZATION_RELOAD_BUNDLE_MAX_BYTES:
                record = self._memory_plane.get_record(
                    "semantic_ingestion:bootstrap-v3-recovery:" + recovery_key_digest
                )
                hierarchical_closure_proof = {
                    "recovery_key_digest": recovery_key_digest,
                    "namespace_id": str(record.content["namespace_id"]),
                    "generation": generation,
                    "atomic_request_digest": atomic_request_digest,
                    "result_digest": result_digest,
                    "member_identity": member_identity(members),
                }
                hierarchical_closure_metrics["admissions"] += 1
                hierarchical_closure_metrics["retained_members"] = len(members)
                hierarchical_closure_metrics["retained_payload_bytes"] = (
                    retained_payload_bytes
                )
            else:
                hierarchical_closure_metrics["capacity_fallbacks"] += 1
        return result

    def observed_run_semantic(self: object, *args: object, **kwargs: object) -> object:
        installed_runtime = self._semantic_runtime
        installed_pipeline = self._semantic_pipeline
        installed_identities.update(
            {
                "runtime_exact": installed_runtime is runtime,
                "pipeline_exact": installed_pipeline is pipeline,
                "preparation_service_exact": (
                    installed_runtime.text_preparation_service is preparation
                ),
                "repository_exact": (
                    installed_runtime.prepared_source_repository is repository
                ),
                "atomic_store_exact": installed_runtime.atomic_store is atomic_store,
                "selected_runtime_id": id(runtime),
                "installed_runtime_id": id(installed_runtime),
                "selected_pipeline_id": id(pipeline),
                "installed_pipeline_id": id(installed_pipeline),
            }
        )
        token = semantic_context.set(self is ingestion)
        try:
            return original_run_semantic(self, *args, **kwargs)
        finally:
            semantic_context.reset(token)

    def observed_prepare_publish(self: object, request: object) -> PreparedSource:
        nonlocal persisted_reload_hits
        if self is preparation and mode == "persisted_reload" and semantic_context.get():
            loaded = repository.load(
                source_id=request.observation.source_id,
                source_digest=request.observation.source_digest,
            )
            if loaded is not None:
                persisted_reload_hits += 1
                verifier = type(preparation)(producer=lambda _: loaded, repository=repository)
                return verifier.prepare(request)
        return original_prepare_publish(self, request)

    def observed_repository_load(self: object, *args: object, **kwargs: object) -> object:
        nonlocal repository_load_calls
        if self is repository:
            repository_load_calls += 1
        return original_repository_load(self, *args, **kwargs)

    def observed_bootstrap_publish(self: object, *args: object, **kwargs: object) -> object:
        nonlocal bootstrap_publish_calls
        if self is atomic_store:
            bootstrap_publish_calls += 1
        return original_bootstrap_publish(self, *args, **kwargs)

    def observed_semantic_publish(self: object, *args: object, **kwargs: object) -> object:
        nonlocal semantic_publish_calls
        if self is atomic_store:
            semantic_publish_calls += 1
        return original_semantic_publish(self, *args, **kwargs)

    def observed_pipeline_run(self: object, *args: object, **kwargs: object) -> object:
        nonlocal pipeline_run_calls
        pipeline_run_calls += 1
        pipeline_run_identities.append(
            {
                "exact_selected_pipeline": self is pipeline,
                "pipeline_id": id(self),
                "pipeline_type": f"{type(self).__module__}.{type(self).__qualname__}",
            }
        )
        return original_pipeline_run(self, *args, **kwargs)

    def observed_graph_execute(self: object, *args: object, **kwargs: object) -> object:
        nonlocal graph_execute_calls
        if self is graph_bundle:
            graph_execute_calls += 1
        started = time.perf_counter()
        result = original_graph_execute(self, *args, **kwargs)
        if self is graph_bundle:
            graph_outcomes.append(
                {
                    "type": f"{type(result).__module__}.{type(result).__qualname__}",
                    "kind": getattr(result, "kind", None),
                    "reason": getattr(result, "reason", None),
                    "elapsed_seconds": time.perf_counter() - started,
                }
            )
        return result

    def observed_normalize(self: object, *args: object, **kwargs: object) -> object:
        started = time.perf_counter()
        result = original_normalize(self, *args, **kwargs)
        if self is normalization_owner:
            normalization_outcomes.append(
                {
                    "type": f"{type(result).__module__}.{type(result).__qualname__}",
                    "phase": getattr(result, "phase", None),
                    "reason": getattr(result, "reason", None),
                    "elapsed_seconds": time.perf_counter() - started,
                }
            )
        return result

    def observed_interpret(self: object, *args: object, **kwargs: object) -> object:
        started = time.perf_counter()
        try:
            result = original_interpret(self, *args, **kwargs)
        except Exception as error:
            if self is normalization_interpreter:
                normalization_boundary_events.append(
                    {"boundary": "interpreter", "exception": repr(error)}
                )
            raise
        if self is normalization_interpreter:
            normalization_boundary_events.append(
                {"boundary": "interpreter", "result_type": type(result).__qualname__}
            )
            normalization_boundary_events[-1]["elapsed_seconds"] = (
                time.perf_counter() - started
            )
        return result

    def observed_stage_normalize(self: object, *args: object, **kwargs: object) -> object:
        started = time.perf_counter()
        try:
            result = original_stage_normalize(self, *args, **kwargs)
        except Exception as error:
            if self is normalization_stage:
                normalization_boundary_events.append(
                    {"boundary": "publication_stage", "exception": repr(error)}
                )
            raise
        if self is normalization_stage:
            normalization_boundary_events.append(
                {"boundary": "publication_stage", "result_type": type(result).__qualname__}
            )
            normalization_boundary_events[-1]["elapsed_seconds"] = (
                time.perf_counter() - started
            )
        return result

    def observed_reduction_authority_create(**values: object) -> object:
        core = values["normalization_request_core"]
        operation_inputs = values["operation_inputs"]
        execution_policy = values["execution_policy"]
        capability_registry = values["capability_registry"]
        assert isinstance(operation_inputs, tuple)
        pairs = tuple(
            (item.dependency_group.group_id, item.operation_id)
            for item in operation_inputs
        )
        operation_ids = tuple(item.operation_id for item in operation_inputs)
        expected_operation_ids = {
            operation_id
            for group in core.source_alignment.source_dependency_groups
            if group.status == "complete"
            for operation_id in group.operation_ids
        }
        computed_core_bytes = encode_typed_value(contracts.canonical_contract_value(core))
        computed_policy_bytes = encode_typed_value(
            contracts.canonical_contract_value(execution_policy)
        )
        computed_registry_bytes = encode_typed_value(
            contracts.canonical_contract_value(capability_registry)
        )
        diagnostic: dict[str, object] = {
            "nonempty_operation_inputs": bool(operation_inputs),
            "pairs_sorted": pairs == tuple(sorted(pairs)),
            "operation_ids_sorted_unique": operation_ids
            == tuple(sorted(set(operation_ids))),
            "operation_id_closure_exact": set(operation_ids) == expected_operation_ids,
            "core_bytes_equal": values["normalization_request_core_canonical_bytes"]
            == computed_core_bytes,
            "policy_bytes_equal": values["execution_policy_canonical_bytes"]
            == computed_policy_bytes,
            "registry_bytes_equal": values["capability_registry_canonical_bytes"]
            == computed_registry_bytes,
            "operation_pairs": pairs,
            "expected_operation_ids": tuple(sorted(expected_operation_ids)),
            "core_bytes_sha256": sha256(computed_core_bytes).hexdigest(),
            "policy_bytes_sha256": sha256(computed_policy_bytes).hexdigest(),
            "registry_bytes_sha256": sha256(computed_registry_bytes).hexdigest(),
        }
        reduction_authority_clause_diagnostics.append(diagnostic)
        try:
            return original_reduction_authority_create(**values)
        except ValueError as error:
            diagnostic["exception"] = str(error)
            raise

    type(ingestion)._run_semantic_ingestion = observed_run_semantic
    type(preparation).prepare_and_publish = observed_prepare_publish
    type(repository).load = observed_repository_load
    type(atomic_store).publish_bootstrap_prepared_source_if_absent = observed_bootstrap_publish
    type(atomic_store).publish_prepared_source = observed_semantic_publish
    type(
        atomic_store
    ).recover_bootstrap_v3_source_normalization = observed_recover_normalization
    type(pipeline).run = observed_pipeline_run
    type(graph_bundle).execute = observed_graph_execute
    type(normalization_owner).normalize_after_recovery_claim = observed_normalize
    type(normalization_interpreter).interpret = observed_interpret
    type(normalization_stage).normalize = observed_stage_normalize
    reduction_authority_type.create = staticmethod(observed_reduction_authority_create)
    profiler = cProfile.Profile()
    try:
        if profile_enabled:
            profiler.enable()
        (
            elapsed,
            output,
            content_calls,
            blocked_reasons,
            content_validation_families,
            evidence_measurement,
            reference_counterfactual_snapshot,
            reconstruction_trace,
            validation_floor_census,
        ) = _execute(
            service,
            measure_evidence=measure_evidence,
            reference_counterfactual=reference_counterfactual,
            trace_reconstruction=trace_reconstruction,
            trace_validation_floor=trace_validation_floor,
        )
        if profile_enabled:
            profiler.disable()
    finally:
        del reduction_authority_type.create
        type(normalization_stage).normalize = original_stage_normalize
        type(normalization_interpreter).interpret = original_interpret
        type(normalization_owner).normalize_after_recovery_claim = original_normalize
        type(graph_bundle).execute = original_graph_execute
        type(pipeline).run = original_pipeline_run
        type(atomic_store).publish_prepared_source = original_semantic_publish
        type(
            atomic_store
        ).recover_bootstrap_v3_source_normalization = original_recover_normalization
        type(atomic_store).publish_bootstrap_prepared_source_if_absent = original_bootstrap_publish
        type(repository).load = original_repository_load
        type(preparation).prepare_and_publish = original_prepare_publish
        type(ingestion)._run_semantic_ingestion = original_run_semantic
        for module, attribute, original in reversed(patched_codec_bindings):
            setattr(module, attribute, original)
        PreparedSource.model_validate = original_validate
        issuer.close()

    if trace_only:
        profile_rows = []
        for entry in profiler.getstats() if profile_enabled else ():
            code = entry.code
            if not hasattr(code, "co_filename"):
                continue
            profile_rows.append(
                {
                    "function": f"{code.co_filename}:{code.co_firstlineno}:{code.co_qualname}",
                    "calls": entry.callcount,
                    "inline_seconds": entry.inlinetime,
                    "cumulative_seconds": entry.totaltime,
                }
            )
        profile_rows.sort(
            key=lambda row: float(row["cumulative_seconds"]), reverse=True
        )
        print(
            json.dumps(
                {
                    "mode": mode,
                    "elapsed_seconds": elapsed,
                    "output_sha256": sha256(output).hexdigest(),
                    "content_validation_calls": content_calls,
                    "producer_calls": counting.calls,
                    "bootstrap_publish_calls": bootstrap_publish_calls,
                    "semantic_publish_calls": semantic_publish_calls,
                    "repository_load_calls": repository_load_calls,
                    "persisted_reload_hits": persisted_reload_hits,
                    "pipeline_run_calls": pipeline_run_calls,
                    "graph_execute_calls": graph_execute_calls,
                    "graph_outcomes": graph_outcomes,
                    "normalization_lane_calls": lane_calls,
                    "normalization_outcomes": normalization_outcomes,
                    "normalization_boundary_events": normalization_boundary_events,
                    "reduction_authority_clause_diagnostics": (
                        reduction_authority_clause_diagnostics
                    ),
                    "content_validation_families": dict(
                        sorted(
                            content_validation_families.items(),
                            key=lambda item: int(item[1]["calls"]),
                            reverse=True,
                        )
                    ),
                    "profile_top_cumulative": profile_rows[:40],
                    "validated_evidence_measurement": evidence_measurement,
                    "reference_digest_counterfactual": (
                        reference_counterfactual_snapshot
                    ),
                    "reconstruction_trace": reconstruction_trace,
                    "normalization_reload_bundle": normalization_reload_metrics,
                    "validation_floor_census": validation_floor_census,
                    "hierarchical_closure_proof": hierarchical_closure_metrics,
                    "family_complete_closure_proof": family_complete_metrics,
                    "blocked_reasons": blocked_reasons,
                    "pipeline_run_identities": pipeline_run_identities,
                    "installed_identities": installed_identities,
                },
                sort_keys=True,
            )
        )
        return

    if pipeline_run_calls != 1:
        raise RuntimeError(
            "fixture did not execute the pipeline exactly once: "
            f"calls={pipeline_run_calls}, identities={pipeline_run_identities}, "
            f"installed={installed_identities}"
        )
    if not installed_identities:
        raise RuntimeError("provider did not enter the semantic-ingestion path")
    if bootstrap_publish_calls != 1:
        raise RuntimeError(f"bootstrap publication count changed: {bootstrap_publish_calls}")
    if mode == "persisted_reload":
        if (
            counting.calls != 1
            or semantic_publish_calls != 0
            or persisted_reload_hits != 1
            or repository_load_calls != 2
        ):
            raise RuntimeError(
                "pipeline persisted reload lifecycle mismatch: "
                f"producer={counting.calls}, semantic_publish={semantic_publish_calls}, "
                f"reload_hits={persisted_reload_hits}, repository_loads={repository_load_calls}"
            )
    elif counting.calls != 2 or semantic_publish_calls != 1 or persisted_reload_hits != 0 or repository_load_calls != 1:
        raise RuntimeError(
            "pipeline baseline or rollback lifecycle mismatch: "
            f"producer={counting.calls}, semantic_publish={semantic_publish_calls}, "
            f"reload_hits={persisted_reload_hits}, repository_loads={repository_load_calls}"
        )
    registered_sites = [site for site, registered in validation_sites if registered]
    if any(site != "prepare" for site in registered_sites):
        raise RuntimeError(f"private authority crossed a mandatory boundary: {registered_sites}")
    print(
        json.dumps(
            {
                "mode": mode,
                "elapsed_seconds": elapsed,
                "output_sha256": sha256(output).hexdigest(),
                "content_validation_calls": content_calls,
                "producer_calls": counting.calls,
                "bootstrap_publish_calls": bootstrap_publish_calls,
                "semantic_publish_calls": semantic_publish_calls,
                "repository_load_calls": repository_load_calls,
                "persisted_reload_hits": persisted_reload_hits,
                "pipeline_run_calls": pipeline_run_calls,
                "pipeline_run_identities": pipeline_run_identities,
                "installed_identities": installed_identities,
                "registered_validation_sites": registered_sites,
                "ordinary_validation_sites": [
                    site for site, registered in validation_sites if not registered
                ],
            },
            sort_keys=True,
        )
    )


def _distribution(values: list[float]) -> dict[str, float]:
    return {
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
        "mean": statistics.fmean(values),
        "population_stdev": statistics.pstdev(values),
    }


def _parent() -> None:
    script = Path(__file__).resolve()
    order = [(sample, mode) for sample in range(SAMPLES) for mode in MODES]
    random.Random(SEED).shuffle(order)
    env = dict(os.environ)
    env["PYTHONPATH"] = "memorii"
    runs: list[dict[str, object]] = []
    for ordinal, (sample, mode) in enumerate(order):
        try:
            completed = subprocess.run(
                [sys.executable, str(script), "--child", mode],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=CHILD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"PBD-EXP-005 child timed out: {ordinal=} {sample=} {mode=}") from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"PBD-EXP-005 child failed: {ordinal=} {sample=} {mode=} "
                f"stderr={completed.stderr[-3000:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        run = json.loads(lines[-1])
        run.update({"ordinal": ordinal, "sample": sample})
        runs.append(run)

    if len({str(run["output_sha256"]) for run in runs}) != 1:
        raise RuntimeError("pipeline duplicate-lifecycle cells emitted different output bytes")
    distributions = {
        mode: _distribution(
            [float(run["elapsed_seconds"]) for run in runs if run["mode"] == mode]
        )
        for mode in MODES
    }
    validation_counts = {
        mode: sorted(
            {int(run["content_validation_calls"]) for run in runs if run["mode"] == mode}
        )
        for mode in MODES
    }
    if any(len(counts) != 1 for counts in validation_counts.values()):
        raise RuntimeError(f"pipeline validation accounting was nondeterministic: {validation_counts}")
    if validation_counts["rollback"] != validation_counts["safe_reference"]:
        raise RuntimeError("pipeline rollback did not restore baseline validation accounting")
    baseline = distributions["safe_reference"]["median"]
    optimized = distributions["persisted_reload"]["median"]
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.pipeline-duplicate-step2.v1",
        "experiment": "PBD-EXP-005",
        "decision": "DUPLICATE_STEP2_PIPELINE_FAMILY_CONFIRMED",
        "evidence_stage": "reference_only_diagnostic",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "fixture_authority": (
            "test_normal_provider_accepted_control_commits_complete_effect_group"
        ),
        "manifest": {
            "samples_per_mode": SAMPLES,
            "random_seed": SEED,
            "child_timeout_seconds": CHILD_TIMEOUT_SECONDS,
            "script_sha256": sha256(script.read_bytes()).hexdigest(),
            "order": [
                {"ordinal": run["ordinal"], "sample": run["sample"], "mode": run["mode"]}
                for run in runs
            ],
        },
        "output_sha256": str(runs[0]["output_sha256"]),
        "distributions_seconds": distributions,
        "validation_counts": validation_counts,
        "persisted_reload_median_reduction_fraction": 1.0 - optimized / baseline,
        "pipeline_run_calls_per_cell": 1,
        "counterfactual_boundary": (
            "The existing accepted-control provider fixture supplies all business authority. "
            "Bootstrap publication, handoff, full persisted reload, production preparation binding "
            "checks, pipeline execution/reload, accepted terminal, and complete durable effects execute."
        ),
        "runs": runs,
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-005-pipeline-duplicate-step2-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, sort_keys=True))


def _counterfactual_parent() -> None:
    script = Path(__file__).resolve()
    env = dict(os.environ)
    env["PYTHONPATH"] = "memorii"
    runs: dict[str, dict[str, Any]] = {}
    for name, extra_arguments in (
        ("safe_reference_a", []),
        ("safe_reference_b", []),
        ("reference_counterfactual", ["--reference-counterfactual"]),
    ):
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--child",
                    "safe_reference",
                    "--trace-only",
                    *extra_arguments,
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=COUNTERFACTUAL_CHILD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"reference counterfactual child timed out: {name}") from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"reference counterfactual child failed: {name}: "
                f"stderr={completed.stderr[-3000:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        runs[name] = json.loads(lines[-1])
    baseline_a = runs["safe_reference_a"]
    baseline_b = runs["safe_reference_b"]
    counterfactual = runs["reference_counterfactual"]

    def without_elapsed(rows: object) -> object:
        if isinstance(rows, list):
            return [without_elapsed(row) for row in rows]
        if isinstance(rows, dict):
            return {
                key: without_elapsed(value)
                for key, value in rows.items()
                if key != "elapsed_seconds"
            }
        return rows

    def promise_projection(run: dict[str, Any]) -> dict[str, object]:
        return {
            "blocked_reasons": run["blocked_reasons"],
            "producer_calls": run["producer_calls"],
            "bootstrap_publish_calls": run["bootstrap_publish_calls"],
            "semantic_publish_calls": run["semantic_publish_calls"],
            "repository_load_calls": run["repository_load_calls"],
            "persisted_reload_hits": run["persisted_reload_hits"],
            "pipeline_run_calls": run["pipeline_run_calls"],
            "graph_execute_calls": run["graph_execute_calls"],
            "graph_outcomes": without_elapsed(run["graph_outcomes"]),
            "normalization_lane_calls": run["normalization_lane_calls"],
            "normalization_outcomes": without_elapsed(run["normalization_outcomes"]),
            "normalization_boundary_events": without_elapsed(
                run["normalization_boundary_events"]
            ),
            "reduction_authority_clause_diagnostics": run[
                "reduction_authority_clause_diagnostics"
            ],
            "content_validation_calls": run["content_validation_calls"],
            "content_validation_families": run["content_validation_families"],
            "pipeline_identity": [
                {
                    "exact_selected_pipeline": row["exact_selected_pipeline"],
                    "pipeline_type": row["pipeline_type"],
                }
                for row in run["pipeline_run_identities"]
            ],
            "installed_identity_checks": {
                key: value
                for key, value in run["installed_identities"].items()
                if key.endswith("_exact")
            },
        }

    baseline_a_promises = promise_projection(baseline_a)
    baseline_b_promises = promise_projection(baseline_b)
    counterfactual_promises = promise_projection(counterfactual)
    if baseline_a_promises != baseline_b_promises:
        raise RuntimeError("unchanged baseline promise projection was nondeterministic")
    if baseline_a_promises != counterfactual_promises:
        raise RuntimeError("reference counterfactual changed the production promise projection")
    snapshot = counterfactual["reference_digest_counterfactual"]
    baseline_elapsed = statistics.median(
        [float(baseline_a["elapsed_seconds"]), float(baseline_b["elapsed_seconds"])]
    )
    exact_output_hashes = {
        "safe_reference_a": baseline_a["output_sha256"],
        "safe_reference_b": baseline_b["output_sha256"],
        "reference_counterfactual": counterfactual["output_sha256"],
    }
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.reference-digest-counterfactual.v1",
        "experiment": "PBD-EXP-006",
        "evidence_stage": "reference_only_diagnostic",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "promise_projection_sha256": sha256(
            json.dumps(baseline_a_promises, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "promise_projection_equal": True,
        "exact_output_hashes": exact_output_hashes,
        "exact_output_hash_cross_process_stable": len(set(exact_output_hashes.values())) == 1,
        "elapsed_seconds": {
            "safe_reference_a": baseline_a["elapsed_seconds"],
            "safe_reference_b": baseline_b["elapsed_seconds"],
            "safe_reference_median": baseline_elapsed,
            "reference_counterfactual": counterfactual["elapsed_seconds"],
        },
        "elapsed_reduction_fraction": 1.0
        - float(counterfactual["elapsed_seconds"]) / baseline_elapsed,
        "content_validation_calls": {
            "safe_reference_a": baseline_a["content_validation_calls"],
            "safe_reference_b": baseline_b["content_validation_calls"],
            "reference_counterfactual": counterfactual["content_validation_calls"],
        },
        "digest_computations": {
            "safe_reference_a": baseline_a["reference_digest_counterfactual"]["digest_computations"],
            "safe_reference_b": baseline_b["reference_digest_counterfactual"]["digest_computations"],
            "reference_counterfactual": snapshot["digest_computations"],
        },
        "counterfactual_snapshot": snapshot,
        "coherence_contract": (
            "Reuse requires the same strongly held frozen model reference, concrete type, digest domain, "
            "declared digest, and recursively unchanged immutable reference shape. Mutable values, changed "
            "shape, equal-but-distinct objects, capacity exhaustion, and non-admitted values fall back to "
            "the complete production digest calculation; all other production validators still execute."
        ),
        "bounds": {
            "scope": "one isolated provider operation child",
            "maximum_entries": _ReferenceDigestCounterfactual.MAX_ENTRIES,
            "maximum_charged_bytes": _ReferenceDigestCounterfactual.MAX_CHARGED_BYTES,
            "entry_charge_bytes": _ReferenceDigestCounterfactual.ENTRY_CHARGE,
            "eviction": "none; fail closed to production calculation at capacity",
        },
        "runs": runs,
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-006-reference-digest-counterfactual-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, sort_keys=True))


def _reconstruction_trace_parent() -> None:
    script = Path(__file__).resolve()
    env = dict(os.environ)
    env["PYTHONPATH"] = "memorii"
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--child",
                "safe_reference",
                "--trace-only",
                "--trace-reconstruction",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=COUNTERFACTUAL_CHILD_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("seven-family reconstruction trace timed out") from error
    if completed.returncode != 0:
        raise RuntimeError(
            "seven-family reconstruction trace failed: "
            f"stderr={completed.stderr[-3000:]!r}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    run = json.loads(lines[-1])
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.seven-family-reconstruction-trace.v1",
        "experiment": "PBD-EXP-007",
        "evidence_stage": "reference_only_diagnostic",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "elapsed_seconds": run["elapsed_seconds"],
        "output_sha256": run["output_sha256"],
        "content_validation_calls": run["content_validation_calls"],
        "graph_outcomes": run["graph_outcomes"],
        "normalization_outcomes": run["normalization_outcomes"],
        "blocked_reasons": run["blocked_reasons"],
        "reconstruction_trace": run["reconstruction_trace"],
        "trace_boundary": (
            "Generation-safe weak-reference object tokens distinguish equal-content model "
            "reconstruction without retaining production object graphs. Stack aggregation is "
            "bounded to the seven measured families and 30 sites plus 24 first events per family."
        ),
        "manifest": {
            "child_timeout_seconds": COUNTERFACTUAL_CHILD_TIMEOUT_SECONDS,
            "script_sha256": sha256(script.read_bytes()).hexdigest(),
            "families": sorted(RECONSTRUCTION_TRACE_FAMILIES),
        },
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-007-seven-family-reconstruction-trace-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        family.rsplit(".", 1)[-1]: {
            "validations": row["validations"],
            "unique_content_identities": row["unique_content_identities"],
            "unique_object_instances": row["unique_object_instances"],
            "equal_content_reconstructions": row["equal_content_reconstructions"],
            "origins": row["origins"],
        }
        for family, row in run["reconstruction_trace"].items()
    }
    aggregate_stack_sites: Counter[tuple[str, ...]] = Counter()
    for row in run["reconstruction_trace"].values():
        for site in row["stack_sites"]:
            aggregate_stack_sites[tuple(site["stack"])] += int(site["validations"])
    print(
        json.dumps(
            {
                "experiment": result["experiment"],
                "elapsed_seconds": result["elapsed_seconds"],
                "content_validation_calls": result["content_validation_calls"],
                "families": summary,
                "top_concrete_stack_sites": [
                    {"validations": count, "stack": stack}
                    for stack, count in aggregate_stack_sites.most_common(30)
                ],
                "evidence": str(evidence),
            },
            sort_keys=True,
        )
    )


def _normalization_reload_counterfactual_parent() -> None:
    script = Path(__file__).resolve()
    env = dict(os.environ)
    env["PYTHONPATH"] = "memorii"
    runs: dict[str, dict[str, Any]] = {}
    for name, extra_arguments in (
        ("safe_reference", []),
        (
            "generation_bound_bundle",
            ["--normalization-reload-counterfactual"],
        ),
    ):
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--child",
                    "safe_reference",
                    "--trace-only",
                    *extra_arguments,
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=COUNTERFACTUAL_CHILD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"normalization reload counterfactual timed out: {name}"
            ) from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"normalization reload counterfactual failed: {name}: "
                f"stderr={completed.stderr[-3000:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        runs[name] = json.loads(lines[-1])

    def without_elapsed(rows: object) -> object:
        if isinstance(rows, list):
            return [without_elapsed(row) for row in rows]
        if isinstance(rows, dict):
            return {
                key: without_elapsed(value)
                for key, value in rows.items()
                if key != "elapsed_seconds"
            }
        return rows

    def promise_projection(run: dict[str, Any]) -> dict[str, object]:
        return {
            "blocked_reasons": run["blocked_reasons"],
            "producer_calls": run["producer_calls"],
            "bootstrap_publish_calls": run["bootstrap_publish_calls"],
            "semantic_publish_calls": run["semantic_publish_calls"],
            "repository_load_calls": run["repository_load_calls"],
            "persisted_reload_hits": run["persisted_reload_hits"],
            "pipeline_run_calls": run["pipeline_run_calls"],
            "graph_execute_calls": run["graph_execute_calls"],
            "graph_outcomes": without_elapsed(run["graph_outcomes"]),
            "normalization_lane_calls": run["normalization_lane_calls"],
            "normalization_outcomes": without_elapsed(run["normalization_outcomes"]),
            "normalization_boundary_events": without_elapsed(
                run["normalization_boundary_events"]
            ),
            "reduction_authority_clause_diagnostics": run[
                "reduction_authority_clause_diagnostics"
            ],
            "pipeline_identity": [
                {
                    "exact_selected_pipeline": row["exact_selected_pipeline"],
                    "pipeline_type": row["pipeline_type"],
                }
                for row in run["pipeline_run_identities"]
            ],
            "installed_identity_checks": {
                key: value
                for key, value in run["installed_identities"].items()
                if key.endswith("_exact")
            },
        }

    baseline = runs["safe_reference"]
    counterfactual = runs["generation_bound_bundle"]
    baseline_promises = promise_projection(baseline)
    counterfactual_promises = promise_projection(counterfactual)
    if baseline_promises != counterfactual_promises:
        raise RuntimeError(
            "generation-bound normalization bundle changed the production promise projection"
        )
    bundle = counterfactual["normalization_reload_bundle"]
    if (
        bundle["admissions"] != 1
        or bundle["hits"] != 2
        or bundle["full_validations"] != 1
        or bundle["coherence_checks"] != 2
        or bundle["coherence_rejections"] != 0
        or bundle["capacity_fallbacks"] != 0
    ):
        raise RuntimeError(
            f"generation-bound normalization bundle lifecycle mismatch: {bundle}"
        )
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.normalization-reload-bundle-counterfactual.v1",
        "experiment": "PBD-EXP-009",
        "evidence_stage": "reference_only_diagnostic",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "promise_projection_equal": True,
        "promise_projection_sha256": sha256(
            json.dumps(baseline_promises, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "elapsed_seconds": {
            "safe_reference": baseline["elapsed_seconds"],
            "generation_bound_bundle": counterfactual["elapsed_seconds"],
        },
        "elapsed_reduction_fraction": 1.0
        - float(counterfactual["elapsed_seconds"])
        / float(baseline["elapsed_seconds"]),
        "content_validation_calls": {
            "safe_reference": baseline["content_validation_calls"],
            "generation_bound_bundle": counterfactual["content_validation_calls"],
        },
        "eliminated_content_validations": int(baseline["content_validation_calls"])
        - int(counterfactual["content_validation_calls"]),
        "bundle": bundle,
        "bounds": {
            "maximum_bundles": 1,
            "maximum_retained_payload_bytes": NORMALIZATION_RELOAD_BUNDLE_MAX_BYTES,
            "scope": "one exact atomic-store owner and provider operation",
            "eviction": "none; mismatch or overflow falls back to complete validation",
        },
        "coherence_contract": (
            "Admission follows one complete production committed-generation validation. "
            "Every reuse re-reads the recovery index and generation-member envelopes and "
            "requires the same atomic-store owner, recovery key, namespace, generation, "
            "atomic request digest, result digest, ordered member IDs, member kinds, declared "
            "payload digests, actual payload SHA-256 values, and payload lengths."
        ),
        "runs": runs,
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-009-normalization-reload-bundle-counterfactual-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, sort_keys=True))


def _validation_floor_census_parent() -> None:
    script = Path(__file__).resolve()
    env = dict(os.environ)
    env["PYTHONPATH"] = "memorii"
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--child",
                "safe_reference",
                "--trace-only",
                "--trace-validation-floor",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=COUNTERFACTUAL_CHILD_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("mandatory validation floor census timed out") from error
    if completed.returncode != 0:
        raise RuntimeError(
            "mandatory validation floor census failed: "
            f"stderr={completed.stderr[-3000:]!r}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    run = json.loads(lines[-1])
    census = run["validation_floor_census"]
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.mandatory-validation-floor-census.v1",
        "experiment": "PBD-EXP-010",
        "evidence_stage": "reference_only_diagnostic",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "elapsed_seconds": run["elapsed_seconds"],
        "output_sha256": run["output_sha256"],
        "census": census,
        "classification_contract": {
            "mandatory_boundary_root": (
                "The identity is itself the root expected type of a persisted or writer-admission decode."
            ),
            "aggregate_coverable_candidate": (
                "The identity is nested beneath a persisted or writer-admission root but is never itself "
                "observed as that boundary root; coverage requires a future authenticated closure proof."
            ),
            "in_process_only_candidate": (
                "The identity is not observed in a persisted or writer-admission decode stack in this run; "
                "it still requires classification as static-reusable, necessary derived, or eliminable transient."
            ),
        },
        "manifest": {
            "child_timeout_seconds": COUNTERFACTUAL_CHILD_TIMEOUT_SECONDS,
            "script_sha256": sha256(script.read_bytes()).hexdigest(),
        },
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-010-mandatory-validation-floor-census-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "experiment": result["experiment"],
                "elapsed_seconds": result["elapsed_seconds"],
                "unique_content_identities": census["unique_content_identities"],
                "total_validations": census["total_validations"],
                "repeat_validations": census["repeat_validations"],
                "classification_identity_counts": census[
                    "classification_identity_counts"
                ],
                "classification_validation_counts": census[
                    "classification_validation_counts"
                ],
                "mandatory_boundary_root_families": census[
                    "mandatory_boundary_root_families"
                ],
                "boundary_events": census["boundary_events"],
                "writer_required_occurrences": census[
                    "writer_required_occurrences"
                ],
                "nonwriter_event_identity_floor": census[
                    "nonwriter_event_identity_floor"
                ],
                "in_process_role_identity_counts": census[
                    "in_process_role_identity_counts"
                ],
                "in_process_role_validation_counts": census[
                    "in_process_role_validation_counts"
                ],
                "conservative_security_adjusted_floor": census[
                    "conservative_security_adjusted_floor"
                ],
                "evidence": str(evidence),
            },
            sort_keys=True,
        )
    )


def _hierarchical_closure_counterfactual_parent() -> None:
    script = Path(__file__).resolve()
    env = dict(os.environ)
    env["PYTHONPATH"] = "memorii"
    runs: dict[str, dict[str, Any]] = {}
    for name, extra_arguments in (
        ("safe_reference", []),
        ("hierarchical_closure_proof", ["--hierarchical-closure-counterfactual"]),
    ):
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--child",
                    "safe_reference",
                    "--trace-only",
                    *extra_arguments,
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=COUNTERFACTUAL_CHILD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"hierarchical closure counterfactual timed out: {name}"
            ) from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"hierarchical closure counterfactual failed: {name}: "
                f"stderr={completed.stderr[-3000:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        runs[name] = json.loads(lines[-1])

    def without_elapsed(rows: object) -> object:
        if isinstance(rows, list):
            return [without_elapsed(row) for row in rows]
        if isinstance(rows, dict):
            return {
                key: without_elapsed(value)
                for key, value in rows.items()
                if key != "elapsed_seconds"
            }
        return rows

    def promise_projection(run: dict[str, Any]) -> dict[str, object]:
        return {
            "blocked_reasons": run["blocked_reasons"],
            "producer_calls": run["producer_calls"],
            "bootstrap_publish_calls": run["bootstrap_publish_calls"],
            "semantic_publish_calls": run["semantic_publish_calls"],
            "repository_load_calls": run["repository_load_calls"],
            "persisted_reload_hits": run["persisted_reload_hits"],
            "pipeline_run_calls": run["pipeline_run_calls"],
            "graph_execute_calls": run["graph_execute_calls"],
            "graph_outcomes": without_elapsed(run["graph_outcomes"]),
            "normalization_lane_calls": run["normalization_lane_calls"],
            "normalization_outcomes": without_elapsed(run["normalization_outcomes"]),
            "normalization_boundary_events": without_elapsed(
                run["normalization_boundary_events"]
            ),
            "reduction_authority_clause_diagnostics": run[
                "reduction_authority_clause_diagnostics"
            ],
        }

    baseline = runs["safe_reference"]
    counterfactual = runs["hierarchical_closure_proof"]
    baseline_promises = promise_projection(baseline)
    if baseline_promises != promise_projection(counterfactual):
        raise RuntimeError(
            "hierarchical closure proof changed the production promise projection"
        )
    proof = counterfactual["hierarchical_closure_proof"]
    digest = counterfactual["reference_digest_counterfactual"]
    if (
        proof["admissions"] != 1
        or proof["full_admission_validations"] != 1
        or proof["proof_covered_revalidations"] != 2
        or proof["coherence_checks"] != 2
        or proof["coherence_rejections"] != 0
        or proof["capacity_fallbacks"] != 0
        or digest["hierarchical_proof_covered_digest_validations"] <= 0
    ):
        raise RuntimeError(f"hierarchical closure proof lifecycle mismatch: {proof}")
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.hierarchical-closure-counterfactual.v1",
        "experiment": "PBD-EXP-012",
        "evidence_stage": "reference_only_diagnostic",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "promise_projection_equal": True,
        "promise_projection_sha256": sha256(
            json.dumps(baseline_promises, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "elapsed_seconds": {
            "safe_reference": baseline["elapsed_seconds"],
            "hierarchical_closure_proof": counterfactual["elapsed_seconds"],
        },
        "elapsed_reduction_fraction": 1.0
        - float(counterfactual["elapsed_seconds"])
        / float(baseline["elapsed_seconds"]),
        "content_validator_executions": {
            "safe_reference": baseline["content_validation_calls"],
            "hierarchical_closure_proof": counterfactual["content_validation_calls"],
        },
        "full_digest_computations": {
            "safe_reference": baseline["reference_digest_counterfactual"]["digest_computations"],
            "hierarchical_closure_proof": digest["digest_computations"],
        },
        "proof_covered_digest_validations": digest[
            "hierarchical_proof_covered_digest_validations"
        ],
        "proof": proof,
        "bounds": {
            "maximum_proofs": 1,
            "maximum_retained_payload_bytes": NORMALIZATION_RELOAD_BUNDLE_MAX_BYTES,
            "scope": "one exact atomic-store owner, recovery key, generation and provider operation",
        },
        "security_contract": (
            "Proof admission follows complete bounded production validation of one committed generation. "
            "Each proof-covered revalidation first re-reads and matches the recovery index plus every "
            "ordered member envelope and actual payload SHA-256. Bounded decode, concrete root typing, "
            "all semantic validators, cross-member closure checks, re-encoding checks, authority-specific "
            "decodes and writer admission remain active; only nested content-digest recomputation is covered."
        ),
        "runs": runs,
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-012-hierarchical-closure-counterfactual-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, sort_keys=True))


def _family_complete_closure_counterfactual_parent() -> None:
    script = Path(__file__).resolve()
    env = dict(os.environ)
    env["PYTHONPATH"] = "memorii"
    runs: dict[str, dict[str, Any]] = {}
    for name, extra_arguments in (
        ("safe_reference", []),
        ("family_complete_closure", ["--family-complete-closure-counterfactual"]),
    ):
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--child",
                    "safe_reference",
                    "--trace-only",
                    *extra_arguments,
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=COUNTERFACTUAL_CHILD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"family-complete closure counterfactual timed out: {name}"
            ) from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"family-complete closure counterfactual failed: {name}: "
                f"stderr={completed.stderr[-3000:]!r}"
            )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        runs[name] = json.loads(lines[-1])

    def without_elapsed(rows: object) -> object:
        if isinstance(rows, list):
            return [without_elapsed(row) for row in rows]
        if isinstance(rows, dict):
            return {
                key: without_elapsed(value)
                for key, value in rows.items()
                if key != "elapsed_seconds"
            }
        return rows

    def promise_projection(run: dict[str, Any]) -> dict[str, object]:
        return {
            "blocked_reasons": run["blocked_reasons"],
            "producer_calls": run["producer_calls"],
            "bootstrap_publish_calls": run["bootstrap_publish_calls"],
            "semantic_publish_calls": run["semantic_publish_calls"],
            "repository_load_calls": run["repository_load_calls"],
            "persisted_reload_hits": run["persisted_reload_hits"],
            "pipeline_run_calls": run["pipeline_run_calls"],
            "graph_execute_calls": run["graph_execute_calls"],
            "graph_outcomes": without_elapsed(run["graph_outcomes"]),
            "normalization_lane_calls": run["normalization_lane_calls"],
            "normalization_outcomes": without_elapsed(run["normalization_outcomes"]),
            "normalization_boundary_events": without_elapsed(
                run["normalization_boundary_events"]
            ),
            "reduction_authority_clause_diagnostics": run[
                "reduction_authority_clause_diagnostics"
            ],
        }

    baseline = runs["safe_reference"]
    counterfactual = runs["family_complete_closure"]
    baseline_promises = promise_projection(baseline)
    if baseline_promises != promise_projection(counterfactual):
        raise RuntimeError(
            "family-complete closure proof changed the production promise projection"
        )
    baseline_digest = baseline["reference_digest_counterfactual"]
    counterfactual_digest = counterfactual["reference_digest_counterfactual"]
    proof = counterfactual["family_complete_closure_proof"]
    full_computations = int(counterfactual_digest["digest_computations"])
    repeated_baseline = int(baseline_digest["digest_computations"]) - 238
    repeated_remaining = max(0, full_computations - 238)
    repeated_reduction_fraction = 1.0 - repeated_remaining / repeated_baseline
    result = {
        "schema": "memorii.semantic-ingestion.production-performance.family-complete-closure-counterfactual.v1",
        "experiment": "PBD-EXP-013",
        "evidence_stage": "reference_only_diagnostic",
        "production_implementation_changed": False,
        "certifies_m3_1": False,
        "decision": (
            "REPEATED_DIGEST_REDUCTION_TARGET_MET"
            if repeated_reduction_fraction >= 0.90
            else "REPEATED_DIGEST_REDUCTION_TARGET_NOT_MET"
        ),
        "promise_projection_equal": True,
        "promise_projection_sha256": sha256(
            json.dumps(baseline_promises, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "elapsed_seconds": {
            "safe_reference": baseline["elapsed_seconds"],
            "family_complete_closure": counterfactual["elapsed_seconds"],
        },
        "elapsed_reduction_fraction": 1.0
        - float(counterfactual["elapsed_seconds"])
        / float(baseline["elapsed_seconds"]),
        "full_digest_computations": {
            "safe_reference": baseline_digest["digest_computations"],
            "family_complete_closure": full_computations,
        },
        "proof_covered_digest_validations": counterfactual_digest[
            "hierarchical_proof_covered_digest_validations"
        ],
        "repeated_digest_computations": {
            "safe_reference": repeated_baseline,
            "family_complete_closure": repeated_remaining,
        },
        "repeated_digest_reduction_fraction": repeated_reduction_fraction,
        "target": {
            "minimum_repeated_digest_reduction_fraction": 0.90,
            "maximum_repeated_digest_computations": 4_272,
            "maximum_total_full_digest_computations": 4_510,
        },
        "proof": proof,
        "bounds": {
            "maximum_entries": FAMILY_COMPLETE_PROOF_MAX_ENTRIES,
            "maximum_root_bytes": FAMILY_COMPLETE_PROOF_MAX_ROOT_BYTES,
            "maximum_charged_bytes": FAMILY_COMPLETE_PROOF_MAX_CHARGED_BYTES,
            "scope": "one provider operation; writer proofs are unique per write invocation",
        },
        "security_contract": (
            "A miss performs complete production validation before admitting exact root bytes and "
            "concrete type in one trust-event scope. A hit requires byte-for-byte root equality. "
            "Writer scopes include the concrete writer-admission invocation and cannot authorize "
            "another write. All semantic validators, decoder bounds, closure checks and writer "
            "admissions execute; only nested content-digest recomputation is proof-covered."
        ),
        "runs": runs,
    }
    evidence = DEBUG_WORK / "evidence/pbd-exp-013-family-complete-closure-counterfactual-v1.json"
    evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=MODES)
    parser.add_argument("--trace-only", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--measure-evidence", action="store_true")
    parser.add_argument("--reference-counterfactual", action="store_true")
    parser.add_argument("--reference-counterfactual-pair", action="store_true")
    parser.add_argument("--trace-reconstruction", action="store_true")
    parser.add_argument("--reconstruction-trace-parent", action="store_true")
    parser.add_argument("--normalization-reload-counterfactual", action="store_true")
    parser.add_argument(
        "--normalization-reload-counterfactual-pair", action="store_true"
    )
    parser.add_argument("--trace-validation-floor", action="store_true")
    parser.add_argument("--validation-floor-census", action="store_true")
    parser.add_argument("--hierarchical-closure-counterfactual", action="store_true")
    parser.add_argument(
        "--hierarchical-closure-counterfactual-pair", action="store_true"
    )
    parser.add_argument("--family-complete-closure-counterfactual", action="store_true")
    parser.add_argument(
        "--family-complete-closure-counterfactual-pair", action="store_true"
    )
    arguments = parser.parse_args()
    if arguments.family_complete_closure_counterfactual_pair:
        _family_complete_closure_counterfactual_parent()
    elif arguments.hierarchical_closure_counterfactual_pair:
        _hierarchical_closure_counterfactual_parent()
    elif arguments.validation_floor_census:
        _validation_floor_census_parent()
    elif arguments.normalization_reload_counterfactual_pair:
        _normalization_reload_counterfactual_parent()
    elif arguments.reconstruction_trace_parent:
        _reconstruction_trace_parent()
    elif arguments.reference_counterfactual_pair:
        _counterfactual_parent()
    elif arguments.child:
        _child(
            arguments.child,
            trace_only=arguments.trace_only,
            profile_enabled=arguments.profile,
            measure_evidence=arguments.measure_evidence,
            reference_counterfactual=arguments.reference_counterfactual,
            trace_reconstruction=arguments.trace_reconstruction,
            normalization_reload_counterfactual=(
                arguments.normalization_reload_counterfactual
            ),
            trace_validation_floor=arguments.trace_validation_floor,
            hierarchical_closure_counterfactual=(
                arguments.hierarchical_closure_counterfactual
            ),
            family_complete_closure_counterfactual=(
                arguments.family_complete_closure_counterfactual
            ),
        )
    else:
        _parent()


if __name__ == "__main__":
    main()

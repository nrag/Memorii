"""Tests for the non-default scenario C2 trust fixture."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
    decode_artifact,
    encode_typed_value,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_acceptance_watermark_store import (
    FileTraceabilityReleaseWatermarkStore,
)
from memorii.tools.semantic_ingestion_execution_evidence import (
    ExecutionEvidenceError,
    RegisteredApprovalExecutor,
    _verify_m0_pointer_history,
)
from memorii.tools.semantic_ingestion_release_persistence import (
    FileMonotonicFenceStore,
)
from memorii.tools.semantic_ingestion_release_persistence import (
    FileTraceabilityReleasePublicationStore as _FileTraceabilityReleasePublicationStore,
)
from memorii.tools.semantic_ingestion_scenario_test_trust import (
    CURRENT_GENERATION_MEMBER_ORDER,
    TEST_BOOTSTRAP_KEY,
    TEST_RECOVERY_KEY,
    ExplicitTestIndependentGenerationVerifier,
    _binding,
    build_generation_package,
    build_scenario_test_authority,
    verifier,
)
from memorii.tools.semantic_ingestion_traceability_release import (
    AcceptanceTrustStore,
    VerifierHeldTrustMaterial,
)
from memorii.tools.semantic_ingestion_trust_resolver import DefaultAcceptanceTrustResolver
from tests.fixtures.semantic_ingestion.current_release_chain import (
    _current_chain,
    bind_chain_to_generation,
    current_chain_successor,
)

ROOT = Path(__file__).parents[4]


def FileTraceabilityReleasePublicationStore(path: Path):
    return _FileTraceabilityReleasePublicationStore(
        path,
        FileMonotonicFenceStore(
            path.parent / "fence-domain" / f"{path.name}.minimum.log"
        ),
    )


@lru_cache(maxsize=1)
def _inputs() -> dict[str, Any]:
    scenario = build_scenario_test_authority(
        design_bytes=(ROOT / "docs/design/semantic_ingestion_architecture.md").read_bytes(),
        registry_bytes=(
            ROOT
            / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
        ).read_bytes(),
        authority_bytes=(
            ROOT
            / "docs/design/semantic_ingestion/traceability_golden_vectors/ctv-binding-authority-v2.json"
        ).read_bytes(),
        group_id="semantic-ingestion-r03",
    )
    authority = scenario["authority"]
    roots = scenario["roots"]
    assert isinstance(authority, dict)
    assert isinstance(roots, dict)
    chain = bind_chain_to_generation(
        _current_chain(
            external_roots={
                key: str(roots[key])
                for key in (
                    "design_document_digest",
                    "structural_manifest_digest",
                    "coverage_root_digest",
                    "execution_root_digest",
                    "report_schema_registry_digest",
                    "runner_environment_profile_registry_digest",
                    "trust_snapshot_digest",
                )
            },
            golden_vector_manifest_digest=str(roots["golden_vector_manifest_digest"]),
        ),
        roots={
            key: value
            for key, value in roots.items()
            if isinstance(key, str) and isinstance(value, str)
        },
        binding_for_schema=lambda schema: _binding(authority, schema),
    )
    generation_artifacts = chain["generation_artifacts"]
    assert isinstance(generation_artifacts, dict)
    typed = scenario["typed"]
    assert isinstance(typed, dict)
    typed.update(generation_artifacts)
    typed["bootstrap_anchor"] = chain["bootstrap"]
    typed["recovery_root"] = chain["recovery"]
    typed["recovery_policy"] = chain["policy"]
    typed["active_pointer"] = chain["pointer"]
    scenario.update(
        {
            "material": chain["material"],
            "release_digest": chain["release_digest"],
            "expected_release_roots": chain["roots"],
            "sign": chain["sign"],
            "now": chain["now"],
            "chain": chain,
        }
    )
    return scenario


@lru_cache(maxsize=1)
def _generation_package() -> tuple[bytes, dict[str, bytes]]:
    return build_generation_package(
        built=_inputs(),
        design_bytes=(ROOT / "docs/design/semantic_ingestion_architecture.md").read_bytes(),
        registry_bytes=(
            ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
        ).read_bytes(),
    )


@lru_cache(maxsize=1)
def _successor_inputs() -> tuple[dict[str, Any], bytes, dict[str, bytes]]:
    first = _inputs()
    _generation_package()
    authority = first["authority"]
    roots = first["roots"]
    typed = first["typed"]
    chain = first["chain"]
    assert isinstance(authority, dict)
    assert isinstance(roots, dict)
    assert isinstance(typed, dict)
    assert isinstance(chain, dict)
    prior_pointer = typed["active_pointer"]
    assert isinstance(prior_pointer, bytes)
    successor = bind_chain_to_generation(
        current_chain_successor({**chain, "pointer": prior_pointer}),
        roots={
            key: value
            for key, value in roots.items()
            if isinstance(key, str) and isinstance(value, str)
        },
        binding_for_schema=lambda schema: _binding(authority, schema),
    )
    successor_artifacts = successor["generation_artifacts"]
    assert isinstance(successor_artifacts, dict)
    successor_typed = {**typed, **successor_artifacts}
    successor_typed["active_pointer"] = successor["pointer"]
    built = {
        **first,
        "typed": successor_typed,
        "material": successor["material"],
        "release_digest": successor["release_digest"],
        "expected_release_roots": successor["roots"],
        "sign": successor["sign"],
        "now": successor["now"],
        "prior_pointer": prior_pointer,
        "chain": successor,
    }
    generation, members = build_generation_package(
        built=built,
        design_bytes=(
            ROOT / "docs/design/semantic_ingestion_architecture.md"
        ).read_bytes(),
        registry_bytes=(
            ROOT
            / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
        ).read_bytes(),
    )
    return built, generation, members


def test_scenario_test_trust_is_a_distinct_signed_ctv_authority() -> None:
    built = _inputs()
    typed = built["typed"]
    assert isinstance(typed, dict)
    bootstrap = typed["bootstrap_anchor"]
    recovery = typed["recovery_root"]
    assert isinstance(bootstrap, bytes)
    assert isinstance(recovery, bytes)
    assert decode_artifact(bootstrap).binding.schema_id == "TraceabilityBootstrapTrustAnchorBody.v1"
    assert decode_artifact(recovery).binding.schema_id == "TraceabilityRecoveryTrustRootBody.v1"
    assert TEST_BOOTSTRAP_KEY != TEST_RECOVERY_KEY
    assert verifier("deterministic-v1", TEST_BOOTSTRAP_KEY, b"x", b"bad") is False


def test_scenario_test_trust_is_deterministic() -> None:
    first = _inputs()
    second = _inputs()
    assert first["release_digest"] == second["release_digest"]
    assert first["report_bytes"] == second["report_bytes"]


def test_scenario_generation_uses_the_current_18_member_raw_ledger_closure() -> None:
    generation, members = _generation_package()
    assert generation
    assert len(members) == 18
    member_kinds = tuple(coordinate.split("/")[2] for coordinate in members)
    assert member_kinds == CURRENT_GENERATION_MEMBER_ORDER


def test_scenario_test_trust_passes_only_when_installed_as_explicit_authority() -> None:
    built = _inputs()
    generation, members = _generation_package()
    typed = built["typed"]
    assert isinstance(typed, dict)
    with TemporaryDirectory() as directory:
        publication = FileTraceabilityReleasePublicationStore(Path(directory) / "publication.json")
        assert publication.provision(1, 1, built["release_digest"]).__class__.__name__ == "WatermarkAdvanced"
        authority = AcceptanceTrustStore(
            material=built["material"], watermark_store=publication,
            expected_release_roots=built["expected_release_roots"],
            publication_store=publication,
            allow_test_file_fence=True,
            independent_generation_verifier=built["independent_generation_verifier"],
        )
        result = RegisteredApprovalExecutor(authority).execute(
            registry_bytes=(ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json").read_bytes(),
            group_id=built["group_id"], report_bytes=built["report_bytes"],
            artifacts=built["artifacts"], implementation_revision="scenario-c2",
            implementation_tree_digest="a" * 64, environment_observation_bytes=built["environment"],
            bootstrap_artifact=typed["bootstrap_anchor"], recovery_artifact=typed["recovery_root"],
            lifecycle_artifact=typed["trust_lifecycle_root"], release_artifact=typed["release"],
            active_pointer_artifact=typed["active_pointer"], release_history_artifact=typed["release_history"],
            pointer_history_artifact=next(
                raw for coordinate, raw in members.items() if "/pointer_history/" in coordinate
            ),
            generation_manifest_bytes=generation, generation_member_bytes=members,
            design_document_bytes=(ROOT / "docs/design/semantic_ingestion_architecture.md").read_bytes(),
            now=built["now"],
        )
        inventory = publication.version_inventory()
        assert inventory.state == "corrected_v2"
        assert inventory.corrected_v2_tail_count == 1
        assert inventory.current is not None
    assert result["command_id"]


def test_registered_scenario_publishes_sequence_two_after_sequence_one() -> None:
    first = _inputs()
    first_generation, first_members = _generation_package()
    second, second_generation, second_members = _successor_inputs()

    def publish(
        built: dict[str, Any],
        generation: bytes,
        members: dict[str, bytes],
        authority: AcceptanceTrustStore,
        *,
        report_bytes: bytes | None = None,
        environment_bytes: bytes | None = None,
        artifacts: dict[str, bytes] | None = None,
    ) -> None:
        typed = built["typed"]
        assert isinstance(typed, dict)
        RegisteredApprovalExecutor(authority).execute(
            registry_bytes=(
                ROOT
                / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
            ).read_bytes(),
            group_id=built["group_id"],
            report_bytes=built["report_bytes"] if report_bytes is None else report_bytes,
            artifacts=built["artifacts"] if artifacts is None else artifacts,
            implementation_revision="scenario-c2",
            implementation_tree_digest="a" * 64,
            environment_observation_bytes=(
                built["environment"]
                if environment_bytes is None
                else environment_bytes
            ),
            bootstrap_artifact=typed["bootstrap_anchor"],
            recovery_artifact=typed["recovery_root"],
            lifecycle_artifact=typed["trust_lifecycle_root"],
            release_artifact=typed["release"],
            active_pointer_artifact=typed["active_pointer"],
            release_history_artifact=typed["release_history"],
            pointer_history_artifact=next(
                raw
                for coordinate, raw in members.items()
                if "/pointer_history/" in coordinate
            ),
            historical_release_artifacts=(
                () if built is first else (first["typed"]["release"],)
            ),
            generation_manifest_bytes=generation,
            generation_member_bytes=members,
            design_document_bytes=(
                ROOT / "docs/design/semantic_ingestion_architecture.md"
            ).read_bytes(),
            now=built["now"],
        )

    with TemporaryDirectory() as directory:
        publication = FileTraceabilityReleasePublicationStore(
            Path(directory) / "publication.json"
        )
        publication.provision(1, 1, first["release_digest"])
        authority = AcceptanceTrustStore(
            material=first["material"],
            watermark_store=publication,
            expected_release_roots=first["expected_release_roots"],
            publication_store=publication,
            allow_test_file_fence=True,
            independent_generation_verifier=first["independent_generation_verifier"],
        )
        publish(first, first_generation, first_members, authority)
        successor_authority = AcceptanceTrustStore(
            material=second["material"],
            watermark_store=publication,
            expected_release_roots=second["expected_release_roots"],
            publication_store=publication,
            allow_test_file_fence=True,
            independent_generation_verifier=second["independent_generation_verifier"],
        )
        publish(second, second_generation, second_members, successor_authority)
        inventory = publication.version_inventory()
        assert inventory.current is not None
        assert inventory.current.sequence == 2
        assert inventory.corrected_v2_tail_count == 2
        publication_path = Path(directory) / "publication.json"
        published = publication_path.read_bytes()
        verifier = second["independent_generation_verifier"]
        assert isinstance(verifier, ExplicitTestIndependentGenerationVerifier)
        good_result = verifier.result
        bad_spool_result = replace(
            good_result,
            structural_spool_bytes=good_result.structural_spool_bytes + b"x",
        )
        bad_spool_authority = replace(
            successor_authority,
            independent_generation_verifier=ExplicitTestIndependentGenerationVerifier(
                bad_spool_result
            ),
        )
        mutations = (
            {"report_bytes": second["report_bytes"] + b" "},
            {"environment_bytes": second["environment"] + b" "},
            {
                "artifacts": {
                    **second["artifacts"],
                    next(iter(second["artifacts"])): b"mutated",
                }
            },
        )
        for mutation in mutations:
            with pytest.raises(ExecutionEvidenceError):
                publish(
                    second,
                    second_generation,
                    second_members,
                    successor_authority,
                    **mutation,
                )
            assert publication_path.read_bytes() == published
        with pytest.raises(ExecutionEvidenceError, match="structural_derivation_unavailable"):
            publish(second, second_generation, second_members, bad_spool_authority)
        assert publication_path.read_bytes() == published


def test_pointer_history_rejects_malformed_truncated_reordered_and_unsigned_entries() -> None:
    profile, key = "test-profile", "test-key"
    start = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    end = None
    signer = {
        "source_kind": "prior_verified_lifecycle_root",
        "signature_purpose": "semantic_ingestion_traceability_active_release_pointer",
        "issuer_id": "issuer-1",
        "signature_profile_id": profile,
        "key_or_certificate_digest": key,
        "eligible_not_before": start.isoformat(),
        "eligible_not_after": None,
        "trust_lifecycle_root_digest": "5" * 64,
        "lifecycle_record_digest": "6" * 64,
    }

    def sign(payload: bytes) -> bytes:
        return sha256(profile.encode() + b"\0" + key.encode() + b"\0" + payload).digest()

    def verify(p: str, k: str, payload: bytes, signature: bytes) -> bool:
        return (p, k) == (profile, key) and signature == sign(payload)

    def seal_pointer(body: dict[str, object]) -> dict[str, object]:
        digest = sha256(
            b"memorii:sia-traceability-active-release-pointer:v1\0"
            + encode_typed_value(body)
        ).hexdigest()
        return {
            **body,
            "active_pointer_digest": digest,
            "signature": sign(
                encode_typed_value(
                    {
                        "issuance_purpose": "semantic_ingestion_traceability_active_release_pointer",
                        "body_binding": body["canonical_profile_binding"],
                        "active_pointer_digest": digest,
                        "signer_coordinate": body["signer_coordinate"],
                    }
                )
            ).hex(),
        }

    pointer = seal_pointer(
        {
            "pointer_id": "pointer-1",
            "issuance_purpose": "semantic_ingestion_traceability_active_release_pointer",
            "target_authority_id": "authority-1",
            "canonical_profile_binding": {},
            "generation_id": "generation-1",
            "generation_manifest_digest": "1" * 64,
            "release_id": "release-1",
            "release_digest": "2" * 64,
            "release_epoch": 1,
            "release_sequence": 1,
            "release_history_digest": "3" * 64,
            "predecessor_pointer_history_digest": None,
            "predecessor_active_pointer_digest": None,
            "pointer_sequence": 1,
            "published_at": "2026-01-01T00:00:01+00:00",
            "signer_coordinate": signer,
        }
    )
    history = {
        "history_id": "history-1",
        "issuance_purpose": "semantic_ingestion_traceability_pointer_history",
        "canonical_profile_binding": {},
        "pointers": [pointer],
        "signer_coordinate": {**signer, "signature_purpose": "semantic_ingestion_traceability_pointer_history"},
    }
    active_signers = (
        (
            str(signer["issuer_id"]),
            "7" * 64,
            str(signer["signature_profile_id"]),
            str(signer["key_or_certificate_digest"]),
            start,
            end,
        ),
    )
    lifecycle_artifact = serialize_artifact(
        {
            "lifecycle_root_digest": "5" * 64,
            "records": [{"record_digest": "6" * 64, "target_digest": "7" * 64}],
        },
        CanonicalTypedValueProfileBinding(
            "semantic_ingestion_typed_value", 1, "8" * 64, "test", 1, "9" * 64
        ),
    )

    def reseal(candidate: dict[str, object]) -> dict[str, object]:
        body = {
            key: value
            for key, value in candidate.items()
            if key not in {"pointer_history_digest", "signature"}
        }
        digest = sha256(
            b"memorii:sia-traceability-pointer-history:v1\0"
            + encode_typed_value(body)
        ).hexdigest()
        coordinate = candidate["signer_coordinate"]
        assert isinstance(coordinate, dict)
        signature = sign(
            encode_typed_value(
                {
                    "issuance_purpose": "semantic_ingestion_traceability_pointer_history",
                    "body_binding": candidate["canonical_profile_binding"],
                    "pointer_history_digest": digest,
                    "signer_coordinate": coordinate,
                }
            ),
        ).hex()
        return {
            **body,
            "pointer_history_digest": digest,
            "signature": signature,
        }

    history = reseal(history)
    active = seal_pointer(
        {
            **{
                key: value
                for key, value in pointer.items()
                if key not in {"active_pointer_digest", "signature"}
            },
            "pointer_id": "pointer-2",
            "pointer_sequence": 2,
            "release_id": "release-2",
            "release_digest": "4" * 64,
            "release_sequence": 2,
            "predecessor_pointer_history_digest": history["pointer_history_digest"],
            "predecessor_active_pointer_digest": pointer["active_pointer_digest"],
        }
    )
    pointers = history["pointers"]
    assert isinstance(pointers, list)
    malformed = deepcopy(history)
    malformed_pointers = malformed["pointers"]
    assert isinstance(malformed_pointers, list) and isinstance(malformed_pointers[0], dict)
    del malformed_pointers[0]["release_digest"]
    truncated = {**history, "pointers": []}
    reordered = {**history, "pointers": [deepcopy(pointers[0]), deepcopy(pointers[0])]}
    unsigned = deepcopy(history)
    unsigned_pointers = unsigned["pointers"]
    assert isinstance(unsigned_pointers, list) and isinstance(unsigned_pointers[0], dict)
    unsigned_pointers[0]["signature"] = ""
    for candidate in (malformed, truncated, reordered, unsigned):
        with pytest.raises(ExecutionEvidenceError):
            _verify_m0_pointer_history(
                bodies=[reseal(candidate)],
                active_pointer=active,
                lifecycle_artifact=lifecycle_artifact,
                active_signers=active_signers,
                verify_signature=verify,
                now=datetime.fromisoformat("2026-01-01T00:00:02+00:00"),
            )


def test_foreign_trust_rejects_without_advancing_watermark() -> None:
    built = _inputs()
    typed = built["typed"]
    assert isinstance(typed, dict)
    with TemporaryDirectory() as directory:
        watermark_path = Path(directory) / "watermark.json"
        store = FileTraceabilityReleaseWatermarkStore(watermark_path)
        assert store.provision(1, 1, built["release_digest"]).__class__.__name__ == "WatermarkAdvanced"
        foreign = AcceptanceTrustStore(
            material=VerifierHeldTrustMaterial(typed["bootstrap_anchor"], (), verifier, typed["recovery_policy"]),
            watermark_store=store, expected_release_roots=built["expected_release_roots"],
            publication_store=FileTraceabilityReleasePublicationStore(
                Path(directory) / "foreign-publication.json"
            ),
        )
        before = watermark_path.read_bytes()
        try:
            RegisteredApprovalExecutor(foreign).execute(
                registry_bytes=(ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json").read_bytes(), group_id=built["group_id"], report_bytes=built["report_bytes"], artifacts=built["artifacts"], implementation_revision="scenario-c2", implementation_tree_digest="a" * 64, environment_observation_bytes=built["environment"], bootstrap_artifact=typed["bootstrap_anchor"], recovery_artifact=typed["recovery_root"], lifecycle_artifact=typed["trust_lifecycle_root"], release_artifact=typed["release"], active_pointer_artifact=typed["active_pointer"], release_history_artifact=typed["release_history"], now=built["now"],
            )
        except ExecutionEvidenceError as exc:
            assert "trust_not_independently_provisioned" in str(exc)
        else:
            raise AssertionError("foreign trust accepted")
        assert watermark_path.read_bytes() == before
        assert not (Path(directory) / "foreign-publication.json").exists()


def test_default_resolver_rejects_exact_scenario_bytes_without_watermark_change() -> None:
    built = _inputs()
    typed = built["typed"]
    assert isinstance(typed, dict)
    with TemporaryDirectory() as directory:
        watermark_path = Path(directory) / "watermark.json"
        store = FileTraceabilityReleaseWatermarkStore(watermark_path)
        assert store.provision(1, 1, built["release_digest"]).__class__.__name__ == "WatermarkAdvanced"
        before = watermark_path.read_bytes()
        with pytest.raises(ExecutionEvidenceError, match="registered trust authority is unavailable"):
            RegisteredApprovalExecutor.from_resolver(DefaultAcceptanceTrustResolver()).execute(
                registry_bytes=(ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json").read_bytes(), group_id=built["group_id"], report_bytes=built["report_bytes"], artifacts=built["artifacts"], implementation_revision="scenario-c2", implementation_tree_digest="a" * 64, environment_observation_bytes=built["environment"], bootstrap_artifact=typed["bootstrap_anchor"], recovery_artifact=typed["recovery_root"], lifecycle_artifact=typed["trust_lifecycle_root"], release_artifact=typed["release"], active_pointer_artifact=typed["active_pointer"], release_history_artifact=typed["release_history"], now=built["now"],
            )
        assert watermark_path.read_bytes() == before

"""Shared exact current-CTV release-chain fixtures."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
    decode_artifact,
    decode_typed_value,
    encode_typed_value,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_traceability_registry import load_registry
from memorii.tools.semantic_ingestion_traceability_release import (
    VerifierHeldTrustMaterial,
    _binding_for,
    _required_roots,
    _root_coordinate,
    _typed_digest,
)

AUTHORITY = "authority-a"
ROOT_DIGEST = "a" * 64
RECORD_DIGEST = "b" * 64
PROFILE = ("semantic_ingestion_typed_value", 2, "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f")
BINDINGS = {
    "bootstrap": ("TraceabilityBootstrapTrustAnchorBody.v1", "b3afc00594f4ba871e64a1a1d649a1d32e1b7bb77e7eb2ff14d550e897f19c77"),
    "recovery": ("TraceabilityRecoveryTrustRootBody.v1", "b8e2679794f444955932cd204dee8312e6c0077346c9f5570e1c28770c09abf3"),
    "recovery_policy": ("TraceabilityRecoveryTrustPolicyBody.v1", "4cf90609b1ab78610816b1316082f40f749052f33fe3ad5a2b85b65820cffd75"),
    "lifecycle": ("TraceabilityTrustLifecycleRootBody.v1", "82cee87c03a941f2dc58489f9f358d18eb505bf956a72bc23b9f4f2abd0d214e"),
    "release": ("SemanticIngestionTraceabilityReleaseBody.v1", "2e1ba193b6fac94c03598d7c27489f5fa69e48c5a052072124acb398adfd8ce2"),
    "active_pointer": ("TraceabilityActiveReleasePointerBody.v1", "fd5f73aadb565cdaf53afa7aa3acb2218af5e0cac5f0dfaff7032aaa9a982d7d"),
    "release_history": ("TraceabilityReleaseHistoryBody.v1", "398f87e800eba421e3e657af5c6b34e1887c5c93e7038c981d6e6ce3d38d87e3"),
}


def _binding(kind: str) -> CanonicalTypedValueProfileBinding:
    schema, digest = BINDINGS[kind]
    return CanonicalTypedValueProfileBinding(*PROFILE, schema, 1, digest)


def _artifact(kind: str, body: dict[str, object]) -> bytes:
    return serialize_artifact(body, _binding(kind))


def _bootstrap() -> dict[str, object]:
    return {
        "anchor_id": "bootstrap-a",
        "target_authority_id": AUTHORITY,
        "issuance_purpose": "semantic_ingestion_traceability_release_root",
        "target_purpose": "semantic_ingestion_traceability_release",
        "authorized_signature_purposes": [
            "semantic_ingestion_traceability_lifecycle_record",
            "semantic_ingestion_traceability_lifecycle_root",
            "semantic_ingestion_traceability_recovery_policy",
            "semantic_ingestion_traceability_release",
            "semantic_ingestion_traceability_active_release_pointer",
            "semantic_ingestion_traceability_release_history",
        ],
        "canonical_profile_binding": _binding_for("bootstrap"),
        "signature_profile_id": "profile-a",
        "public_key_or_root_certificate_digest": "a" * 64,
        "provisioned_channel_id": "channel-a",
        "rotation_sequence": 1,
        "predecessor_anchor_id": None,
        "predecessor_anchor_digest": None,
        "effective_at": "2026-01-01T00:00:00Z",
        "recorded_at": "2026-01-01T00:00:00Z",
        "expires_at": None,
        "provenance": {
            "source_kind": "independently_provisioned_genesis",
            "authority_id": AUTHORITY,
            "provisioned_channel_id": "channel-a",
            "provisioned_authorization_artifact_digest": "c" * 64,
            "provisioned_signature_purpose": "semantic_ingestion_traceability_release_root",
            "provisioned_signature_profile_id": "profile-a",
            "provisioned_key_or_certificate_digest": "a" * 64,
            "eligible_not_before": "2026-01-01T00:00:00Z",
            "eligible_not_after": None,
        },
    }


def _lifecycle() -> dict[str, object]:
    return {
        "authority_id": AUTHORITY,
        "lifecycle_root_digest": ROOT_DIGEST,
        "records": [
            {
                "record_digest": RECORD_DIGEST,
                "sequence": 1,
                "target_id": "bootstrap-old",
                "target_digest": "d" * 64,
            }
        ],
    }


def _policy() -> dict[str, object]:
    bootstrap = _bootstrap()
    return {
        "sequence": 1,
        "predecessor_policy_digest": None,
        "signer_provenance": {
            "source_kind": "independently_provisioned_bootstrap_anchor",
            "signature_purpose": "semantic_ingestion_traceability_recovery_policy",
            "authority_id": AUTHORITY,
            "provisioned_channel_id": "channel-a",
            "bootstrap_anchor_digest": _root_coordinate(bootstrap)[2],
            "issuer_id": "bootstrap-a",
            "key_or_certificate_digest": "a" * 64,
            "signature_profile_id": "profile-a",
            "eligible_not_before": "2026-01-01T00:00:00Z",
            "eligible_not_after": None,
        },
    }


def _current_chain(
    external_roots: dict[str, str] | None = None,
    golden_vector_manifest_digest: str = "d" * 64,
    *,
    threshold_recovery: bool = False,
    activate_recovery_roots: bool = True,
    terminal_recovery_action: str | None = None,
    bootstrap_expires_at: str | None = None,
    release_issued_at: str | None = None,
) -> dict[str, object]:
    """Build the complete current CTV chain without any flat compatibility preimages."""
    now = datetime(2026, 1, 2, tzinfo=UTC)
    key_a, key_b, key_r = "a" * 64, "b" * 64, "c" * 64
    key_c, key_r2 = "4" * 64, "5" * 64

    def signature(profile: str, key: str, payload: bytes) -> bytes:
        return sha256(profile.encode() + b"\0" + key.encode() + b"\0" + payload).digest()

    def signed(profile: str, key: str, payload: bytes) -> str:
        return signature(profile, key, payload).hex()

    def artifact(kind: str, body: dict[str, object]) -> bytes:
        return serialize_artifact(body, _binding(kind))

    def record(
        sequence: int, *, predecessor: str | None, target_id: str, target_digest: str,
        action: str, replacement_id: str | None, replacement_digest: str | None,
        signer_id: str, signer_key: str, recorded_at: str,
        eligibility_reference: dict[str, object],
        signer_profile: str = "profile-a",
        target_kind: str = "bootstrap_anchor",
    ) -> dict[str, object]:
        binding = {
            "signature_purpose": "semantic_ingestion_traceability_lifecycle_record",
            "signer_id": signer_id,
            "signer_key_or_certificate_digest": signer_key,
            "signature_profile_id": signer_profile,
            "eligibility_reference": eligibility_reference,
            "recovery_root_digest": None,
        }
        body: dict[str, object] = {
            "record_id": f"record-{sequence}",
            "issuance_purpose": "semantic_ingestion_traceability_lifecycle_record",
            "target_kind": target_kind, "target_id": target_id,
            "target_digest": target_digest, "action": action,
            "replacement_target_id": replacement_id,
            "replacement_target_digest": replacement_digest,
            "canonical_profile_binding": _binding_for("lifecycle_record"),
            "effective_at": recorded_at, "recorded_at": recorded_at,
            "sequence": sequence, "predecessor_record_digest": predecessor,
            "recovery_policy_digest": None, "signer_bindings": [binding],
        }
        digest = _typed_digest(b"memorii:sia-traceability-trust-lifecycle-record:v1", body)
        payload = encode_typed_value({
            "issuance_purpose": body["issuance_purpose"],
            "body_binding": body["canonical_profile_binding"],
            "record_digest": digest, "signer_binding": binding,
        })
        return {**body, "record_digest": digest, "signatures": [signature(signer_profile, signer_key, payload)]}

    bootstrap = _bootstrap()
    bootstrap["public_key_or_root_certificate_digest"] = key_a
    bootstrap["expires_at"] = bootstrap_expires_at
    bootstrap["provenance"] = {
        **bootstrap["provenance"],  # type: ignore[arg-type]
        "provisioned_key_or_certificate_digest": key_a,
    }
    bootstrap_digest = _root_coordinate(bootstrap)[2]
    recovery = {
        "recovery_root_id": "recovery-a",
        "issuance_purpose": "semantic_ingestion_traceability_recovery_root",
        "target_authority_id": AUTHORITY,
        "authorized_signature_purposes": ["semantic_ingestion_traceability_recovery_policy"],
        "canonical_profile_binding": _binding_for("recovery"),
        "signature_profile_id": "profile-r", "public_key_or_root_certificate_digest": key_r,
        "provisioned_channel_id": "recovery-channel", "rotation_sequence": 1,
        "predecessor_recovery_root_id": None, "predecessor_recovery_root_digest": None,
        "effective_at": "2026-01-01T00:00:00Z", "recorded_at": "2026-01-01T00:00:00Z",
        "expires_at": None,
        "provenance": {
            "source_kind": "independently_provisioned_genesis", "authority_id": AUTHORITY,
            "provisioned_channel_id": "recovery-channel",
            "provisioned_authorization_artifact_digest": "d" * 64,
            "provisioned_signature_purpose": "semantic_ingestion_traceability_recovery_root",
            "provisioned_signature_profile_id": "profile-r",
            "provisioned_key_or_certificate_digest": key_r,
            "eligible_not_before": "2026-01-01T00:00:00Z", "eligible_not_after": None,
        },
    }
    recovery_digest = _root_coordinate(recovery)[2]
    first = record(1, predecessor=None, target_id="bootstrap-a", target_digest=bootstrap_digest,
                   action="activate", replacement_id=None, replacement_digest=None,
                   signer_id="bootstrap-a", signer_key=key_a, recorded_at="2026-01-01T00:00:01Z",
                   eligibility_reference={
                       "source_kind": "independently_provisioned_genesis", "authority_id": AUTHORITY,
                       "eligibility_purpose": "semantic_ingestion_traceability_lifecycle_record",
                       "source_artifact_digest": bootstrap_digest, "prior_lifecycle_root_digest": None,
                       "prior_lifecycle_record_digest": None, "prior_lifecycle_sequence": 0,
                       "target_id": "bootstrap-a", "target_digest": bootstrap_digest,
                       "eligible_not_before": "2026-01-01T00:00:00Z", "eligible_not_after": bootstrap_expires_at,
                       "provisioned_channel_id": "channel-a",
                   })
    genesis_coordinate = {
        "source_kind": "independently_provisioned_bootstrap_anchor", "authority_id": AUTHORITY,
        "provisioned_channel_id": "channel-a", "bootstrap_anchor_id": "bootstrap-a",
        "bootstrap_anchor_digest": bootstrap_digest, "issuer_id": "bootstrap-a",
        "key_or_certificate_digest": key_a, "signature_profile_id": "profile-a",
        "signature_purpose": "semantic_ingestion_traceability_lifecycle_root",
        "eligible_not_before": "2026-01-01T00:00:00Z", "eligible_not_after": bootstrap_expires_at,
    }
    root_body = {"authority_id": AUTHORITY, "issuance_purpose": "semantic_ingestion_traceability_lifecycle_root",
                 "canonical_profile_binding": _binding_for("lifecycle"), "bootstrap_anchor_history_digest": "e" * 64,
                 "recovery_root_history_digest": "f" * 64, "recovery_policy_history_digest": "0" * 64,
                 "records": [first]}
    genesis_digest = _typed_digest(b"memorii:sia-traceability-trust-lifecycle-root:v1", root_body)
    genesis = {**root_body, "signer_coordinates": [genesis_coordinate],
               "signatures": [signature("profile-a", key_a, encode_typed_value({"issuance_purpose": root_body["issuance_purpose"], "body_binding": root_body["canonical_profile_binding"], "lifecycle_root_digest": genesis_digest, "signer_coordinate": genesis_coordinate}))],
               "lifecycle_root_digest": genesis_digest}
    successor = dict(bootstrap)
    successor.update({"anchor_id": "bootstrap-b", "public_key_or_root_certificate_digest": key_b,
                      "rotation_sequence": 2, "predecessor_anchor_id": "bootstrap-a",
                      "predecessor_anchor_digest": bootstrap_digest,
                      "provenance": {"source_kind": "prior_verified_lifecycle_root", "authority_id": AUTHORITY,
                                     "trust_lifecycle_root_digest": genesis_digest, "lifecycle_record_digest": first["record_digest"],
                                     "eligible_not_before": "2026-01-01T00:00:02Z", "eligible_not_after": None},
                      "effective_at": "2026-01-01T00:00:02Z", "recorded_at": "2026-01-01T00:00:02Z"})
    successor_digest = _root_coordinate(successor)[2]
    second = record(2, predecessor=str(first["record_digest"]), target_id="bootstrap-a", target_digest=bootstrap_digest,
                    action="rotate", replacement_id="bootstrap-b", replacement_digest=successor_digest,
                    signer_id="bootstrap-a", signer_key=key_a, recorded_at="2026-01-01T00:00:02Z",
                    eligibility_reference={
                        "source_kind": "prior_verified_lifecycle_root", "authority_id": AUTHORITY,
                        "eligibility_purpose": "semantic_ingestion_traceability_lifecycle_record",
                        "source_artifact_digest": genesis_digest,
                        "prior_lifecycle_root_digest": genesis_digest,
                        "prior_lifecycle_record_digest": first["record_digest"],
                        "prior_lifecycle_sequence": 1, "target_id": "bootstrap-a",
                        "target_digest": bootstrap_digest,
                        "eligible_not_before": "2026-01-01T00:00:00Z", "eligible_not_after": bootstrap_expires_at,
                        "provisioned_channel_id": "channel-a",
                    })
    successor_coordinate = {"source_kind": "prior_verified_lifecycle_root", "signature_purpose": "semantic_ingestion_traceability_lifecycle_root",
                             "issuer_id": "bootstrap-a", "key_or_certificate_digest": key_a, "signature_profile_id": "profile-a",
                             "trust_lifecycle_root_digest": genesis_digest, "lifecycle_record_digest": first["record_digest"],
                             "eligible_not_before": "2026-01-01T00:00:00Z", "eligible_not_after": bootstrap_expires_at}
    successor_body = {**root_body, "records": [first, second]}
    lifecycle_digest = _typed_digest(b"memorii:sia-traceability-trust-lifecycle-root:v1", successor_body)
    lifecycle = {**successor_body, "signer_coordinates": [successor_coordinate],
                 "signatures": [signature("profile-a", key_a, encode_typed_value({"issuance_purpose": successor_body["issuance_purpose"], "body_binding": successor_body["canonical_profile_binding"], "lifecycle_root_digest": lifecycle_digest, "signer_coordinate": successor_coordinate}))],
                 "lifecycle_root_digest": lifecycle_digest}
    recoveries = [recovery]
    successor_documents = [successor]
    prior_lifecycle_documents = [genesis]
    active_anchor_id, active_anchor_digest = "bootstrap-b", successor_digest
    release_signer_id, release_signer_key, release_signer_profile = (
        "bootstrap-a", key_a, "profile-a"
    )
    terminal_record = second
    if threshold_recovery:
        recovery_two = {
            **recovery,
            "recovery_root_id": "recovery-b",
            "signature_profile_id": "profile-r2",
            "public_key_or_root_certificate_digest": key_r2,
            "provisioned_channel_id": "recovery-channel-2",
            "provenance": {
                **recovery["provenance"],  # type: ignore[arg-type]
                "provisioned_channel_id": "recovery-channel-2",
                "provisioned_authorization_artifact_digest": "6" * 64,
                "provisioned_signature_profile_id": "profile-r2",
                "provisioned_key_or_certificate_digest": key_r2,
            },
        }
        recovery_two_digest = _root_coordinate(recovery_two)[2]
        recoveries.append(recovery_two)

        def recovery_binding(
            recovery_root: dict[str, object], recovery_root_digest: str
        ) -> dict[str, object]:
            _, root_id, _, profile, key = _root_coordinate(recovery_root)
            return {
                "signature_purpose": "semantic_ingestion_traceability_lifecycle_record",
                "signer_id": root_id,
                "signer_key_or_certificate_digest": key,
                "signature_profile_id": profile,
                "eligibility_reference": {
                    "source_kind": "prior_verified_lifecycle_root",
                    "authority_id": AUTHORITY,
                    "eligibility_purpose": "semantic_ingestion_traceability_lifecycle_record",
                    "source_artifact_digest": genesis_digest,
                    "prior_lifecycle_root_digest": genesis_digest,
                    "prior_lifecycle_record_digest": first["record_digest"],
                    "prior_lifecycle_sequence": 1,
                    "target_id": "bootstrap-a",
                    "target_digest": bootstrap_digest,
                    "eligible_not_before": "2026-01-01T00:00:00Z",
                    "eligible_not_after": None,
                    "provisioned_channel_id": recovery_root["provisioned_channel_id"],
                },
                "recovery_root_digest": recovery_root_digest,
            }

        recovery_bindings = [
            recovery_binding(recovery, recovery_digest),
            recovery_binding(recovery_two, recovery_two_digest),
        ]

        def signed_successor_root(
            records: list[dict[str, object]],
            previous_root: dict[str, object],
            *,
            signer_id: str,
            signer_profile: str,
            signer_key: str,
        ) -> dict[str, object]:
            previous_records = previous_root["records"]
            assert isinstance(previous_records, list)
            previous_terminal = previous_records[-1]
            assert isinstance(previous_terminal, dict)
            coordinate = {
                **successor_coordinate,
                "issuer_id": signer_id,
                "key_or_certificate_digest": signer_key,
                "signature_profile_id": signer_profile,
                "trust_lifecycle_root_digest": previous_root[
                    "lifecycle_root_digest"
                ],
                "lifecycle_record_digest": previous_terminal["record_digest"],
            }
            body = {**root_body, "records": records}
            digest = _typed_digest(
                b"memorii:sia-traceability-trust-lifecycle-root:v1", body
            )
            return {
                **body,
                "signer_coordinates": [coordinate],
                "signatures": [
                    signature(
                        signer_profile,
                        signer_key,
                        encode_typed_value(
                            {
                                "issuance_purpose": body["issuance_purpose"],
                                "body_binding": body["canonical_profile_binding"],
                                "lifecycle_root_digest": digest,
                                "signer_coordinate": coordinate,
                            }
                        ),
                    )
                ],
                "lifecycle_root_digest": digest,
            }

        pre_recovery_records: list[dict[str, object]] = [first]
        reference_chain: list[dict[str, object]] = [genesis]
        if activate_recovery_roots:
            activation_one = record(
                2,
                predecessor=str(first["record_digest"]),
                target_id="recovery-a",
                target_digest=recovery_digest,
                target_kind="recovery_root",
                action="activate",
                replacement_id=None,
                replacement_digest=None,
                signer_id="bootstrap-a",
                signer_key=key_a,
                recorded_at="2026-01-01T00:00:02Z",
                eligibility_reference={
                    "source_kind": "prior_verified_lifecycle_root",
                    "authority_id": AUTHORITY,
                    "eligibility_purpose": "semantic_ingestion_traceability_lifecycle_record",
                    "source_artifact_digest": genesis_digest,
                    "prior_lifecycle_root_digest": genesis_digest,
                    "prior_lifecycle_record_digest": first["record_digest"],
                    "prior_lifecycle_sequence": 1,
                    "target_id": "recovery-a",
                    "target_digest": recovery_digest,
                    "eligible_not_before": "2026-01-01T00:00:00Z",
                    "eligible_not_after": None,
                    "provisioned_channel_id": "channel-a",
                },
            )
            reference_chain.append(
                signed_successor_root(
                    [first, activation_one],
                    reference_chain[-1],
                    signer_id="bootstrap-a",
                    signer_profile="profile-a",
                    signer_key=key_a,
                )
            )
            activation_one_root_digest = reference_chain[-1][
                "lifecycle_root_digest"
            ]
            assert isinstance(activation_one_root_digest, str)
            activation_two = record(
                3,
                predecessor=str(activation_one["record_digest"]),
                target_id="recovery-b",
                target_digest=recovery_two_digest,
                target_kind="recovery_root",
                action="activate",
                replacement_id=None,
                replacement_digest=None,
                signer_id="bootstrap-a",
                signer_key=key_a,
                recorded_at="2026-01-01T00:00:03Z",
                eligibility_reference={
                    "source_kind": "prior_verified_lifecycle_root",
                    "authority_id": AUTHORITY,
                    "eligibility_purpose": "semantic_ingestion_traceability_lifecycle_record",
                    "source_artifact_digest": activation_one_root_digest,
                    "prior_lifecycle_root_digest": activation_one_root_digest,
                    "prior_lifecycle_record_digest": activation_one[
                        "record_digest"
                    ],
                    "prior_lifecycle_sequence": 2,
                    "target_id": "recovery-b",
                    "target_digest": recovery_two_digest,
                    "eligible_not_before": "2026-01-01T00:00:00Z",
                    "eligible_not_after": None,
                    "provisioned_channel_id": "channel-a",
                },
            )
            pre_recovery_records.extend((activation_one, activation_two))
            reference_chain.append(
                signed_successor_root(
                    pre_recovery_records,
                    reference_chain[-1],
                    signer_id="bootstrap-a",
                    signer_profile="profile-a",
                    signer_key=key_a,
                )
            )
            if terminal_recovery_action is not None:
                activation_two_root_digest = reference_chain[-1][
                    "lifecycle_root_digest"
                ]
                assert isinstance(activation_two_root_digest, str)
                terminal_record_for_recovery = record(
                    4,
                    predecessor=str(activation_two["record_digest"]),
                    target_id="recovery-a",
                    target_digest=recovery_digest,
                    target_kind="recovery_root",
                    action=terminal_recovery_action,
                    replacement_id=None,
                    replacement_digest=None,
                    signer_id="bootstrap-a",
                    signer_key=key_a,
                    recorded_at="2026-01-01T00:00:04Z",
                    eligibility_reference={
                        "source_kind": "prior_verified_lifecycle_root",
                        "authority_id": AUTHORITY,
                        "eligibility_purpose": "semantic_ingestion_traceability_lifecycle_record",
                        "source_artifact_digest": activation_two_root_digest,
                        "prior_lifecycle_root_digest": activation_two_root_digest,
                        "prior_lifecycle_record_digest": activation_two[
                            "record_digest"
                        ],
                        "prior_lifecycle_sequence": 3,
                        "target_id": "recovery-a",
                        "target_digest": recovery_digest,
                        "eligible_not_before": "2026-01-01T00:00:00Z",
                        "eligible_not_after": None,
                        "provisioned_channel_id": "channel-a",
                    },
                )
                pre_recovery_records.append(terminal_record_for_recovery)
                reference_chain.append(
                    signed_successor_root(
                        pre_recovery_records,
                        reference_chain[-1],
                        signer_id="bootstrap-a",
                        signer_profile="profile-a",
                        signer_key=key_a,
                    )
                )
        recovery_prior = reference_chain[-1]
        recovery_prior_records = recovery_prior["records"]
        assert isinstance(recovery_prior_records, list)
        recovery_prior_terminal = recovery_prior_records[-1]
        assert isinstance(recovery_prior_terminal, dict)
        recovery_prior_digest = recovery_prior["lifecycle_root_digest"]
        assert isinstance(recovery_prior_digest, str)
        for binding in recovery_bindings:
            reference = binding["eligibility_reference"]
            assert isinstance(reference, dict)
            reference.update(
                {
                    "source_artifact_digest": recovery_prior_digest,
                    "prior_lifecycle_root_digest": recovery_prior_digest,
                    "prior_lifecycle_record_digest": recovery_prior_terminal[
                        "record_digest"
                    ],
                    "prior_lifecycle_sequence": len(recovery_prior_records),
                }
            )
        recover_sequence = len(pre_recovery_records) + 1
        recover_time = f"2026-01-01T00:00:0{recover_sequence}Z"
        recovered_body = dict(successor)
        recovered_body.update(
            {
                "anchor_id": "bootstrap-b",
                "public_key_or_root_certificate_digest": key_b,
                "rotation_sequence": 2,
                "predecessor_anchor_id": "bootstrap-a",
                "predecessor_anchor_digest": bootstrap_digest,
                "effective_at": recover_time,
                "recorded_at": recover_time,
            }
        )
        recovered = recovered_body
        recovered_digest = _root_coordinate(recovered)[2]
        recover_body = {
            "record_id": f"record-{recover_sequence}",
            "issuance_purpose": "semantic_ingestion_traceability_lifecycle_record",
            "target_kind": "bootstrap_anchor",
            "target_id": "bootstrap-a",
            "target_digest": bootstrap_digest,
            "action": "recover",
            "replacement_target_id": "bootstrap-b",
            "replacement_target_digest": recovered_digest,
            "canonical_profile_binding": _binding_for("lifecycle_record"),
            "effective_at": recover_time,
            "recorded_at": recover_time,
            "sequence": recover_sequence,
            "predecessor_record_digest": pre_recovery_records[-1]["record_digest"],
            "recovery_policy_digest": None,
            "signer_bindings": recovery_bindings,
        }
        recover_digest = _typed_digest(
            b"memorii:sia-traceability-trust-lifecycle-record:v1", recover_body
        )
        recover_record = {
            **recover_body,
            "record_digest": recover_digest,
            "signatures": [
                signature(
                    str(binding["signature_profile_id"]),
                    str(binding["signer_key_or_certificate_digest"]),
                    encode_typed_value(
                        {
                            "issuance_purpose": recover_body["issuance_purpose"],
                            "body_binding": recover_body["canonical_profile_binding"],
                            "record_digest": recover_digest,
                            "signer_binding": binding,
                        }
                    ),
                )
                for binding in recovery_bindings
            ],
        }

        prior_chain = [genesis]
        appended_records = [*pre_recovery_records[1:], recover_record]
        accumulated_records = [first]
        for appended_record in appended_records:
            accumulated_records = [*accumulated_records, appended_record]
            prior_chain.append(
                signed_successor_root(
                    accumulated_records,
                    prior_chain[-1],
                    signer_id="bootstrap-a",
                    signer_profile="profile-a",
                    signer_key=key_a,
                )
            )
        recovered_lifecycle = prior_chain[-1]
        recovered_lifecycle_digest = recovered_lifecycle[
            "lifecycle_root_digest"
        ]
        assert isinstance(recovered_lifecycle_digest, str)
        final_anchor = {
            **recovered,
            "anchor_id": "bootstrap-c",
            "public_key_or_root_certificate_digest": key_c,
            "rotation_sequence": 3,
            "predecessor_anchor_id": "bootstrap-b",
            "predecessor_anchor_digest": recovered_digest,
            "effective_at": f"2026-01-01T00:00:0{recover_sequence + 1}Z",
            "recorded_at": f"2026-01-01T00:00:0{recover_sequence + 1}Z",
            "provenance": {
                "source_kind": "prior_verified_lifecycle_root",
                "authority_id": AUTHORITY,
                "trust_lifecycle_root_digest": recovered_lifecycle_digest,
                "lifecycle_record_digest": recover_digest,
                "eligible_not_before": recover_time,
                "eligible_not_after": None,
            },
        }
        final_digest = _root_coordinate(final_anchor)[2]
        third = record(
            recover_sequence + 1,
            predecessor=recover_digest,
            target_id="bootstrap-b",
            target_digest=recovered_digest,
            action="rotate",
            replacement_id="bootstrap-c",
            replacement_digest=final_digest,
            signer_id="recovery-a",
            signer_key=key_r,
            signer_profile="profile-r",
            recorded_at=f"2026-01-01T00:00:0{recover_sequence + 1}Z",
            eligibility_reference={
                "source_kind": "prior_verified_lifecycle_root",
                "authority_id": AUTHORITY,
                "eligibility_purpose": "semantic_ingestion_traceability_lifecycle_record",
                "source_artifact_digest": recovered_lifecycle_digest,
                "prior_lifecycle_root_digest": recovered_lifecycle_digest,
                "prior_lifecycle_record_digest": recover_digest,
                "prior_lifecycle_sequence": recover_sequence,
                "target_id": "bootstrap-b",
                "target_digest": recovered_digest,
                "eligible_not_before": "2026-01-01T00:00:00Z",
                "eligible_not_after": None,
                "provisioned_channel_id": "recovery-channel",
            },
        )
        lifecycle = signed_successor_root(
            [*pre_recovery_records, recover_record, third],
            recovered_lifecycle,
            signer_id="recovery-a",
            signer_profile="profile-r",
            signer_key=key_r,
        )
        lifecycle_digest = lifecycle["lifecycle_root_digest"]
        assert isinstance(lifecycle_digest, str)
        successor_documents = [recovered, final_anchor]
        prior_lifecycle_documents = prior_chain
        active_anchor_id, active_anchor_digest = "bootstrap-c", final_digest
        release_signer_id, release_signer_key, release_signer_profile = (
            "recovery-a", key_r, "profile-r"
        )
        terminal_record = third
    policy_body = {"policy_id": "policy-a", "issuance_purpose": "semantic_ingestion_traceability_recovery_policy", "target_authority_id": AUTHORITY,
                   "bootstrap_anchor_id": "bootstrap-a", "bootstrap_anchor_digest": bootstrap_digest,
                   "eligible_recovery_root_digests": [_root_coordinate(item)[2] for item in recoveries],
                   "minimum_distinct_signatures": len(recoveries),
                   "signer_separation_rule_digest": "1" * 64, "canonical_profile_binding": _binding_for("recovery_policy"),
                   "effective_at": "2026-01-01T00:00:00Z", "recorded_at": "2026-01-01T00:00:00Z", "sequence": 1,
                   "predecessor_policy_digest": None, "expires_at": None,
                   "signer_provenance": {"source_kind": "independently_provisioned_bootstrap_anchor", "signature_purpose": "semantic_ingestion_traceability_recovery_policy", "authority_id": AUTHORITY, "provisioned_channel_id": "channel-a", "bootstrap_anchor_digest": bootstrap_digest, "issuer_id": "bootstrap-a", "key_or_certificate_digest": key_a, "signature_profile_id": "profile-a", "eligible_not_before": "2026-01-01T00:00:00Z", "eligible_not_after": None}}
    policy_digest = _typed_digest(b"memorii:sia-traceability-recovery-policy:v1", policy_body)
    policy = {**policy_body, "recovery_policy_digest": policy_digest,
              "signature": signed("profile-a", key_a, encode_typed_value({"issuance_purpose": policy_body["issuance_purpose"], "body_binding": policy_body["canonical_profile_binding"], "recovery_policy_digest": policy_digest, "signer_provenance": policy_body["signer_provenance"]}))}
    registry = load_registry(Path(__file__).parents[4] / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json")
    external = external_roots or {"design_document_digest": "2" * 64, "structural_manifest_digest": "3" * 64, "coverage_root_digest": "4" * 64, "execution_root_digest": "5" * 64, "report_schema_registry_digest": "6" * 64, "runner_environment_profile_registry_digest": "7" * 64, "trust_snapshot_digest": "8" * 64}
    roots = {
        **_required_roots(registry, external),
        "golden_vector_manifest_digest": golden_vector_manifest_digest,
    }
    signer = {
        **successor_coordinate,
        "signature_purpose": "semantic_ingestion_traceability_release",
        "issuer_id": release_signer_id,
        "key_or_certificate_digest": release_signer_key,
        "signature_profile_id": release_signer_profile,
        "trust_lifecycle_root_digest": lifecycle_digest,
        "lifecycle_record_digest": terminal_record["record_digest"],
    }
    default_release_issued_at = (
        f"2026-01-01T00:00:0{recover_sequence + 2}Z"
        if threshold_recovery
        else "2026-01-01T00:00:03Z"
    )
    selected_release_issued_at = release_issued_at or default_release_issued_at
    release_body = {"release_id": "release-1", "issuance_purpose": "semantic_ingestion_traceability_release", **roots,
                    "grammar_revision": registry.source["grammar_revision"], "canonical_profile_binding": _binding_for("release"),
                    "artifact_dag_digest": "9" * 64, "requirement_binding_registry_digest": "a" * 64, "assertion_registry_digest": "b" * 64, "test_evidence_group_registry_digest": "c" * 64, "golden_vector_manifest_digest": "d" * 64, "section_default_registry_digest": "e" * 64, "structural_mapping_rule_registry_digest": "f" * 64, "override_registry_digest": "0" * 64, "anchor_binding_registry_digest": "1" * 64,
                    "bootstrap_anchor_id": active_anchor_id, "bootstrap_anchor_digest": active_anchor_digest, "bootstrap_anchor_history_digest": "e" * 64, "bootstrap_rotation_sequence": 3 if threshold_recovery else 2, "recovery_trust_policy_digest": policy_digest, "recovery_policy_history_digest": "0" * 64, "recovery_trust_root_digests": [_root_coordinate(item)[2] for item in recoveries], "recovery_root_history_digest": "f" * 64, "trust_lifecycle_root_digest": lifecycle_digest, "epoch": 1, "sequence": 1, "issued_state": "active", "predecessor_release_id": None, "supersedes_release_id": None, "issued_at": selected_release_issued_at, "expires_at": "2026-01-03T00:00:00Z", "signer_coordinate": signer}
    release_body.update({
        name: roots[name]
        for name in (
            "artifact_dag_digest", "requirement_binding_registry_digest",
            "assertion_registry_digest", "test_evidence_group_registry_digest",
            "section_default_registry_digest", "structural_mapping_rule_registry_digest",
            "override_registry_digest", "anchor_binding_registry_digest",
        )
    })
    release_digest = _typed_digest(b"memorii:sia-traceability-release:v1", release_body)
    release = {**release_body, "release_digest": release_digest, "signature": signed(release_signer_profile, release_signer_key, encode_typed_value({"issuance_purpose": release_body["issuance_purpose"], "body_binding": release_body["canonical_profile_binding"], "release_digest": release_digest, "signer_coordinate": signer}))}
    entry_body = {"entry_id": "entry-1", "sequence": 1, "predecessor_entry_digest": None, "release_id": "release-1", "release_digest": release_digest, "release_epoch": 1, "release_sequence": 1, "prior_active_release_digest": None, "prior_release_terminal_state": None, "effective_at": release_body["issued_at"]}
    entry = {**entry_body, "entry_digest": _typed_digest(b"memorii:sia-traceability-release-history-entry:v1", entry_body)}
    history_signer = {**signer, "signature_purpose": "semantic_ingestion_traceability_release_history"}
    history_body = {"history_id": "history-2", "issuance_purpose": "semantic_ingestion_traceability_release_history", "canonical_profile_binding": _binding_for("release_history"), "entries": [entry], "signer_coordinate": history_signer}
    history_digest = _typed_digest(b"memorii:sia-traceability-release-history:v1", history_body)
    history = {**history_body, "release_history_digest": history_digest, "signature": signed(release_signer_profile, release_signer_key, encode_typed_value({"issuance_purpose": history_body["issuance_purpose"], "body_binding": history_body["canonical_profile_binding"], "release_history_digest": history_digest, "signer_coordinate": history_signer}))}
    pointer_signer = {**signer, "signature_purpose": "semantic_ingestion_traceability_active_release_pointer"}
    pointer_body = {"pointer_id": "pointer-1", "issuance_purpose": "semantic_ingestion_traceability_active_release_pointer", "target_authority_id": AUTHORITY, "canonical_profile_binding": _binding_for("active_pointer"), "generation_id": "generation-1", "generation_manifest_digest": "9" * 64, "release_id": "release-1", "release_digest": release_digest, "release_epoch": 1, "release_sequence": 1, "release_history_digest": history_digest, "predecessor_pointer_history_digest": None, "predecessor_active_pointer_digest": None, "pointer_sequence": 1, "published_at": release_body["issued_at"], "signer_coordinate": pointer_signer}
    pointer_digest = _typed_digest(b"memorii:sia-traceability-active-release-pointer:v1", pointer_body)
    pointer = {**pointer_body, "active_pointer_digest": pointer_digest, "signature": signed(release_signer_profile, release_signer_key, encode_typed_value({"issuance_purpose": pointer_body["issuance_purpose"], "body_binding": pointer_body["canonical_profile_binding"], "active_pointer_digest": pointer_digest, "signer_coordinate": pointer_signer}))}
    return {"registry": registry, "bootstrap": artifact("bootstrap", bootstrap), "recovery": artifact("recovery", recovery), "recoveries": tuple(artifact("recovery", item) for item in recoveries), "policy": artifact("recovery_policy", policy), "lifecycle": artifact("lifecycle", lifecycle), "prior_lifecycle": artifact("lifecycle", genesis), "release": artifact("release", release), "history": artifact("release_history", history), "pointer": artifact("active_pointer", pointer), "material": VerifierHeldTrustMaterial(artifact("bootstrap", bootstrap), tuple(artifact("recovery", item) for item in recoveries), lambda p, k, payload, value: value == signature(p, k, payload), artifact("recovery_policy", policy), tuple(artifact("bootstrap", item) for item in successor_documents), tuple(artifact("lifecycle", item) for item in prior_lifecycle_documents)), "roots": external, "release_roots": roots, "now": now, "release_digest": release_digest, "sign": signature}


def bind_chain_to_generation(
    chain: dict[str, object],
    *,
    roots: dict[str, str],
    binding_for_schema: Callable[[str], CanonicalTypedValueProfileBinding],
) -> dict[str, object]:
    """Re-sign a current chain against one exact generation's trust closure."""
    configured_sign = chain.get("sign")
    if not callable(configured_sign):
        raise TypeError("current chain signer is unavailable")
    sign = cast(Callable[[str, str, bytes], bytes], configured_sign)

    bootstrap = _body(chain["bootstrap"])
    policy = _body(chain["policy"])
    lifecycle = _body(chain["lifecycle"])
    prior_release = _body(chain["release"])
    prior_history = _body(chain["history"])
    signer = prior_release["signer_coordinate"]
    if not isinstance(signer, dict):
        raise TypeError("current chain signer coordinate must be a map")
    profile = signer["signature_profile_id"]
    key = signer["key_or_certificate_digest"]
    if not isinstance(profile, str) or not isinstance(key, str):
        raise TypeError("current chain signer coordinate is invalid")

    material = chain["material"]
    if not isinstance(material, VerifierHeldTrustMaterial):
        raise TypeError("current chain material is invalid")
    bootstrap_values = [
        bootstrap,
        *(_body(raw) for raw in material.provisioned_successor_root_bytes),
    ]
    recovery_values = [_body(raw) for raw in material.recovery_root_bytes]

    def history(
        schema: str, history_id: str, field: str, values: list[dict[str, object]],
        domain: bytes,
    ) -> dict[str, object]:
        body = {
            "history_id": history_id,
            "canonical_profile_binding": binding_for_schema(schema).as_value(),
            field: values,
        }
        return {
            **body,
            "history_digest": _typed_digest(domain, body),
        }

    bootstrap_history = history(
        "TraceabilityBootstrapAnchorHistoryBody.v1",
        "generation-bootstrap-history",
        "anchors",
        bootstrap_values,
        b"memorii:sia-traceability-bootstrap-anchor-history:v1",
    )
    recovery_history = history(
        "TraceabilityRecoveryRootHistoryBody.v1",
        "generation-recovery-history",
        "recovery_roots",
        recovery_values,
        b"memorii:sia-traceability-recovery-root-history:v1",
    )
    policy_history = history(
        "TraceabilityRecoveryPolicyHistoryBody.v1",
        "generation-policy-history",
        "policies",
        [policy],
        b"memorii:sia-traceability-recovery-policy-history:v1",
    )
    lifecycle_body = {
        **{
            name: value
            for name, value in lifecycle.items()
            if name not in {
                "lifecycle_root_digest",
                "signatures",
                "signer_coordinates",
            }
        },
        "bootstrap_anchor_history_digest": bootstrap_history["history_digest"],
        "recovery_root_history_digest": recovery_history["history_digest"],
        "recovery_policy_history_digest": policy_history["history_digest"],
    }
    lifecycle_digest = _typed_digest(
        b"memorii:sia-traceability-trust-lifecycle-root:v1", lifecycle_body
    )
    coordinates = lifecycle["signer_coordinates"]
    if not isinstance(coordinates, list):
        raise TypeError("current lifecycle signer coordinates are invalid")
    lifecycle_value = {
        **lifecycle_body,
        "signer_coordinates": coordinates,
        "signatures": [
            sign(
                str(coordinate["signature_profile_id"]),
                str(coordinate["key_or_certificate_digest"]),
                encode_typed_value(
                    {
                        "issuance_purpose": lifecycle_body["issuance_purpose"],
                        "body_binding": lifecycle_body["canonical_profile_binding"],
                        "lifecycle_root_digest": lifecycle_digest,
                        "signer_coordinate": coordinate,
                    }
                ),
            )
            for coordinate in coordinates
            if isinstance(coordinate, dict)
        ],
        "lifecycle_root_digest": lifecycle_digest,
    }
    terminal = lifecycle_value["records"]
    if not isinstance(terminal, list) or not terminal or not isinstance(terminal[-1], dict):
        raise TypeError("current lifecycle terminal record is invalid")
    release_signer = {
        **signer,
        "trust_lifecycle_root_digest": lifecycle_digest,
        "lifecycle_record_digest": terminal[-1]["record_digest"],
    }
    release_id = str(prior_release["release_id"])
    snapshot_body = {
        "snapshot_id": "generation-trust-snapshot",
        "issuance_purpose": "semantic_ingestion_traceability_release_trust_snapshot",
        "canonical_profile_binding": binding_for_schema(
            "TraceabilityReleaseTrustSnapshotBody.v1"
        ).as_value(),
        "release_id": release_id,
        "release_epoch": prior_release["epoch"],
        "release_sequence": prior_release["sequence"],
        "bootstrap_anchor_digest": prior_release["bootstrap_anchor_digest"],
        "recovery_policy_digest": policy["recovery_policy_digest"],
        "trust_lifecycle_root_digest": lifecycle_digest,
        "lifecycle_recorded_time_cutoff": prior_release["issued_at"],
        "qualified_issuers": [release_signer],
        "created_at": prior_release["issued_at"],
    }
    snapshot = {
        **snapshot_body,
        "trust_snapshot_digest": _typed_digest(
            b"memorii:sia-traceability-release-trust-snapshot:v1", snapshot_body
        ),
    }
    release_body = {
        **{
            name: value
            for name, value in prior_release.items()
            if name not in {"release_digest", "signature"}
        },
        **{name: value for name, value in roots.items() if name in prior_release},
        "bootstrap_anchor_history_digest": bootstrap_history["history_digest"],
        "recovery_root_history_digest": recovery_history["history_digest"],
        "recovery_policy_history_digest": policy_history["history_digest"],
        "trust_lifecycle_root_digest": lifecycle_digest,
        "trust_snapshot_digest": snapshot["trust_snapshot_digest"],
        "signer_coordinate": release_signer,
    }
    release_digest = _typed_digest(b"memorii:sia-traceability-release:v1", release_body)
    release = {
        **release_body,
        "release_digest": release_digest,
        "signature": sign(
            profile,
            key,
            encode_typed_value(
                {
                    "issuance_purpose": release_body["issuance_purpose"],
                    "body_binding": release_body["canonical_profile_binding"],
                    "release_digest": release_digest,
                    "signer_coordinate": release_signer,
                }
            ),
        ).hex(),
    }
    release_sequence = release_body["sequence"]
    if not isinstance(release_sequence, int):
        raise TypeError("current release sequence is invalid")
    prior_entries = prior_history.get("entries")
    if not isinstance(prior_entries, list) or not prior_entries:
        raise TypeError("current release history is invalid")
    retained_entries = [] if release_sequence == 1 else prior_entries[:-1]
    predecessor_entry_digest = (
        retained_entries[-1].get("entry_digest")
        if retained_entries and isinstance(retained_entries[-1], dict)
        else None
    )
    entry_body = {
        "entry_id": f"generation-entry-{release_sequence}",
        "sequence": release_sequence,
        "predecessor_entry_digest": predecessor_entry_digest,
        "release_id": release_id,
        "release_digest": release_digest,
        "release_epoch": release_body["epoch"],
        "release_sequence": release_body["sequence"],
        "prior_active_release_digest": (
            prior_entries[-2].get("release_digest")
            if release_sequence > 1
            and len(prior_entries) > 1
            and isinstance(prior_entries[-2], dict)
            else None
        ),
        "prior_release_terminal_state": (
            "superseded" if release_sequence > 1 else None
        ),
        "effective_at": release_body["issued_at"],
    }
    entry = {
        **entry_body,
        "entry_digest": _typed_digest(
            b"memorii:sia-traceability-release-history-entry:v1", entry_body
        ),
    }
    history_signer = {
        **release_signer,
        "signature_purpose": "semantic_ingestion_traceability_release_history",
    }
    release_history_body = {
        "history_id": "generation-release-history",
        "issuance_purpose": "semantic_ingestion_traceability_release_history",
        "canonical_profile_binding": binding_for_schema(
            "TraceabilityReleaseHistoryBody.v1"
        ).as_value(),
        "entries": [*retained_entries, entry],
        "signer_coordinate": history_signer,
    }
    history_digest = _typed_digest(
        b"memorii:sia-traceability-release-history:v1", release_history_body
    )
    release_history = {
        **release_history_body,
        "release_history_digest": history_digest,
        "signature": sign(
            profile,
            key,
            encode_typed_value(
                {
                    "issuance_purpose": release_history_body["issuance_purpose"],
                    "body_binding": release_history_body["canonical_profile_binding"],
                    "release_history_digest": history_digest,
                    "signer_coordinate": history_signer,
                }
            ),
        ).hex(),
    }
    prior_pointer = _body(chain["pointer"])
    pointer_signer = {
        **release_signer,
        "signature_purpose": "semantic_ingestion_traceability_active_release_pointer",
    }
    pointer_body = {
        **{
            name: value
            for name, value in prior_pointer.items()
            if name not in {"active_pointer_digest", "signature"}
        },
        "release_id": release_id,
        "release_digest": release_digest,
        "release_epoch": release_body["epoch"],
        "release_sequence": release_body["sequence"],
        "release_history_digest": history_digest,
        "signer_coordinate": pointer_signer,
    }
    pointer_digest = _typed_digest(
        b"memorii:sia-traceability-active-release-pointer:v1", pointer_body
    )
    pointer = {
        **pointer_body,
        "active_pointer_digest": pointer_digest,
        "signature": sign(
            profile,
            key,
            encode_typed_value(
                {
                    "issuance_purpose": pointer_body["issuance_purpose"],
                    "body_binding": pointer_body["canonical_profile_binding"],
                    "active_pointer_digest": pointer_digest,
                    "signer_coordinate": pointer_signer,
                }
            ),
        ).hex(),
    }
    artifact_for = {
        "bootstrap_anchor_history": ("TraceabilityBootstrapAnchorHistoryBody.v1", bootstrap_history),
        "recovery_root_history": ("TraceabilityRecoveryRootHistoryBody.v1", recovery_history),
        "recovery_policy_history": ("TraceabilityRecoveryPolicyHistoryBody.v1", policy_history),
        "trust_lifecycle_root": ("TraceabilityTrustLifecycleRootBody.v1", lifecycle_value),
        "trust_snapshot": ("TraceabilityReleaseTrustSnapshotBody.v1", snapshot),
        "release": ("SemanticIngestionTraceabilityReleaseBody.v1", release),
        "release_history": ("TraceabilityReleaseHistoryBody.v1", release_history),
    }
    return {
        **chain,
        "roots": {
            **cast(Mapping[str, str], chain["roots"]),
            "trust_snapshot_digest": cast(str, snapshot["trust_snapshot_digest"]),
        },
        "lifecycle": serialize_artifact(
            lifecycle_value, binding_for_schema("TraceabilityTrustLifecycleRootBody.v1")
        ),
        "release": serialize_artifact(
            release, binding_for_schema("SemanticIngestionTraceabilityReleaseBody.v1")
        ),
        "history": serialize_artifact(
            release_history, binding_for_schema("TraceabilityReleaseHistoryBody.v1")
        ),
        "pointer": serialize_artifact(
            pointer, binding_for_schema("TraceabilityActiveReleasePointerBody.v1")
        ),
        "generation_artifacts": {
            name: serialize_artifact(value, binding_for_schema(schema))
            for name, (schema, value) in artifact_for.items()
        },
        "release_roots": {
            **cast(Mapping[str, str], chain["release_roots"]),
            **roots,
            "trust_snapshot_digest": snapshot["trust_snapshot_digest"],
        },
        "release_digest": release_digest,
    }


def _body(raw: object) -> dict[str, object]:
    if not isinstance(raw, bytes):
        raise TypeError("current chain artifact must be bytes")
    value = decode_typed_value(decode_artifact(raw).canonical_value_bytes)
    if not isinstance(value, dict):
        raise TypeError("current chain artifact body must be a map")
    return value


def current_chain_successor(chain: dict[str, object]) -> dict[str, object]:
    """Append an exact sequence-two release/history/pointer transaction."""
    prior_release = _body(chain["release"])
    prior_history = _body(chain["history"])
    prior_pointer = _body(chain["pointer"])
    signer = prior_release["signer_coordinate"]
    if not isinstance(signer, dict):
        raise TypeError("current chain release signer must be a map")
    profile = signer["signature_profile_id"]
    key = signer["key_or_certificate_digest"]
    if not isinstance(profile, str) or not isinstance(key, str):
        raise TypeError("current chain release signer coordinate is invalid")

    def signed(payload: bytes) -> str:
        return sha256(profile.encode() + b"\0" + key.encode() + b"\0" + payload).hexdigest()

    release_body = {
        **{
            name: value
            for name, value in prior_release.items()
            if name not in {"release_digest", "signature"}
        },
        "release_id": "release-2",
        "sequence": 2,
        "predecessor_release_id": prior_release["release_id"],
        "supersedes_release_id": prior_release["release_id"],
        "issued_at": "2026-01-01T00:00:04Z",
    }
    release_digest = _typed_digest(
        b"memorii:sia-traceability-release:v1", release_body
    )
    release = {
        **release_body,
        "release_digest": release_digest,
        "signature": signed(
            encode_typed_value(
                {
                    "issuance_purpose": release_body["issuance_purpose"],
                    "body_binding": release_body["canonical_profile_binding"],
                    "release_digest": release_digest,
                    "signer_coordinate": signer,
                }
            )
        ),
    }
    prior_entries = prior_history["entries"]
    if not isinstance(prior_entries, list) or len(prior_entries) != 1:
        raise TypeError("current chain genesis history is invalid")
    prior_entry = prior_entries[0]
    if not isinstance(prior_entry, dict):
        raise TypeError("current chain genesis history entry is invalid")
    entry_body = {
        "entry_id": "entry-2",
        "sequence": 2,
        "predecessor_entry_digest": prior_entry["entry_digest"],
        "release_id": release["release_id"],
        "release_digest": release_digest,
        "release_epoch": release["epoch"],
        "release_sequence": release["sequence"],
        "prior_active_release_digest": prior_release["release_digest"],
        "prior_release_terminal_state": "superseded",
        "effective_at": release["issued_at"],
    }
    entry = {
        **entry_body,
        "entry_digest": _typed_digest(
            b"memorii:sia-traceability-release-history-entry:v1", entry_body
        ),
    }
    history_signer = {
        **signer,
        "signature_purpose": "semantic_ingestion_traceability_release_history",
    }
    history_body = {
        "history_id": prior_history["history_id"],
        "issuance_purpose": prior_history["issuance_purpose"],
        "canonical_profile_binding": prior_history["canonical_profile_binding"],
        "entries": [prior_entry, entry],
        "signer_coordinate": history_signer,
    }
    history_digest = _typed_digest(
        b"memorii:sia-traceability-release-history:v1", history_body
    )
    history = {
        **history_body,
        "release_history_digest": history_digest,
        "signature": signed(
            encode_typed_value(
                {
                    "issuance_purpose": history_body["issuance_purpose"],
                    "body_binding": history_body["canonical_profile_binding"],
                    "release_history_digest": history_digest,
                    "signer_coordinate": history_signer,
                }
            )
        ),
    }
    pointer_signer = {
        **signer,
        "signature_purpose": "semantic_ingestion_traceability_active_release_pointer",
    }
    pointer_body = {
        **{
            name: value
            for name, value in prior_pointer.items()
            if name not in {"active_pointer_digest", "signature"}
        },
        "pointer_id": "pointer-2",
        "generation_id": "generation-2",
        "release_id": release["release_id"],
        "release_digest": release_digest,
        "release_sequence": 2,
        "release_history_digest": history_digest,
        "predecessor_pointer_history_digest": None,
        "predecessor_active_pointer_digest": prior_pointer["active_pointer_digest"],
        "pointer_sequence": 2,
        "published_at": release["issued_at"],
        "signer_coordinate": pointer_signer,
    }
    pointer_digest = _typed_digest(
        b"memorii:sia-traceability-active-release-pointer:v1", pointer_body
    )
    pointer = {
        **pointer_body,
        "active_pointer_digest": pointer_digest,
        "signature": signed(
            encode_typed_value(
                {
                    "issuance_purpose": pointer_body["issuance_purpose"],
                    "body_binding": pointer_body["canonical_profile_binding"],
                    "active_pointer_digest": pointer_digest,
                    "signer_coordinate": pointer_signer,
                }
            )
        ),
    }
    return {
        **chain,
        "release": _artifact("release", release),
        "history": _artifact("release_history", history),
        "pointer": _artifact("active_pointer", pointer),
        "historical_releases": (chain["release"],),
        "release_digest": release_digest,
    }

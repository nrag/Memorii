from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest
from memorii.tools.semantic_ingestion_execution_evidence import (
    ExecutionEvidenceError,
    ExecutionEvidenceRecord,
    artifact_digest,
    sign_record,
    verify_execution_evidence,
)
from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping


@dataclass(frozen=True)
class EvidenceInputs:
    mappings: tuple[UnitRequirementMapping, ...]
    records: tuple[ExecutionEvidenceRecord, ...]
    artifacts: dict[str, bytes]
    expected_design_digest: str
    expected_implementation_revision: str
    expected_implementation_tree_digest: str
    expected_trust_context_digest: str
    trusted_issuers: dict[str, bytes]
    now: datetime

    def verify(self) -> None:
        verify_execution_evidence(
            mappings=self.mappings,
            records=self.records,
            artifacts=self.artifacts,
            expected_design_digest=self.expected_design_digest,
            expected_implementation_revision=self.expected_implementation_revision,
            expected_implementation_tree_digest=self.expected_implementation_tree_digest,
            expected_trust_context_digest=self.expected_trust_context_digest,
            trusted_issuers=self.trusted_issuers,
            now=self.now,
        )


def _evidence() -> tuple[ExecutionEvidenceRecord, EvidenceInputs]:
    secret = b"trusted-reviewer-key"
    test_bytes, result_bytes = b"pytest SIA-T03", b"passed"
    test_digest, result_digest = artifact_digest(test_bytes), artifact_digest(result_bytes)
    mapping = UnitRequirementMapping("unit", "key", "SIA-R03", "acceptance", "assertion", 1, "SIA-T03-EVIDENCE")
    unsigned = ExecutionEvidenceRecord(
        ("key",), ("SIA-R03",), "assertion", 1, "SIA-T03-EVIDENCE", test_digest, "d" * 64, "revision", "t" * 64,
        "run-1", "executed", "pass", result_digest, datetime(2026, 1, 1, tzinfo=UTC), "reviewer",
        "semantic_ingestion_normative_evidence", "trust", None, "",
    )
    record = replace(unsigned, signature=sign_record(unsigned, secret))
    inputs = EvidenceInputs(
        mappings=(mapping,),
        records=(record,),
        artifacts={test_digest: test_bytes, result_digest: result_bytes},
        expected_design_digest="d" * 64,
        expected_implementation_revision="revision",
        expected_implementation_tree_digest="t" * 64,
        expected_trust_context_digest="trust",
        trusted_issuers={"reviewer": secret},
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    return record, inputs


def test_sia_t03_legacy_caller_hmac_cannot_authorize_evidence() -> None:
    _, inputs = _evidence()
    with pytest.raises(ExecutionEvidenceError, match="not approval-capable"):
        inputs.verify()


@pytest.mark.parametrize("field,value", [("execution_status", "not_executed"), ("execution_result", "fail"), ("design_document_digest", "x" * 64), ("implementation_revision", "other"), ("implementation_tree_digest", "x" * 64), ("trust_context_digest", "other"), ("signature", "forged")])
def test_sia_t03_evidence_rejects_unexecuted_failed_stale_or_forged_records(field: str, value: str) -> None:
    record, inputs = _evidence()
    if field == "execution_status":
        mutated = replace(record, execution_status=value)
    elif field == "execution_result":
        mutated = replace(record, execution_result=value)
    elif field == "design_document_digest":
        mutated = replace(record, design_document_digest=value)
    elif field == "implementation_revision":
        mutated = replace(record, implementation_revision=value)
    elif field == "implementation_tree_digest":
        mutated = replace(record, implementation_tree_digest=value)
    elif field == "trust_context_digest":
        mutated = replace(record, trust_context_digest=value)
    else:
        mutated = replace(record, signature=value)
    with pytest.raises(ExecutionEvidenceError):
        replace(inputs, records=(mutated,)).verify()


def test_sia_t03_legacy_caller_hmac_is_rejected_before_record_details() -> None:
    record, inputs = _evidence()
    with pytest.raises(ExecutionEvidenceError, match="not approval-capable"):
        replace(inputs, records=(replace(record, expires_at=datetime(2026, 1, 1, tzinfo=UTC)),)).verify()


def test_sia_t03_release_bound_helper_is_not_a_public_approval_api() -> None:
    import memorii.tools.semantic_ingestion_execution_evidence as evidence

    assert not hasattr(evidence, "verify_release_bound_execution")

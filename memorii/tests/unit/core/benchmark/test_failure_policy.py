from memorii.core.benchmark.failure_policy import (
    FailureBucketSeverity,
    failure_bucket_severity,
)


def test_warning_and_provider_buckets_are_explicitly_noncritical() -> None:
    assert failure_bucket_severity("extra_context_provenance") == FailureBucketSeverity.WARNING
    assert failure_bucket_severity("runtime_provider_failure") == FailureBucketSeverity.OPERATIONAL


def test_new_semantic_failure_bucket_fails_closed() -> None:
    assert failure_bucket_severity("new_unclassified_semantic_failure") == FailureBucketSeverity.CRITICAL


def test_known_high_risk_failures_are_critical() -> None:
    for bucket in (
        "hidden_fact_answer_leak",
        "source_trust_inversion",
        "entity_rekey_lost",
        "provenance_chain_broken",
        "runtime_action_status_mismatch",
        "runtime_execution_state_ambiguous",
    ):
        assert failure_bucket_severity(bucket) == FailureBucketSeverity.CRITICAL

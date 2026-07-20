"""Central severity policy for memory-evolution benchmark diagnostics."""

from __future__ import annotations

from enum import StrEnum


class FailureBucketSeverity(StrEnum):
    """The action a benchmark gate takes for a diagnostic bucket."""

    CRITICAL = "critical"
    OPERATIONAL = "operational"
    WARNING = "warning"


WARNING_ONLY_BUCKETS = frozenset(
    {
        "extra_context_provenance",
        "extra_provenance_noise",
        "graph_answer_optional_missing",
        "role_channel_context_overlap",
    }
)

WARNING_ONLY_BUCKET_RATIONALES = {
    "extra_context_provenance": "Context channels may include broader audit evidence when selected and supporting channels remain clean.",
    "extra_provenance_noise": "Extra non-support provenance is retained for precision analysis but is not selected or supporting truth.",
    "graph_answer_optional_missing": "Structured graph channels are authoritative when natural-language answer text is optional.",
    "role_channel_context_overlap": "An entity may be useful context in one role while another role is selected, provided answer-bearing channels remain disjoint.",
}

if frozenset(WARNING_ONLY_BUCKET_RATIONALES) != WARNING_ONLY_BUCKETS:
    raise RuntimeError("warning bucket rationales must cover the warning-only severity policy exactly")

# Provider availability is gated by provider/fallback rates rather than by a
# semantic zero-tolerance policy. Everything else fails closed: an unregistered
# semantic bucket is critical until it is deliberately classified here.
OPERATIONAL_FAILURE_BUCKETS = frozenset(
    {
        "llm_not_configured",
        "llm_provider_failure",
        "provider_error",
        "runtime_provider_failure",
        "runtime_provider_fallback",
        "schema_validation",
        "invalid_json",
    }
)


def failure_bucket_severity(bucket: str) -> FailureBucketSeverity:
    """Classify a bucket with a fail-closed default for new semantics."""

    if bucket in WARNING_ONLY_BUCKETS:
        return FailureBucketSeverity.WARNING
    if bucket in OPERATIONAL_FAILURE_BUCKETS:
        return FailureBucketSeverity.OPERATIONAL
    return FailureBucketSeverity.CRITICAL


def is_critical_failure_bucket(bucket: str) -> bool:
    return failure_bucket_severity(bucket) == FailureBucketSeverity.CRITICAL

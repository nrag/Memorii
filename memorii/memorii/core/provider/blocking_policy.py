"""Provider-level policy matrix for domain writes.

This module intentionally avoids text-semantic heuristics. Decisions are based on
provider operation + write kind semantics so the policy is language-agnostic.
"""

from __future__ import annotations

from memorii.core.provider.models import (
    ProviderDomainPermission,
    ProviderOperation,
    ProviderPolicyDecision,
)
from memorii.domain.enums import MemoryDomain

_OPERATION_PERMISSIONS: dict[ProviderOperation, ProviderDomainPermission] = {
    ProviderOperation.CHAT_USER_TURN: ProviderDomainPermission(
        operation=ProviderOperation.CHAT_USER_TURN,
        allowed_raw_append_domains=[MemoryDomain.TRANSCRIPT],
        allowed_candidate_domains=[],
        blocked_commit_domains=[MemoryDomain.EPISODIC, MemoryDomain.SEMANTIC, MemoryDomain.USER],
    ),
    ProviderOperation.CHAT_ASSISTANT_TURN: ProviderDomainPermission(
        operation=ProviderOperation.CHAT_ASSISTANT_TURN,
        allowed_raw_append_domains=[MemoryDomain.TRANSCRIPT],
        allowed_candidate_domains=[],
        blocked_commit_domains=[MemoryDomain.EPISODIC, MemoryDomain.SEMANTIC, MemoryDomain.USER],
    ),
    ProviderOperation.MEMORY_WRITE_LONGTERM: ProviderDomainPermission(
        operation=ProviderOperation.MEMORY_WRITE_LONGTERM,
        allowed_raw_append_domains=[MemoryDomain.TRANSCRIPT],
        allowed_candidate_domains=[MemoryDomain.SEMANTIC],
        blocked_commit_domains=[MemoryDomain.SEMANTIC, MemoryDomain.USER, MemoryDomain.EPISODIC],
    ),
    ProviderOperation.MEMORY_WRITE_USER: ProviderDomainPermission(
        operation=ProviderOperation.MEMORY_WRITE_USER,
        allowed_raw_append_domains=[MemoryDomain.TRANSCRIPT],
        allowed_candidate_domains=[MemoryDomain.USER],
        blocked_commit_domains=[MemoryDomain.USER, MemoryDomain.SEMANTIC, MemoryDomain.EPISODIC],
    ),
    ProviderOperation.MEMORY_WRITE_DAILYLOG: ProviderDomainPermission(
        operation=ProviderOperation.MEMORY_WRITE_DAILYLOG,
        allowed_raw_append_domains=[MemoryDomain.TRANSCRIPT],
        allowed_candidate_domains=[MemoryDomain.EPISODIC],
        blocked_commit_domains=[MemoryDomain.SEMANTIC, MemoryDomain.USER],
    ),
    ProviderOperation.SESSION_END: ProviderDomainPermission(
        operation=ProviderOperation.SESSION_END,
        allowed_raw_append_domains=[MemoryDomain.TRANSCRIPT],
        allowed_candidate_domains=[MemoryDomain.EPISODIC],
        blocked_commit_domains=[MemoryDomain.SEMANTIC, MemoryDomain.USER],
    ),
    ProviderOperation.PRE_COMPRESS: ProviderDomainPermission(
        operation=ProviderOperation.PRE_COMPRESS,
        allowed_raw_append_domains=[MemoryDomain.TRANSCRIPT],
        allowed_candidate_domains=[MemoryDomain.EPISODIC],
        blocked_commit_domains=[MemoryDomain.SEMANTIC, MemoryDomain.USER],
    ),
    ProviderOperation.DELEGATION_RESULT: ProviderDomainPermission(
        operation=ProviderOperation.DELEGATION_RESULT,
        allowed_raw_append_domains=[MemoryDomain.TRANSCRIPT],
        allowed_candidate_domains=[MemoryDomain.EPISODIC],
        blocked_commit_domains=[MemoryDomain.SEMANTIC, MemoryDomain.USER],
    ),
    ProviderOperation.PREFETCH_QUERY: ProviderDomainPermission(
        operation=ProviderOperation.PREFETCH_QUERY,
        allowed_raw_append_domains=[],
        allowed_candidate_domains=[],
        blocked_commit_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EPISODIC, MemoryDomain.SEMANTIC, MemoryDomain.USER],
    ),
    ProviderOperation.UNKNOWN: ProviderDomainPermission(
        operation=ProviderOperation.UNKNOWN,
        allowed_raw_append_domains=[],
        allowed_candidate_domains=[],
        blocked_commit_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EPISODIC, MemoryDomain.SEMANTIC, MemoryDomain.USER],
    ),
}


def evaluate_operation_policy(*, operation: ProviderOperation) -> ProviderPolicyDecision:
    permission = _OPERATION_PERMISSIONS[operation]
    reasons = {
        domain.value: f"operation '{operation.value}' blocks direct '{domain.value}' commit in provider ingestion path"
        for domain in permission.blocked_commit_domains
    }
    return ProviderPolicyDecision(
        operation=operation,
        allowed_raw_append_domains=permission.allowed_raw_append_domains,
        allowed_candidate_domains=permission.allowed_candidate_domains,
        blocked_commit_domains=permission.blocked_commit_domains,
        blocked_reasons=reasons,
    )

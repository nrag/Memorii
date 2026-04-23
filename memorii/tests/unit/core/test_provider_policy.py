from memorii.core.provider.blocking_policy import evaluate_operation_policy
from memorii.core.provider.models import ProviderOperation
from memorii.domain.enums import MemoryDomain


def test_chat_user_turn_allows_transcript_raw_append_and_blocks_direct_commits() -> None:
    policy = evaluate_operation_policy(operation=ProviderOperation.CHAT_USER_TURN)
    assert policy.allowed_raw_append_domains == [MemoryDomain.TRANSCRIPT]
    assert policy.allowed_candidate_domains == []
    assert set(policy.blocked_commit_domains) == {MemoryDomain.EPISODIC, MemoryDomain.SEMANTIC, MemoryDomain.USER}


def test_chat_assistant_turn_policy_matches_user_turn_commit_safety() -> None:
    policy = evaluate_operation_policy(operation=ProviderOperation.CHAT_ASSISTANT_TURN)
    assert policy.allowed_raw_append_domains == [MemoryDomain.TRANSCRIPT]
    assert policy.allowed_candidate_domains == []
    assert set(policy.blocked_commit_domains) == {MemoryDomain.EPISODIC, MemoryDomain.SEMANTIC, MemoryDomain.USER}


def test_memory_write_longterm_allows_semantic_candidate_only() -> None:
    policy = evaluate_operation_policy(operation=ProviderOperation.MEMORY_WRITE_LONGTERM)
    assert MemoryDomain.TRANSCRIPT in policy.allowed_raw_append_domains
    assert policy.allowed_candidate_domains == [MemoryDomain.SEMANTIC]
    assert MemoryDomain.SEMANTIC in policy.blocked_commit_domains
    assert MemoryDomain.USER in policy.blocked_commit_domains


def test_memory_write_user_allows_user_candidate_only() -> None:
    policy = evaluate_operation_policy(operation=ProviderOperation.MEMORY_WRITE_USER)
    assert MemoryDomain.TRANSCRIPT in policy.allowed_raw_append_domains
    assert policy.allowed_candidate_domains == [MemoryDomain.USER]
    assert MemoryDomain.USER in policy.blocked_commit_domains
    assert MemoryDomain.SEMANTIC in policy.blocked_commit_domains


def test_session_end_allows_episodic_candidate_and_blocks_semantic_user_commit() -> None:
    policy = evaluate_operation_policy(operation=ProviderOperation.SESSION_END)
    assert policy.allowed_raw_append_domains == [MemoryDomain.TRANSCRIPT]
    assert policy.allowed_candidate_domains == [MemoryDomain.EPISODIC]
    assert set(policy.blocked_commit_domains) == {MemoryDomain.SEMANTIC, MemoryDomain.USER}


def test_delegation_result_allows_transcript_and_episodic_candidate() -> None:
    policy = evaluate_operation_policy(operation=ProviderOperation.DELEGATION_RESULT)
    assert policy.allowed_raw_append_domains == [MemoryDomain.TRANSCRIPT]
    assert policy.allowed_candidate_domains == [MemoryDomain.EPISODIC]
    assert set(policy.blocked_commit_domains) == {MemoryDomain.SEMANTIC, MemoryDomain.USER}

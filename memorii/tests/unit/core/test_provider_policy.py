from memorii.core.provider.blocking_policy import evaluate_operation_policy, extract_text_features
from memorii.core.provider.models import ProviderOperation
from memorii.domain.enums import MemoryDomain


def test_sync_turn_blocks_speculative_user_inference() -> None:
    features = extract_text_features("Maybe the user likes dark mode.")
    blocked, allowed, reasons = evaluate_operation_policy(operation=ProviderOperation.CHAT_ASSISTANT_TURN, features=features)
    assert MemoryDomain.USER in blocked
    assert MemoryDomain.EPISODIC not in allowed
    assert MemoryDomain.USER.value in reasons


def test_memory_write_memory_allows_semantic_candidate_only() -> None:
    features = extract_text_features("The API default timeout is 30 seconds.")
    blocked, allowed, _ = evaluate_operation_policy(operation=ProviderOperation.MEMORY_WRITE_LONGTERM, features=features)
    assert MemoryDomain.SEMANTIC in allowed
    assert MemoryDomain.SEMANTIC in blocked


def test_memory_write_user_speculative_is_blocked() -> None:
    features = extract_text_features("Probably the user prefers very long answers.")
    blocked, allowed, reasons = evaluate_operation_policy(operation=ProviderOperation.MEMORY_WRITE_USER, features=features)
    assert MemoryDomain.USER in blocked
    assert MemoryDomain.USER not in allowed
    assert MemoryDomain.USER.value in reasons


def test_session_summary_event_allows_episodic_candidate() -> None:
    features = extract_text_features("Incident resolved today after restart fixed database connection.")
    blocked, allowed, _ = evaluate_operation_policy(operation=ProviderOperation.SESSION_END, features=features)
    assert MemoryDomain.EPISODIC in allowed
    assert MemoryDomain.SEMANTIC in blocked

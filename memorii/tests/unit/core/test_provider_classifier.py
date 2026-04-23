from memorii.core.provider.classifier import classify_memory_target
from memorii.core.provider.models import ProviderOperation


def test_classify_memory_targets() -> None:
    assert classify_memory_target("memory") == ProviderOperation.MEMORY_WRITE_LONGTERM
    assert classify_memory_target("user") == ProviderOperation.MEMORY_WRITE_USER
    assert classify_memory_target("dailylog") == ProviderOperation.MEMORY_WRITE_DAILYLOG
    assert classify_memory_target("something_else") == ProviderOperation.UNKNOWN

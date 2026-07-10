from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Protocol

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMStructuredClient
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.tools.run_live_llm_eval import EvalFakeClient

_DEFAULT_EVAL_FAKE_CLIENT = EvalFakeClient
_DEFAULT_HOTPOTQA_DATASET = files("memorii.core.benchmark.fixture_sets").joinpath("hotpotqa_sample.json")


class LLMClientFactoryProtocol(Protocol):
    """Factory interface used by benchmark runners to create live LLM clients."""

    @staticmethod
    def from_config(config: LLMRuntimeConfig) -> LLMStructuredClient:
        ...


@contextmanager
def hotpotqa_default_dataset_path() -> Iterator[Path]:
    """Yield the package-owned HotpotQA sample as a real filesystem path."""

    with as_file(_DEFAULT_HOTPOTQA_DATASET) as dataset_path:
        yield dataset_path


@dataclass(frozen=True)
class BenchmarkRuntimeDependencies:
    """Runtime dependency seams for benchmark suite runners.

    Tests historically patched ``memorii.tools.run_benchmark.EvalFakeClient``
    and ``LLMClientFactory``. The CLI still exposes those patch points, but the
    registry now passes them explicitly instead of mutating suite module globals.
    """

    eval_fake_client_cls: type[LLMStructuredClient] = EvalFakeClient
    llm_client_factory: LLMClientFactoryProtocol = LLMClientFactory
    default_eval_fake_client_cls: type[LLMStructuredClient] = _DEFAULT_EVAL_FAKE_CLIENT

    def is_default_fake_client(self) -> bool:
        return self.eval_fake_client_cls is self.default_eval_fake_client_cls

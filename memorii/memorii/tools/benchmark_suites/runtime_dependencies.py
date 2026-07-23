from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import as_file, files
from pathlib import Path

from memorii.core.benchmark.artifact_rows import FinalOutputSource
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_eval.fake_client import EvalFakeClient
from memorii.core.llm_provider.base import LLMStructuredClient
from memorii.core.llm_provider.factory import LLMClientFactory

_DEFAULT_HOTPOTQA_DATASET = files("memorii.core.benchmark.fixture_sets").joinpath("hotpotqa_sample.json")


class ExecutionBackend(StrEnum):
    FAKE_ORACLE = "fake_oracle"
    LIVE_PROVIDER = "live_provider"


class DryRunDecisionStrategy(StrEnum):
    ORACLE_ADAPTERS = "oracle_adapters"
    CLIENT_ADAPTERS = "client_adapters"


@dataclass(frozen=True)
class LLMClientBinding:
    """A client and its authoritative execution provenance."""

    client: LLMStructuredClient
    backend: ExecutionBackend
    provider_name: str

    def __post_init__(self) -> None:
        if not self.provider_name.strip():
            raise ValueError("provider_name must not be empty")
        actual_provider = getattr(self.client, "provider_name", "")
        if actual_provider and actual_provider != self.provider_name:
            raise ValueError("binding provider_name does not match the client")

    @property
    def final_output_source(self) -> FinalOutputSource:
        return "fake_oracle" if self.backend == ExecutionBackend.FAKE_ORACLE else "live_llm"


FakeClientBindingFactory = Callable[[], LLMClientBinding]
LiveClientBindingFactory = Callable[[LLMRuntimeConfig], LLMClientBinding]


def default_fake_client_binding() -> LLMClientBinding:
    client = EvalFakeClient()
    return LLMClientBinding(
        client=client,
        backend=ExecutionBackend.FAKE_ORACLE,
        provider_name=client.provider_name,
    )


def default_live_client_binding(config: LLMRuntimeConfig) -> LLMClientBinding:
    client = LLMClientFactory.from_config(config)
    return LLMClientBinding(
        client=client,
        backend=ExecutionBackend.LIVE_PROVIDER,
        provider_name=client.provider_name,
    )


@contextmanager
def hotpotqa_default_dataset_path() -> Iterator[Path]:
    """Yield the package-owned HotPotQA sample as a real filesystem path."""

    with as_file(_DEFAULT_HOTPOTQA_DATASET) as dataset_path:
        yield dataset_path


@dataclass(frozen=True)
class BenchmarkRuntimeDependencies:
    """Explicit composition-root dependencies for benchmark execution."""

    fake_client_binding_factory: FakeClientBindingFactory = default_fake_client_binding
    live_client_binding_factory: LiveClientBindingFactory = default_live_client_binding
    dry_run_decision_strategy: DryRunDecisionStrategy = DryRunDecisionStrategy.ORACLE_ADAPTERS

    def bind_llm_client(
        self,
        *,
        dry_run: bool,
        config: LLMRuntimeConfig,
    ) -> LLMClientBinding:
        binding = (
            self.fake_client_binding_factory()
            if dry_run
            else self.live_client_binding_factory(config)
        )
        expected_backend = (
            ExecutionBackend.FAKE_ORACLE if dry_run else ExecutionBackend.LIVE_PROVIDER
        )
        if binding.backend != expected_backend:
            raise ValueError(
                f"{'dry' if dry_run else 'live'} execution requires "
                f"{expected_backend.value} provenance"
            )
        return binding

    def use_oracle_adapters(self, *, dry_run: bool) -> bool:
        return dry_run and self.dry_run_decision_strategy == DryRunDecisionStrategy.ORACLE_ADAPTERS

    def create_live_client(self, config: LLMRuntimeConfig) -> LLMStructuredClient:
        return self.bind_llm_client(dry_run=False, config=config).client

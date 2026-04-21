"""HotpotQA adapter utilities for benchmark fixture generation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import (
    BenchmarkRunConfig,
    BenchmarkRunReport,
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    BaselineApplicability,
    BaselinePolicy,
    BenchmarkSystem,
    ConflictCandidate,
    ConflictResolutionFixture,
    EndToEndFixture,
    ImplicitRecallFixture,
    LongHorizonDegradationFixture,
    RetrievalFixture,
    RetrievalFixtureMemoryItem,
    RoutingFixture,
)
from memorii.core.benchmark.reporting import write_artifacts
from memorii.domain.enums import MemoryDomain
from memorii.domain.retrieval import RetrievalIntent, RetrievalScope
from memorii.domain.routing import InboundEvent, InboundEventClass


class HotpotContext(BaseModel):
    title: str
    sentences: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class HotpotQAExample(BaseModel):
    example_id: str
    question: str
    answer: str
    question_type: Literal["bridge", "comparison"] | None = None
    supporting_facts: list[tuple[str, int]] = Field(default_factory=list)
    context: list[HotpotContext] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def load_hotpotqa_examples(path: str | Path, *, split: str | None = None) -> list[HotpotQAExample]:
    source = Path(path)
    if source.suffix == ".jsonl":
        rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            if split is not None and split in payload and isinstance(payload[split], list):
                rows = payload[split]
            elif "data" in payload and isinstance(payload["data"], list):
                rows = payload["data"]
            else:
                first_list = next((value for value in payload.values() if isinstance(value, list)), [])
                rows = list(first_list)
        else:
            rows = []

    examples = [_normalize_example(row) for row in rows]
    return sorted(examples, key=lambda item: item.example_id)


def select_hotpotqa_subset(
    examples: list[HotpotQAExample],
    *,
    dataset_source: str,
    split: str,
    seed: int,
    subset_size: int = 25,
    question_type: Literal["bridge", "comparison"] | None = None,
) -> list[HotpotQAExample]:
    filtered = [example for example in examples if question_type is None or example.question_type == question_type]
    ranked = sorted(
        filtered,
        key=lambda item: (
            _stable_key(dataset_source=dataset_source, split=split, seed=seed, example_id=item.example_id),
            item.example_id,
        ),
    )
    return ranked[:subset_size]


def build_hotpotqa_fixtures(examples: list[HotpotQAExample]) -> list[BenchmarkScenarioFixture]:
    fixtures: list[BenchmarkScenarioFixture] = []
    for example in examples:
        corpus = _build_corpus(example)
        relevant_ids = _expected_relevant_ids(example, corpus)
        if not corpus or not relevant_ids:
            continue
        scope = RetrievalScope(task_id=f"hotpot:{example.example_id}")
        fixtures.append(
            BenchmarkScenarioFixture(
                scenario_id=f"hotpot_semantic_{example.example_id}",
                category=BenchmarkScenarioType.SEMANTIC_RETRIEVAL,
                retrieval=RetrievalFixture(
                    query=example.question,
                    intent=RetrievalIntent.DEBUG_OR_INVESTIGATE,
                    scope=scope,
                    top_k=min(3, len(corpus)),
                    corpus=corpus,
                    expected_relevant_ids=relevant_ids,
                ),
                baseline_applicability={
                    BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE: BaselineApplicability(
                        policy=BaselinePolicy.SKIP,
                        skip_reason="semantic-only corpus incompatible with transcript-only baseline",
                    )
                },
            )
        )
        overlap = _lexical_overlap(example.question, " ".join(item.text for item in corpus if item.item_id in relevant_ids))
        fixtures.append(
            BenchmarkScenarioFixture(
                scenario_id=f"hotpot_implicit_{example.example_id}",
                category=BenchmarkScenarioType.IMPLICIT_RECALL,
                implicit_recall=ImplicitRecallFixture(
                    query=example.question,
                    context_tokens=_tokens(example.question),
                    top_k=min(3, len(corpus)),
                    corpus=corpus,
                    relevant_ids=relevant_ids,
                    relevant_memory_texts=[item.text for item in corpus if item.item_id in relevant_ids],
                    lexical_overlap_score=min(overlap, 0.25),
                    expected_domains=[MemoryDomain.SEMANTIC],
                ),
                baseline_applicability={
                    BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE: BaselineApplicability(
                        policy=BaselinePolicy.SKIP,
                        skip_reason="semantic-only corpus incompatible with transcript-only baseline",
                    )
                },
            )
        )
        fixtures.append(
            BenchmarkScenarioFixture(
                scenario_id=f"hotpot_e2e_{example.example_id}",
                category=BenchmarkScenarioType.END_TO_END,
                routing=RoutingFixture(
                    inbound_event=InboundEvent(
                        event_id=f"evt:hotpot:{example.example_id}",
                        event_class=InboundEventClass.TOOL_RESULT,
                        task_id=f"hotpot:{example.example_id}",
                        execution_node_id=f"exec:hotpot:{example.example_id}:root",
                        solver_run_id=f"solver:hotpot:{example.example_id}",
                        payload={"question": example.question, "answer": example.answer},
                        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                    ),
                    expected_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION, MemoryDomain.SOLVER],
                    expected_blocked_domains=[],
                ),
                end_to_end=EndToEndFixture(
                    task_id=f"hotpot:{example.example_id}",
                    expect_pipeline_success=True,
                    expect_writeback_domains=[MemoryDomain.EPISODIC],
                    expect_writeback_candidate_ids=[],
                ),
            )
        )
    return fixtures


def run_hotpotqa_benchmark(
    *,
    dataset_path: str | Path,
    split: str,
    seed: int = 7,
    subset_size: int = 25,
    question_type: Literal["bridge", "comparison"] | None = None,
    output_root: str = "artifacts/benchmarks",
) -> tuple[BenchmarkRunReport, Path]:
    examples = load_hotpotqa_examples(dataset_path, split=split)
    selected = select_hotpotqa_subset(
        examples,
        dataset_source=str(dataset_path),
        split=split,
        seed=seed,
        subset_size=subset_size,
        question_type=question_type,
    )
    fixtures = build_hotpotqa_fixtures(selected) + _preflight_control_fixtures()
    report = BenchmarkHarness().run(
        fixtures=fixtures,
        config=BenchmarkRunConfig(seed=seed, run_label=f"hotpotqa-{split}"),
    )
    run_dir = write_artifacts(
        report,
        fixtures=fixtures,
        dataset="hotpotqa",
        fixture_source=str(dataset_path),
        subset_size=len(selected),
        root_dir=output_root,
    )
    return report, run_dir


def _normalize_example(row: dict[str, object]) -> HotpotQAExample:
    contexts: list[HotpotContext] = []
    for item in row.get("context", []):
        if isinstance(item, list) and len(item) == 2:
            title = str(item[0])
            sentences = [str(sentence) for sentence in item[1]]
            contexts.append(HotpotContext(title=title, sentences=sentences))
    supporting_facts = []
    for item in row.get("supporting_facts", []):
        if isinstance(item, list) and len(item) == 2:
            supporting_facts.append((str(item[0]), int(item[1])))
    return HotpotQAExample(
        example_id=str(row.get("_id") or row.get("id") or row.get("example_id")),
        question=str(row.get("question", "")),
        answer=str(row.get("answer", "")),
        question_type=row.get("type") if row.get("type") in {"bridge", "comparison"} else None,
        supporting_facts=supporting_facts,
        context=contexts,
    )


def _build_corpus(example: HotpotQAExample) -> list[RetrievalFixtureMemoryItem]:
    items: list[RetrievalFixtureMemoryItem] = []
    for index, context in enumerate(example.context):
        items.append(
            RetrievalFixtureMemoryItem(
                item_id=f"ctx:{example.example_id}:{index}",
                domain=MemoryDomain.SEMANTIC,
                text=f"{context.title}: {' '.join(context.sentences)}",
                task_id=f"hotpot:{example.example_id}",
            )
        )
    return items


def _expected_relevant_ids(
    example: HotpotQAExample,
    corpus: list[RetrievalFixtureMemoryItem],
) -> list[str]:
    support_titles = {title for title, _ in example.supporting_facts}
    return [
        item.item_id
        for item in corpus
        if any(item.text.startswith(f"{title}:") for title in support_titles)
    ]


def _stable_key(*, dataset_source: str, split: str, seed: int, example_id: str) -> str:
    raw = f"{dataset_source}|{split}|{seed}|{example_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _tokens(text: str) -> list[str]:
    return [token for token in "".join(char.lower() if char.isalnum() else " " for char in text).split() if token]


def _lexical_overlap(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return float(len(left_tokens & right_tokens)) / float(len(left_tokens | right_tokens))


def _preflight_control_fixtures() -> list[BenchmarkScenarioFixture]:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    noise_corpus = [
        RetrievalFixtureMemoryItem(
            item_id=f"tx:hotpot_noise:{index:02d}",
            domain=MemoryDomain.TRANSCRIPT,
            text=f"irrelevant note {index}",
            task_id="hotpot:control",
        )
        for index in range(1, 51)
    ]
    long_horizon = BenchmarkScenarioFixture(
        scenario_id="hotpot_control_long_horizon",
        category=BenchmarkScenarioType.LONG_HORIZON_DEGRADATION,
        long_horizon_degradation=LongHorizonDegradationFixture(
            early_retrieval=RetrievalFixture(
                query="token rotates at midnight",
                intent=RetrievalIntent.RESUME_TASK,
                scope=RetrievalScope(task_id="hotpot:control"),
                top_k=2,
                corpus=noise_corpus[:10]
                + [
                    RetrievalFixtureMemoryItem(
                        item_id="tx:hotpot_key",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="service token rotates at midnight",
                        task_id="hotpot:control",
                    )
                ],
                expected_relevant_ids=["tx:hotpot_key"],
            ),
            delayed_retrieval=RetrievalFixture(
                query="what rotation schedule applies",
                intent=RetrievalIntent.RESUME_TASK,
                scope=RetrievalScope(task_id="hotpot:control"),
                top_k=3,
                corpus=noise_corpus
                + [
                    RetrievalFixtureMemoryItem(
                        item_id="tx:hotpot_key",
                        domain=MemoryDomain.TRANSCRIPT,
                        text="service token rotates at midnight",
                        task_id="hotpot:control",
                    )
                ],
                expected_relevant_ids=["tx:hotpot_key"],
            ),
            noise_ids=[item.item_id for item in noise_corpus],
            delayed_depends_on_early_context=True,
        ),
    )
    conflict = BenchmarkScenarioFixture(
        scenario_id="hotpot_control_conflict",
        category=BenchmarkScenarioType.CONFLICT_RESOLUTION,
        conflict_resolution=ConflictResolutionFixture(
            candidates=[
                ConflictCandidate(
                    candidate_id="candidate:expired",
                    recency_rank=1,
                    validity_status="expired",
                    preferred=False,
                    timestamp=now,
                ),
                ConflictCandidate(
                    candidate_id="candidate:preferred",
                    recency_rank=0,
                    validity_status="active",
                    preferred=True,
                    timestamp=now,
                ),
            ],
            expected_winner_candidate_id="candidate:preferred",
        ),
    )
    return [long_horizon, conflict]

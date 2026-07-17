# Semantic Temporal Retrieval

Memorii separates query-time temporal relevance from memory lifecycle state.
The query asks which interval, scope, entity, and predicate are relevant. The
lifecycle policy decides whether a claim is active, historical, superseded,
expired, or invalidated. Neither policy may silently replace the other.

## Production Boundary

`QueryAnalyzer` produces a validated `QueryAnalysis` containing language,
temporal intent, entity mentions, predicate, scope, reference time, confidence,
and abstention metadata. A configured semantic analyzer can be injected through
`MemoryEvolutionService` and `ProviderMemoryService`. The conservative analyzer
is an explicit fallback: it supports safe English parsing and abstains for
unsupported or ambiguous requests.

The structured analyzer boundary accepts either a validated `QueryAnalysis` or
a JSON-like provider response. It validates model output against the server's
entity candidate catalog, rejects fabricated entity IDs, records provider/schema
failures, and returns an explicit ambiguous analysis on failure. Providers also
receive the request scope so evidence-backed named anchors cannot cross task
boundaries.

The analyzer does not select memory records. Retrieval applies the resulting
frame to candidates using lifecycle, interval, scope, entity, and provenance
constraints. Retrieval must abstain when entity or temporal resolution is
ambiguous.

## Temporal Anchors

Named anchors are evidence-backed records. Registration requires source records
to exist in the memory plane, belong to the caller's scope, and contain the
declared evidence span. Anchor names are Unicode-normalized and matched with
token boundaries. Substring matching is not authoritative, so `Q1` cannot
match `Q10`.

An anchor is not inferred from general world knowledge. If no registered source
supports a named period, the query remains unresolved.

All validity intervals use half-open semantics: `[valid_from, valid_to)`. An
observation is valid at its start and invalid at its exclusive end; interval
overlap uses strict inequalities on the two ends. This convention is shared by
claim retrieval and graph retrieval.

## Retrieval Contract

The production path is:

```text
query analysis -> candidate generation -> temporal/lifecycle filtering
-> scope/entity filtering -> deterministic ranking -> provenance or abstention
```

The benchmark simulator and oracle are not imported by production retrieval.
The runtime benchmark may align native runtime IDs to oracle labels after the
runtime decision has been produced, but it cannot alter that decision.

Provider integrations accept an explicit `reference_time`; a clock can also be
injected for deterministic runs. Retrieval therefore does not depend on an
uncontrolled wall-clock read.

`ProviderMemoryService.retrieve_evolution_decision(...)` exposes the structured
`ProductionRetrievalDecision` for machine consumers. `prefetch(...)` is only a
text adapter over that decision; it does not reimplement ranking, temporal
filtering, lifecycle filtering, or continuation selection.

## Reporting Contract

Runtime reports distinguish `execution_source` from `provider_health`.
`fake_oracle` is valid for plumbing-only dry-runs, but it is never counted as a
provider success. A checkpoint with no new extractor run is reported as
`reused_runtime_state`, rather than inheriting a previous checkpoint's source.

Graph summaries report unique final graph counts per scenario and separately
retain cumulative snapshot diagnostics. Alignment audit counts are diagnostic;
scored checkpoint verdicts remain the source of pass/fail interpretation.

## Validation Requirements

Tests must cover multilingual structured analysis, conservative fallback and
abstention, entity collisions, temporal anchor provenance, scope isolation,
current versus historical retrieval, provider clock injection, fake-provider
reporting, checkpoint source scoping, and graph aggregation scope.

Live model evaluation is scheduled or manually approved. Pull requests run
deterministic unit, lint, type, schema, no-leakage, simulator, and runtime
plumbing gates. Live evaluation records provider, model, prompt hash, and
configuration metadata and does not use retries to hide failures.

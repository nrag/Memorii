# Engineering Hardening Closure Matrix

This document is the fixed acceptance contract for the current hardening change.
It intentionally excludes overall changelist size and agent-system integration.

| ID | Severity | Required outcome | Verification |
| --- | --- | --- | --- |
| C1 | P1 | Persisted lifecycle values are typed and unknown values fail closed. | Exhaustive temporal-policy and malformed-row tests. |
| C2 | P1 | Prompt output schemas and provider transport models accept exactly the same JSON values; cross-field domain semantics run as an explicit, typed post-transport validation stage. | Prompt-to-transport parity, adversarial semantic-boundary, and runtime failure-classification tests. |
| C3 | P1 | Memory evolution is active through normal production composition. | Default-constructor integration tests. |
| C4 | P1 | The exact clean revision passes the declared live statistical gate before merge. | After a credential-free workflow-identity bootstrap on the default branch, require `Live Runtime Statistical Gate` from a manual dispatch on the PR branch, bound throughout to `github.sha`. |
| C5 | P2 | Calibration and artifact data remains typed until the JSON boundary. | Schema, round-trip, and AST boundary tests. |
| C6 | P2 | Benchmark/runtime modules have cohesive responsibilities with no relocation facades. | Dependency tests and module-size audit. |
| C7 | P2 | Architecture boundaries and production-shaped tests are enforced structurally. | Repository-wide AST boundaries and error-mode type checks across every hardening-owned runtime surface. |
| C8 | P2 | Prompt conformance fixtures do not ship in `memorii.core`. | Package-content and import-boundary tests. |
| C9 | P2 | Promotion assessment and execution have distinct, unambiguous contracts. | Public API and orchestration tests. |
| C10 | P1 | Extraction outcomes distinguish live success, partial output, abstention, provider/schema failure, and hybrid fallback; failed extraction never commits memory. | Rule/LLM/hybrid outcome tests and provider-ingestion failure tests. |
| C11 | P1 | Every public provider mutation carries a non-empty caller delivery ID and replay is idempotent across process restarts and partial-turn recovery. | Public API, restart replay, and partial-turn recovery tests. |
| C12 | P1 | Filesystem memory-plane commits are process-safe and crash-atomic; readers observe the old or new complete snapshot and corruption fails closed. | Multi-process append, failed-replace, checksum, and incomplete-batch tests. |
| C13 | P1 | Active evolution work renews a fenced lease, while abandoned work has bounded stale recovery and a terminal exhaustion state. | Process-safe CAS, reopen/corruption, slow extraction/projection/commit, lost-acknowledgement recovery, token fencing, stale recovery, and exhaustion tests. |
| C14 | P2 | Provider ingestion, retrieval composition, tool dispatch, and work-state projection have explicit owners instead of a monolithic facade. | Component behavior tests plus module- and handler-size architecture budgets. |

The change is complete only when every row has implementation coverage and the
exact reviewed tree passes lint, typing, warning-as-error unit tests, packaging,
artifact validation, deterministic dry runs, and the declared live statistical
gate without post-run prompt or threshold tuning.

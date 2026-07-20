# Engineering Hardening Closure Matrix

This document is the fixed acceptance contract for the current hardening change.
It intentionally excludes overall changelist size and agent-system integration.

| ID | Severity | Required outcome | Verification |
| --- | --- | --- | --- |
| C1 | P1 | Persisted lifecycle values are typed and unknown values fail closed. | Exhaustive temporal-policy and malformed-row tests. |
| C2 | P1 | Prompt output schemas and consuming domain models accept exactly the same values. | Prompt-to-domain schema parity tests. |
| C3 | P1 | Memory evolution is active through normal production composition. | Default-constructor integration tests. |
| C4 | P1 | The exact clean revision passes the declared live statistical gate. | Revision-bound live reports and certificate. |
| C5 | P2 | Calibration and artifact data remains typed until the JSON boundary. | Schema, round-trip, and AST boundary tests. |
| C6 | P2 | Benchmark/runtime modules have cohesive responsibilities with no relocation facades. | Dependency tests and module-size audit. |
| C7 | P2 | Architecture boundaries and production-shaped tests are enforced structurally. | Repository-wide AST and type-check tests. |
| C8 | P2 | Prompt conformance fixtures do not ship in `memorii.core`. | Package-content and import-boundary tests. |
| C9 | P2 | Promotion assessment and execution have distinct, unambiguous contracts. | Public API and orchestration tests. |

The change is complete only when every row has implementation coverage and the
exact reviewed tree passes lint, typing, warning-as-error unit tests, packaging,
artifact validation, deterministic dry runs, and the declared live statistical
gate without post-run prompt or threshold tuning.

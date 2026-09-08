# Package 3: Independent Statistical Evaluator

- Parent WorkPlan: `docs/work/semantic_ingestion/engineering-closure/implementation.plan.md`
- Status: blocked on acceptance-authority design; numeric component approved
- Requirements: R05, R06, R14

Implement frozen coverage and independent recomputation without inventing
thresholds or policy values. The serialized numeric contract is pending linked
design `docs/work/semantic_ingestion/statistical-acceptance/design.plan.md`.
The earlier rejected designs remain historical evidence. The new proof separates
preverified coverage/sampling context from parsed policy and candidate results.
All three independent reviewers approved numeric candidate
502306dc39b966bf13ec261f1f81a6fb59e867816f2f889f491c0ac0037eb9da.
Its closure.md records 76 tests, 33 independent vectors and eight mutation
rejections. This is component design evidence, not implemented R14 acceptance.

## Implementation Evidence

The root `acceptance/` package now contains the approved bounded arithmetic and
strict certificate evaluator/verifier. Coordinator AST comparison establishes
that both ports preserve the reviewed executable bodies; only imports,
formatting, and module description changed. Its CTV encoder is acceptance-owned,
so the package has no production semantic/helper import. The independent math
checker reproduced 33 vectors and rejected eight mutations using the ported
kernel. The final bounded port has 81 focused passing tests and all three reviews,
recorded in the parent's numeric-port-review.md. Tests run from the same `memorii/` working directory as
the repository test jobs, after adding the repository root to pytest's explicit
development search path. Production wheel package discovery remains `memorii*`.

The public evaluator still requires independently constructed held context.
It is not a complete acceptance CLI. Baseline approval requires the linked
`../../acceptance-authority/design.plan.md` prerequisite; the coordinator rejected
its initial proposal as under-specified rather than sending open design choices
to reviewers. No canonical schema or generated authority has been promoted.

## Next Action

Resolve the linked authority design's issue-time, bounded byte-entry and closed
shape obligations before canonical promotion and full acceptance-owner assembly.

The authority reconstruction's one conformance verification did not converge;
its declared budget is exhausted. `../../acceptance-authority/review.md` records
the exact rejected candidate and required successor scope. This does not revoke
the independent numeric component approvals or require real production signing.

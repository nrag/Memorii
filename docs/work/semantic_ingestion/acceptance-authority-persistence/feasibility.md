# Feasibility Evidence

## Repository Publication Primitive

`memorii/memorii/tools/semantic_ingestion_release_persistence.py` implements the
same required transaction topology for another semantic-ingestion authority:
content-addressed immutable objects, an advisory replaceable index, an
independent append-only monotonic fence, predecessor CAS, exact idempotent
retry, and startup reconciliation when the index and fence differ. The
acceptance package cannot import that production tool, but can implement the
same documented port and state machine independently.

`memorii/tests/unit/tools/test_semantic_ingestion_release_persistence.py`
exercises atomic publication, gaps and rewinds, torn state, lost
acknowledgement, interruption before index replacement, predecessor CAS,
rollback-as-a-later-transition, corrupt/mixed inventory, symlink rejection,
external-fence failure, and concurrent publication. This discriminates the
accepted external-fence design from independent JSONL histories that infer a
latest record.

## Installed Runtime Primitive

The dirty Stage 1 candidate packages `acceptance`, installs
`memorii-acceptance-evaluate`, discovers exactly one provider in
`memorii.acceptance_evaluator_runtime`, and rejects invalid provider counts and
protocols. Its CLI exposes candidate artifact inputs but no key, history,
limit, clock, issuer, or approval override. This establishes the entry-point
mechanism is feasible; it does not establish a real configured host provider.

## Acceptance Isolation And Canonical Encoding

`acceptance/ctv.py` supplies an acceptance-owned canonical-map encoder and the
acceptance package contains no production import. The current Stage 1 digest
helper is a prototype and does not yet implement the accepted complete-profile
length-prefixed digest/signature construction. The design deliberately records
that as implementation remediation rather than treating the prototype bytes as
registered authority.

## Reproduced Command

On 2026-09-12, Python 3.12 ran:

```text
.venv/bin/python -W error -m pytest -q
  memorii/tests/unit/tools/test_semantic_ingestion_release_persistence.py
  memorii/tests/unit/acceptance/test_acceptance_evaluator_runtime.py
  docs/work/semantic_ingestion/acceptance-issuance-prefix/test_issuance_prefix_feasibility.py
  docs/work/semantic_ingestion/acceptance-authority-successor/test_authority_successor_feasibility.py
  memorii/tests/unit/acceptance/test_statistical_certification.py
```

Result: 191 passed in 16.03 seconds. Ruff passed for the dirty Stage 1
acceptance, production bridge, and focused test surfaces. These results are
local feasibility evidence from a dirty tree. They are not clean-head, CI,
independent reproduction, operational acceptance, or release evidence.

## Discriminating Outcome

The repository already contains a verified implementation pattern for the
required crash/recovery semantics and a working installed entry-point pattern.
No new database or caller-configured authority mechanism is required. Stage 1
can proceed by implementing the approved state machine independently inside
`acceptance`, then promoting its closed schema authority and installed gate.

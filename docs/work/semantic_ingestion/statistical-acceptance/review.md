# Frozen Numeric Design Review

Candidate: d4e49ab48ca0eee266ee7157088e71b4edfc66bf942493c7cab30b2f6de9ec4f.
All three standard reviewers verified its manifest and reviewed the bounded
component. All returned changes required, without a demonstrated production
P1/P2 claim. Coordinator reconciled all findings before editing.

| Finding | Classification | Coordinator disposition | Correction |
| --- | --- | --- | --- |
| Spec: expanded output map before cap | Not applicable / changes_required / verification-operability | confirmed, contract conformance | Traverse typed certificate fields for byte counting; expand only after cap; instrument both materialization and encoding |
| Spec: exact Pyright invocation absent | Not applicable / changes_required / verification | confirmed, evidence action | Record interpreter-bound exact command and rerun |
| Correctness: alpha-one endpoint contradiction | Not applicable / changes_required / architecture | confirmed documentation ambiguity, no kernel defect | Explicit CP and fixed-range endpoint precedence; alpha-one endpoint vectors |
| Tests: full-domain fallback passes numerical checks | Not applicable / changes_required / verification | confirmed, evidence action | Independent fixed-step CP oracle, meaningful Hoeffding precision cases and public bound checks; widened-result mutation rejection |
| Tests: incomplete transport/parser negatives | Not applicable / changes_required / verification | confirmed, evidence action | Exact/over cap per stream, duplicate keys, evidence shape and numeric grammar families through public verifier |
| Tests: locator encoder can be replaced self-consistently | Not applicable / changes_required / verification | confirmed, evidence action | Literal canonical locator vectors and public Holm ordering |

This is one coherent conformance/evidence correction batch, not product-semantic
remediation. Public lower-any-failure is explicitly unsupported by the safety
policy boundary; lower CP mathematics is tested at the kernel boundary instead.
Hoeffding overlap may legitimately stop early, so precision tests choose robust
cases and separately retain overlap tests rather than demanding unsafe narrowing.

Exact coordinator verification commands, from repository root:

```text
PYTHONPATH=memorii:docs/work/semantic_ingestion/statistical-acceptance .venv/bin/python -W error -m pytest docs/work/semantic_ingestion/statistical-acceptance -p no:cacheprovider -q
.venv/bin/pyright --project docs/work/semantic_ingestion/statistical-acceptance/pyrightconfig.json --pythonpath .venv/bin/python
.venv/bin/ruff check docs/work/semantic_ingestion/statistical-acceptance
PYTHONPATH=memorii:docs/work/semantic_ingestion/statistical-acceptance .venv/bin/python docs/work/semantic_ingestion/statistical-acceptance/run_boundary_evidence.py
PYTHONPATH=memorii:docs/work/semantic_ingestion/statistical-acceptance .venv/bin/python -O docs/work/semantic_ingestion/statistical-acceptance/run_boundary_evidence.py
```

Status: corrections implemented and coordinator-verified; targeted reviews pending.

Successor evidence: 76 focused tests pass in 5.20s. Independent checker passes
33 vectors and rejects eight mutations. A no-write substitution of full-range
inverse bounds causes all three public precision cases to fail, closing the
removed-bisection blind spot. The old exact CP endpoints remain unchanged and
are now documented and tested at alpha one.

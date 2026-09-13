# Observation Ledger Integration Verification

Work type: testing. Status: active.
Parent: ../observation-ledger/implementation.plan.md; bounded packet
../observation-ledger/milestones/activation.plan.md. Related preparation testing:
../activation-deployment-tests/testing.plan.md (its CAS exclusion is preserved).
Root owns all tests/workflows/processes. No product semantics changed here.

## Contract And Topology

The public trusted-host activation method must preserve draining, full-write CAS,
complete native inventory, exact repeated recovery and historical storage. The
feature-local suite grew to include real JSONL and fresh-process recovery, so it
belongs in one dedicated integration job, never the fast unit shards. Existing
provider/atomic/admission unit owners remain unchanged. No test is removed.

Baseline HEAD191826cd3afb38bf605a337a71d576063b3bae5e, authorized dirty tree;
Python3.12.14 locally, Python3.11 ubuntu in CI. Current package-smoke owns deployed
artifact verification; it does not execute ledger activation. The new job selects
only tests/integration/test_observation_ledger_activation.py. No overlap with unit
shards or package-smoke. The Unit Tests aggregate requires this job's success.

## Matrix

| Family | Observable defect signal | Level / owner |
| --- | --- | --- |
| Explicit public trigger and target substitution | Configuration writes nothing; invalid target rejects before mutation | Integration file / dedicated activation job |
| Drain and complete old work | Held public operation stays intact, new old work refuses, old work completes, two native terminal inventories match independent ordered digest | Same, real JSONL/barrier |
| Full snapshot race and finite exhaustion | Unrelated root write loses CAS; no partial trio; bounded rescans | Same, real root batches |
| Equivalent concurrent activation | Both cutover seams and competing drain CAS recover one successor | Same, public API/JSONL |
| Before/after commit interruption | Restart sees all old or all new authority; retry and fresh-process decode give one trio | Same, real JSONL plus subprocess |
| Retired write routes | Ordinary, conditional, UOW and atomic writes reject unchanged state | Same, existing governed policy |
| Historical records and inventory | Original JSONL batch bytes and non-admission records unchanged; missing native member rejects | Same, captured fixture/native loader |

Test reviewer completed the baseline matrix audit. Its missing-test findings are
classified Not applicable/changes_required/verification evidence actions; only
the demonstrated concurrent stale-admission defect is P2. Consolidated corrections
cover public live drain, durable failure/restart, conditional route, historical
bytes, and two native closures. The final candidate receives targeted test review.

## Evidence And Budget

Initial compatibility run:241passed541.44s including16 activation cases. Expanded
activation construction:21passed87.76s. Final corrected integration:24passed218.82s,
retained in final-integration.log and activation-results.xml. CI timeout10min preserves margin;
no CI run or runtime parity claim until observed. Root records final logs and
hashes in ../observation-ledger/activation-evidence/. Preparation-wheel source
pins must be refreshed by the implementation operation before release closure.

## Next Action

Reconcile the evidence-only review correction against the frozen 24-case result
and close the bounded coverage/topology review; CI execution remains unobserved.

## Accepted Preimage And Intent Extension

The same dedicated job now also selects test_observation_ledger_artifacts.py
and test_observation_terminal_intent.py. These publication/captured-codec cases
belong in integration, not fast unit shards. No prior case was removed. The
new set covers exact binding/body LP framing, native ordinary digest retention,
new source-intent/receipt shapes and historical omission/round-trip behavior.
Activation24-case results remain baseline evidence; the expanded 34-case gate
passed locally in228.84s. This is not CI execution or current-candidate closure.

The same job now includes `test_observation_ledger_replay.py`: registered full
prefix/expected-head checks, immutable-result callback failure propagation,
genesis, missing/extra/reordered/duplicate entries, source/group membership,
and protected per-artifact/whole-prefix resource rejection. These exercise
real publication and native decoding; they remain integration-level evidence.
They do not substitute for native atomic caller/result-join/reopen tests.
Twelve focused cases passed21.77s before the additional whole-prefix ceiling
case; the final combined gate will record the complete current count/runtime.

The replay suite now has14 passing cases in28.47s; the combined pre-group gate
passed48 cases in266.93s. Native audit construction adds one real provider-commit
case (45.68s), and registered cursor construction adds one case (5.60s) covering
independent public-key verification and malformed/over-limit inputs. Both are
selected by the same dedicated job and recorded in path-to-gate.json. No fast
unit or package-smoke selection changed. This remains moving-candidate local
construction evidence; final combined timing, activated atomic caller proofs,
and GitHub execution are pending.

The 50-case construction gate passed307.70s. Two additional integration paths
now exercise registered native projection evidence and graph paging mechanics:
`test_native_projection_evidence.py` and `test_graph_observation_paging.py`.
They pass together2 cases13.90s and are included in the same dedicated PR job
(52 collected cases). The latter uses a typed fixture cohort provider and does
not establish production retrieval selection. Two isolated recovery-entry join
regressions live under the normal unit tree; they do not duplicate activation
or full registered replay tests. The final expanded gate passed52 cases306.79s in
`../observation-ledger/append-evidence/integration-paging-candidate.log`.
GitHub and activated transaction proof remain open.

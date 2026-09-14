# Source Consultation Reconciliation

The initial cohort was downgraded to source consultations after the coordinator
updated the unpinned gate inventory during gate execution. Product, test,
workflow and current-state document hashes remained unchanged. This is a
confirmed governance/evidence action: freeze all current ledgers and evidence
before formal approval. No consultation claims approval or parent M5 closure.

Coordinator inspected the cited canonical steps and current implementations.
Confirmed corrections, one bounded invariant batch:

| Concern | Classification | Disposition and evidence |
| --- | --- | --- |
| Zero-score lexical candidates returned for no match | P2 / changes_required / runtime | Independently reproduced; filter positive matches, both-root no-match proof. |
| Channel missing from lexical admission ordering | P2 / changes_required / runtime | Step 6 vs index sort; channel then score/ID, exact shared-cap proof. |
| Canonical no_lifecycle_valid_match becomes abstention | P2 / changes_required / runtime | Canonical retrieval.py explicit state vs adapter branch; exact no-match and ambiguity outputs. |
| Claim/evidence cross-list duplicates charged twice | P2 / changes_required / runtime | Step 8 requires one deduplicated unit; union identity accounting and exact boundaries. |
| Structured sources bypass lifecycle/nonempty provenance closure | P2 / changes_required / provenance | Correctness reviewer reproduced expired raw source release and ungrounded-claim ValidationError; common current-readable dependencies with frame-sensitive historical claim selection retained. |
| Owned decode before provenance exclusion | P2 / changes_required / availability | Steps 3/4 require closure first; unrelated valid mandatory content must survive excluded malformed candidate. |
| Grant whitespace IDs accepted | Not applicable / changes_required / contract conformance | Explicit provision nonblank requirement; determinate validation correction, no invented product priority. |
| Missing exact real-root request labels/schema/revision/backend/structured snapshot assertions | Not applicable / changes_required / verification | Already required matrix evidence; bounded integration assertions, not new product defects. |

Duplicate reviewer findings are clustered above, not separate remediation rounds.
No P1 finding. P2 cases are important supported retrieval edge cases, not claims
about measured prevalence. Reviewers found no mainstream failure requiring P1.

Record-only: per-omission-row ID cap is finite and follows the typed omission
contract; aggregate scope is not explicit, so no invented aggregate semantic
change. Three-second event barrier timeout is a P3 reliability follow-up;
ordering itself is deterministic and is not changed in this corrective batch.

Sole Terra worker scoped_remediation owns only an isolated copy under
/private/tmp/scoped-context-remediation. Original candidate remains unchanged
while initial broad gates finish. Coordinator will inspect/import its bounded
files, rerun affected evidence and freeze a complete formal review candidate.
This is construction completion after consultation, not an approved milestone.

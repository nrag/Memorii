# Source Finalization Debugging Closure

Status: complete for native source-finalization codec, CAS, recovery and historical
terminal compatibility only. Parent R17, M5 and semantic ingestion remain incomplete.

Candidate: `source-candidate.json`, SHA-256
89907b04b2a9888ad6b708c859c3db1bde359dfb029dc24eed03a7780b80c9a5.
HEAD 191826cd3afb38bf605a337a71d576063b3bae5e with authorized dirty changes.
Seven production hashes are unchanged from the candidate approved by independent
spec and correctness reviewers. The targeted test reviewer approves the three-file
verification delta and closes all four required evidence actions.

Root cause: terminal persistence selected generic semantic-contract encoding for
a source observation whose declared wire grammar uses the native atomic-member
codec. The resulting exception became durable retry before any terminal CAS.
The corrected selector preserves existing member bytes. Explicit V1 lowering and
codec initialization retain genuine historical terminal bytes without fabricated
observations. Store-side checks bind the new observation to server-derived
identity, predecessor/successor, result and schema.

Evidence retained in this directory:

- `capture.log` / `codec-fixed.log`: same public reproducer fails then passes.
- `recovery-roots.log`: 22 recovery/restart/normal-root cases pass.
- `codec-regression.log`: 75 codec/evidence-arena/builder cases pass.
- `assembly-contracts.log`: 18 assembler/record checks pass.
- `zero-group.log`: failed-first-group finalization passes.
- `public-boundary-initial.log`: actual same-CAS membership plus four authority-loss
  cases pass; two fixture setup failures are preserved honestly.
- `persisted-public-check.log`: both persisted corruption/reopen cases pass; historical
  environment mismatch is preserved and explained in the debugging plan.
- `historical-public-environment.log`: genuine V1 public replay and duplicate-package
  negative both pass; no normalization/graph re-execution or audit synthesis.
- `identity-final.log`: final identity command exits zero; three changed tests pass Ruff.

remaining_validated_p1_p2: []
remaining_required_evidence_actions: []
remaining_required_contract_conformance_actions: []

No CI, full branch, complete observer, statistical certification or operational
release approval follows from this slice. New V2 publications require readers
with the explicit new grammar; historic V1 bytes retain their old meaning. Group
observations, authenticated query/comparison and final host closure remain parent
work. The isolated fixture's captured installed-package identity is reconstructed
only in the test; real version, byte, profile and admission checks remain active.

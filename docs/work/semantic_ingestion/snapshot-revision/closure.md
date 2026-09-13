# Full Write Snapshot Closure

Status: complete for the bounded memory-plane primitive. Parent observation
ledger and semantic ingestion closure remain partial.

Candidate file-map digest:
`e84b6eaae5242b5cc94d7e032675b558993f30fc079833112ef20f6439514ea3`.
Exact four source hashes, commands, results and exclusions are in candidate.json.
The tree is authorized and dirty at HEAD
`191826cd3afb38bf605a337a71d576063b3bae5e`; no commit or hosted CI claim.

The canonical memory-plane service and both built-in backends now expose a
detached full-write snapshot and an optional full-write CAS guard. Internal
control writes invalidate this token even when runtime-data revision is
unchanged. JSONL reuses its existing persisted batch counter. Existing data
revision, old conditional-call signatures when the option is absent, and
historical storage bytes are preserved. Speculative units of work reject the
root-only capability; actual nonempty commits advance the underlying token.

Evidence: initial combined new/compatibility suite 54 passed in 6.85s. After
adding the requested successful dual-guard case, the final focused suite has
19 passing tests in 1.07s. Production files are unchanged between runs. Ruff,
Pyright, whitespace and final identity hygiene pass. Tests cover stale guards,
control/data/empty root batches, failure atomicity, detached records, service
forwarding, UOW boundaries, durable restart, two-instance contention and failed
atomic file replacement.

Independent specification and correctness reviews approve this bounded scope;
independent test review confirms the required positive evidence gap is closed.
Two suggested product defects were withdrawn after coordinator inspection of
actual authority callbacks and empty UOW semantics. Neither justified changing
existing production behavior. The test gap was an evidence action, not P2.

remaining_validated_p1_p2: []
remaining_required_bounded_evidence_actions: []

This does not implement ledger activation, global append, checkpoint publication
or authenticated retrieval. Those remain in the parent design/implementation
flow. The new operational profile direction is approved, but its full registry
publication and ledger design still require completion and review. Production
signatures, external acceptance authority and whole-branch CI are separate.

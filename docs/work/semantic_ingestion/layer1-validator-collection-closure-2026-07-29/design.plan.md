# Layer 1 Validator Collection Grammar Closure

- Work ID: semantic-ingestion-layer1-validator-collection-closure-2026-07-29
- Work type: design
- Status: complete
- Coordinator: Codex main thread
- Created: 2026-07-29
- Last updated: 2026-07-29
- Parent WorkPlan: `docs/work/semantic_ingestion/implementation.plan.md`
- Related WorkPlans: `docs/work/semantic_ingestion/m0a-c2-layer1-ctv-bindings-2026-07-28/design.plan.md`
- Canonical inputs: `docs/design/semantic_ingestion_architecture.md` SHA-256 `67bf2620a0379761853861e416efba0816045ef4bf88e4808e701a9ac3bc993e`; `docs/design/semantic_ingestion/traceability_registry/registry-v1.json` SHA-256 `38c45adcba41222361ce9c34a65c04eb5dbcb32b94e9432825b6e33a19915692`; checked authority SHA-256 `89a98fc1e545f38c234ce42dbd164c85e3ddc6358856cca70e59dad7b1addc7b`
- Expected outputs: corrected design-side validator SHA-256 `538a01f1a37772b71b224cb4d1456509f0644850eb7ebbc67a64374f4a3d13fc`, checker SHA-256 `2ca3da2c69b453e2107ab4e901345b4b5420288666561c566732849d56c811c1`, atomic-publication and tuple-boundary evidence, an updated static-tooling pin, and an independent design-review disposition

## Objective

Make the design-side CTV v2 validator enforce the already closed collection
grammar: `list`, `set`, and `frozenset` have exactly one item; `tuple` has
finite items or exactly `tuple[T, ...]`. The correction must reject invalid
forms before authority publication and preserve the frozen design, registry,
checked authority, and checker bytes.

## Completion Contract

This design correction is complete only when the validator rejects each invalid
collection shape through its own self-test, accepts and normalizes every
authorized sibling form, reproduces the committed authority byte-for-byte, and
the deterministic checks below pass. A fresh independent `$review-design`
delta/full review must classify the correction with no confirmed
`blocks_approval` or `changes_required` finding in this bounded scope.

## Scope

Included:

- invariant-level collection arity and ellipsis validation in the design-side
  validator;
- direct and declarative-alias mutation evidence derived from the frozen
  architecture;
- quoted type-position, nested, inherited, and unprojected mutation evidence;
- same-directory atomic authority publication and deterministic failure evidence;
- checker allowlist enabling only the stdlib imports required by the approved
  atomic-publication and concurrency owner;
- the documented validator pin in `docs/development/static_tooling.md`;
- this linked design WorkPlan and checksum/evidence records.

Excluded:

- changes to the frozen architecture text, registry, authority bytes, reference
  compiler, implementation tests, CI workflow, or production code;
- broad parser refactoring, new collection kinds, or changed normalized-output
  representation.

Deferred:

- implementation-side equivalent-rejection evidence and PR enforcement remain
  owned by the parent implementation milestone.

## Constraints And Invariants

- Source precedence is `AGENTS.md`, then the approved architecture, then this
  WorkPlan; this WorkPlan does not amend collection semantics.
- Collection validation applies to direct, quoted, nested, inherited, and
  declarative-alias type positions, so one syntax path cannot bypass the
  closed grammar. Literal/default/Field metadata strings remain data.
- On failure before replacement, validator `--write` leaves an absent target
  absent or a pre-existing target byte-identical. It writes exact validated
  bytes to a same-directory temporary file, flushes/fsyncs it, replaces
  atomically, then fsyncs the directory where supported. A post-replace
  directory-fsync error may report failure after the new complete bytes are
  visible; rollback is not claimed for that already-visible publication.
- The checked authority boundary permits the historical static validator imports
  plus exactly `errno`, `os`, `tempfile`, and `threading`, required by the
  approved atomic-publication and concurrency owner. All other import and audit
  isolation checks remain unchanged.
- The correction is design tooling, not a production API or compatibility
  change. Existing valid authority must remain byte-identical.
- Design-side and independent implementation authorship remain separate; this
  work neither imports nor inspects the reference compiler.

## Sources Of Truth

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. `docs/design/semantic_ingestion_architecture.md`, Section 3.23.4.2.1 and
   its closed projection/declaration grammar
6. `docs/design/semantic_ingestion/traceability_golden_vectors/validate_ctv_binding_authority_v2.py`
7. `.agent/PLANS.md` and `.agent/skills/build-design/SKILL.md`
8. Parent implementation WorkPlan round-4 findings

## Current State

Verified facts:

- The frozen validator previously normalized `list[str, int]` as a collection
  and treated `tuple[..., str]` as variadic, despite the architecture’s closed
  collection grammar.
- The independent implementation compiler rejected both probe cases; the
  mismatch is a design-authority verification gap, not permission to weaken
  implementation fail-closed behavior.
- Before this correction, the design, registry, authority, validator, checker,
  and profile hashes are respectively `67bf2620...`, `38c45adc...`,
  `89a98fc1...`, `f0f74bc...`, `bc31ed0d...`, and `20edd38a...`.

Interpretation:

- The normative behavior is already determinate. The smallest correction is
  shared syntax-level collection validation invoked by both alias validation
  and normalization, not a new design semantic.

## Assumptions And Open Questions

Verified facts: finite tuple item lists are normalized positionally; the only
ellipsis form is `tuple[T, ...]`; list/set/frozenset do not admit ellipsis.

Working assumptions: `tuple[()]` remains a finite zero-item tuple if accepted
by the pre-existing static declaration language; this correction does not add
or remove that unrelated syntax.

Unresolved questions: none.

Decisions requiring external input: none.

## Requirements Ledger

| ID | Required behavior | Acceptance evidence | Status |
| --- | --- | --- | --- |
| VLC-001 | List/set/frozenset require one non-ellipsis item | Direct, quoted-child, nested, alias, inherited, reachable, and unprojected invalid mutations reject | approved |
| VLC-002 | Tuple permits finite items or exactly native `tuple[T, ...]` | Direct/whole-quoted/nested/alias/inherited tuple quoted-child variants reject; `tuple[()]`, finite, and native variadic forms normalize | approved |
| VLC-003 | Valid baseline authority remains stable | Canonical checker starts with `python3.12 -I`; the isolated gate materializes its already captured checker bytes in clean scratch and proves the actual non-isolated entry exits `1` with empty stdout and the exact diagnostic before parsing; sibling-shadow, snapshot, exact audit-path, and two-replica proofs remain | approved |
| VLC-004 | Failure cannot publish authority | Complete publication matrix preserves absent/seeded bytes and modes; explicit `int | None` state retains the seeded-mode assertion and scoped Pyright reports 0/0/0. Parent owns public CLI matrix | approved |

## Milestones

### D1 - Correct closed collection grammar

- Purpose: align validator behavior with existing Section 3.23.4.2.1 grammar.
- Bounded scope: validator helper, type-position enforcement, self-test
  mutations, and static-tooling validator pin only.
- Expected artifacts: updated validator, static-tooling pin, and this WorkPlan.
- Verification: validator self-test; temp write/check; syntax/lint/type checks;
  identity comparison; diff check.
- Status: complete; replacement round-10 three-role review approved the frozen candidate.

## Evidence Log

| Evidence | Result | Maturity |
| --- | --- | --- |
| Parent round-4 review and black-box probes | Confirmed invalid `list[str, int]` and `tuple[..., str]` acceptance | specified gap |
| Architecture Section 3.23.4.2.1 and closed projection grammar | Closed collection semantics; no policy invention required | specified |
| Validator `--self-test` after correction | Passed: authority `89a98fc1...`, 56 schemas, 240 enum rows, profile `20edd38a...` | locally verified |
| Round 1 validator SHA-256 | Intermediate candidate `221f9e2c...`, superseded by DREV-001 remediation; design, registry, authority, checker, and profile identities remained unchanged | superseded evidence |
| Scoped Ruff, Pyright, `py_compile`, and `git diff --check` | All passed; Pyright reported zero errors/warnings/information | locally verified |
| Delta 1 review | DREV-001 through DREV-003 confirmed; immutable report preserved | reviewed |
| Round 2 self-test | Passed after context-aware quoted type validation: authority `89a98fc1...`, 56 schemas, 240 enum rows, profile `20edd38a...` | locally verified |
| Round 2 validator identity | Intermediate candidate `128bf582...`, superseded by DREV-004 final classifier remediation | superseded evidence |
| Round 3 validator identity | Validator SHA-256 `3d5e215de91481a1c549f7cc9e753dfa193a9d31e814fc69ce3f562d941e5bff`; design, registry, authority, checker, and profile identities unchanged | locally verified |
| Final round-2 gates | Exact checker passed with two replicas; Ruff, Pyright, `py_compile`, report validation, and `git diff --check` passed | locally verified |
| Final round-3 gates | Validator self-test, exact two-replica checker, Ruff, scoped Pyright from `memorii/`, `py_compile`, both immutable report validators, and `git diff --check` passed | locally verified |
| Additional revision 9 candidate | Validator SHA-256 `538a01f1a37772b71b224cb4d1456509f0644850eb7ebbc67a64374f4a3d13fc`; checker SHA-256 `2ca3da2c69b453e2107ab4e901345b4b5420288666561c566732849d56c811c1`; authority unchanged | approved by replacement round-10 review |

## Decision Log

| Date | Decision | Alternatives considered | Evidence and rationale | Consequences |
| --- | --- | --- | --- | --- |
| 2026-07-29 | Enforce arity/ellipsis in one syntax helper called by alias validation and normalization | Correct only normalizer; add per-case branches; amend architecture | Alias and direct declarations are both closed design inputs; one helper prevents a bypass | Invalid reachable and unreachably declared aliases reject consistently |
| 2026-07-29 | Preserve valid authority bytes | Regenerate/repin authority | Authority contains only valid existing declarations; the correction changes rejection behavior only | Registry, authority, checker, design, and profile identities should remain unchanged |
| 2026-07-29 | Parse quotes only in annotation/alias type positions | Parse every string; leave quoted annotations opaque | Delta DREV-001 proves type-position strings are executable declaration syntax, while Literal/default/Field strings are data | Closed grammar applies without corrupting data-string semantics |
| 2026-07-29 | Repin only static tooling in this design round | Modify workflow/tests/parent plan | DREV-002 directs documented design handoff first; workflow and black-box consumers are implementation-owned | Exact checker can verify this reviewed validator; coordinated implementation repin remains pending |
| 2026-07-29 | Treat ellipsis as native punctuation and Field as metadata/data only | Accept quoted ellipsis; permit Field in generic type grammar | DREV-004 proves raw shape validation alone leaves quoted ellipsis and Field-as-type bypasses | Every collection child uses the closed type classifier; only native position-two tuple ellipsis is skipped |
| 2026-07-29 | Publish validated authority through same-directory atomic replacement | Direct target write; validate after publication; cross-directory temporary file | DREV-005 proves direct writes can truncate the trusted target. Same-directory temporary write/flush/fsync/replace prevents partial reader visibility | Pre-replace failures preserve absent/seeded targets; directory-fsync failure can occur after complete new bytes become visible and is surfaced without a false rollback claim |
| 2026-07-29 | Treat `tuple[()]` as a finite zero-item tuple | Reject the syntax; add a new empty-tuple meaning | Existing closed AST normalization already maps it to zero ordered items and the WorkPlan recorded that interpretation | Explicit positive normalization proof closes the documented boundary without changing grammar |
| 2026-07-29 | Extend the checker boundary only for authority publication and self-test paths | Remove atomic behavior; allow an unrestricted temporary root; bypass the hermetic checker | The checker needs the four stdlib modules plus only the authority parent, its direct `.authority.json.*.tmp` sibling, and a validator-owned `.authority.json.self-test.*` subtree. The exact checker then passes two hermetic replicas. | Runtime file audit remains closed to every other path; validator/checker identities changed together and static tooling pins both. |
| 2026-07-29 | Preserve only access-mode permissions across replacement and create absent targets as `0644` | Preserve broad metadata; retain `mkstemp` `0600`; leave creation subject to umask | DREV-009 establishes an existing authority's regular-file access mode as compatibility-relevant. Applying only `st_mode & 0o7777` after the complete temporary write/flush and before file fsync is the narrowest compatible correction; `0644` matches the prior regular-file creation behavior deterministically. | The temporary inode remains private `0600` while partial bytes exist. Ownership, timestamps, ACLs, xattrs, and non-regular targets are deliberately outside this bounded correction; resolved symlink targets preserve their regular target mode. |
| 2026-07-29 | Classify unsupported directory open and fsync equivalently | Treat every post-replace sync error as failure; hide real I/O error | The `where supported` contract applies to `EINVAL`, `ENOTSUP`, and `EOPNOTSUPP` at either directory-open or fsync. All other errors still surface after the complete target is visible. | Retry semantics remain explicit: unsupported durability enhancement succeeds; real post-replace failure raises without rollback. |
| 2026-07-29 | Execute replicas only from captured source bytes | Copy named source paths after hash verification; keep final path rereads | DREV-011 proves a verified path can change before later `copyfile` materialization. The checker now validates one snapshot and its sole materialization owner receives only those bytes. | Content-addressed evidence no longer relies on path stability after capture; the checker self-hash remains a single capture. |
| 2026-07-29 | Prove audit isolation with an import-valid undeclared-read probe | Rely on positive replicas; widen audit allowlist | DREV-012 requires a negative known answer. A probe derived from the captured validator adds no import, recomputes its local identity, and fails at the real bootstrap audit before authority mutation. | The audit boundary is exercised without altering production validator behavior or allowlists. |
| 2026-07-29 | Require interpreter isolation before checker imports through the canonical `-I` command | Depend on an in-process guard alone; add a wrapper; trust the checkout directory | DREV-013 establishes that imports precede checker code and self-hash validation. The canonical command supplies `-I`; the early main guard gives a clear diagnostic only after imports have completed. A same-directory `hashlib.py` known answer proves the isolated child excludes the shadow. | The security boundary is the reviewed `python3.12 -I` invocation plus the external checker hash. Non-isolated clean invocation is rejected, but the runtime guard is not claimed to prevent a module that executed before it. |
| 2026-07-29 | Bind the audit negative known answer to one exact resolved path | Accept a generic denial phrase; seed a different path | DREV-014 shows an unrelated denial could satisfy generic evidence. The checker now seeds `root/undeclared-probe.txt`, injects that exact resolved path, and requires the complete matching diagnostic. | Import set, checked authority, and owned temporary state remain unchanged while unrelated denials cannot satisfy the assertion. |
| 2026-07-29 | Exercise the actual captured checker entry for clean non-isolated rejection | Keep the substitute startup probe; reread `__file__`; recursively launch the full positive gate | DREV-015 requires revision-bound evidence for the executable entry itself. Main passes its already captured and hash-verified checker bytes to a clean scratch owner; the copied checker runs without `-I` and must fail at the guard with exit `1`, empty stdout, and exact stderr. | The positive isolated gate certifies its own negative entry behavior without source rereads, shadow adjacency, argument parsing, or authority processing. |
| 2026-07-29 | Model seeded publication mode as explicit optional state | Delete the seeded-mode assertion; silence Pyright with a cast | DREV-016 identifies only static branch correlation, not a runtime defect. `initial_mode: int | None` is initialized before branching and the seeded branch fails if it is unexpectedly absent. | The mode assertion remains behaviorally identical while scoped Pyright closes at 0/0/0. |

## Review Log

| Round | Reviewers | Findings and disposition | Resulting action |
| --- | --- | --- | --- |
| Pre-correction | Parent round-4 `spec_auditor`, `correctness_reviewer`, `test_reviewer` | Confirmed `Not applicable / blocks_approval / verification`: validator accepts invalid collection shapes; root validated the evidence | Linked bounded design correction opened |
| Delta 1 | Fresh `$review-design` `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | DREV-001 quoted unprojected type-position bypass confirmed; DREV-002 stale validator pins confirmed; DREV-003 public publication/family proof incomplete. All are `Not applicable / changes_required` and consolidated in immutable report `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-01.md`. | One invariant-level quoted-type remediation, then coordinated implementation repin and public proof |
| Delta 2 | Fresh targeted `$review-design` `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | DREV-001 whole-expression quote handling and DREV-002 design pin handoff validated. DREV-004 confirmed: quoted ellipsis children and `Field(...)` type arguments bypass complete type/data classification; duplicate-ellipsis proof is incomplete. Consolidated in immutable report `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-02.md`. | Final design remediation round closes the classifier invariant |
| Final delta | Fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | DREV-004 is resolved. DREV-005 atomic-publication failure recovery, DREV-006 tuple boundary proof, and DREV-007 revision-bound parent handoff are confirmed as `Not applicable / changes_required`; consolidated in immutable `docs/reviews/semantic-ingestion-layer1-validator-collection-closure-2026-07-29/delta-round-03.md`. | Stop at the exhausted design-round budget and request a bounded design-workflow extension |
| Additional rounds 1-2 | Fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | Grammar, tuple proof, core atomic replacement, content-addressing, and checker isolation verified. DREV-008 incomplete publication failure/transition proof, DREV-009 access-mode regression, and DREV-010 unsupported directory-open classification confirmed as `Not applicable / changes_required`; immutable `delta-round-04.md`. | Additional round 3 completed the bounded correction; fresh delta review required |
| Additional round 3 | Pending fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | DREV-008 through DREV-010 are locally remediated with deterministic filesystem-state evidence | Fresh three-role delta review |
| Additional round 4 | Fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | DREV-008 through DREV-010 are resolved. DREV-011 checker snapshot TOCTOU and DREV-012 real-open/audit-denial proof confirmed as `Not applicable / changes_required`; immutable `delta-round-05.md`. | One snapshot-and-isolation remediation |
| Additional round 5 | Pending fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | DREV-011 and DREV-012 are locally remediated through snapshot-only replica materialization, source-swap proof, audit-denial proof, and real-open state proof | Fresh three-role delta review |
| Additional round 6 | Fresh `spec_auditor`, `correctness_reviewer`, and substitute fresh `test_reviewer` | DREV-011/DREV-012 are resolved. DREV-013 non-isolated checker startup and DREV-014 non-specific audit denial confirmed as `Not applicable / changes_required`; immutable `delta-round-06.md`. The first test pass inspected the wrong checker and was not counted. | Final bounded isolation correction |
| Additional round 7 | Fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | DREV-013/DREV-014 are behaviorally resolved. Spec and correctness approved. Test review confirmed DREV-015 missing checker-owned actual-entry evidence; coordinator confirmed DREV-016 scoped Pyright failure. Both are `Not applicable / changes_required`; immutable `delta-round-07.md`. | One bounded evidence correction in round 9, then final review in round 10 |
| Additional round 7 coordinator gate | Coordinator direct inspection and deterministic checks | Exact isolated checker, clean non-isolated rejection, self-test, Ruff, `py_compile`, prior-report validation, and diff check pass. Scoped Pyright fails at validator line 2477 because publication-test local `initial_mode` is possibly unbound. Candidate remains unapproved pending reviewer reconciliation. | Preserve the reviewed snapshot; reconcile this direct finding with the independent round-8 reports |
| Additional round 9 | Pending fresh final `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | DREV-015/DREV-016 are locally remediated through captured-checker actual-entry proof and explicit optional mode state; exact deterministic gates pass | Fresh final round-10 three-role review |
| Additional round 10 attempt 1 | Invalidated before completion | One spec pass reported transient duplicate source lines and a moving checker but supplied no second digest. Coordinator immediately stopped both other reviewers. Current source contains one `marked_v1` pattern and one `script.write_text`, and all five frozen identities remain exact. The user confirmed no external edit. DREV-017 is unsupported by persistent repository evidence; the pass is not counted as a completed review. | Refreeze the unchanged candidate and restart all three independent reviewers |
| Additional round 10 replacement | Fresh `spec_auditor`, `correctness_reviewer`, and `test_reviewer` | All three reviewers verified identical start/end hashes, independently exercised the relevant gates, approved DREV-015/DREV-016 closure, and found no confirmed `blocks_approval` or `changes_required` gap. Immutable `delta-round-08.md`. | Approve the frozen design and resume the parent implementation handoff |

## Blockers And Limits

- Original budget: 3 design rounds; used: 3 correction rounds and 3 delta
  reviews.
- Additional budget: up to 10 bounded design-revision rounds authorized by the
  user on 2026-07-29. One coherent correction or one independent review pass
  counts as one round; coordinator checks and ledger updates do not.
- Additional rounds used: 10 of 10.
- The user authorized up to 5 further bounded rounds on 2026-07-29 if the
  restarted final review exposes a confirmed gap. An invalidated review attempt
  does not consume a correction/review round.
- Remote CI/branch-protection evidence is outside this design correction.

## Progress Log

- 2026-07-29: Opened linked design WorkPlan from the parent round-4 confirmed
  validator divergence. Established that the architecture semantics are closed
  and the lowest-risk correction is validator-only.
- 2026-07-29: Added common collection syntax validation and self-test coverage
  for direct/alias invalid forms plus each authorized sibling form. Verification
  and fresh review remain pending.
- 2026-07-29: Validator self-test passed against the frozen design and registry,
  reproducing authority SHA-256 `89a98fc1...`, 56 schemas, 240 enum rows, and
  profile digest `20edd38a...`. The corrected validator SHA-256 is
  `221f9e2c57135ff2f833b4eff40418e1366fd306d5b163a404e878bcf8694a5b`.
  Scoped Ruff, Pyright, `py_compile`, and `git diff --check` passed. The
  interrupted worker-side parallel command is not evidence and is superseded
  by these coordinator-run checks.
- 2026-07-29: DREV-001 remediation parses only quoted annotation/alias type
  expressions before recursive closed-grammar validation. Direct, quoted,
  nested, inherited, alias, reachable, and unprojected collection shapes share
  the invariant; Literal/default/Field strings remain data. The validator
  self-test passed with unchanged authority/profile output. Validator SHA-256
  is `128bf582014d6fcb5bf59a8e227f726a83f673722133042c8a870cfb77089b4f`.
  `docs/development/static_tooling.md` is repinned only at its documented
  command and prose identity. DREV-003 remains an explicit parent
  implementation public-CLI handoff.
- 2026-07-29: Coordinator integrity inspection found metadata closure had
  briefly over-tightened unprojected `ast.Name` data expressions. The final
  design validator preserves names, literal strings, and signed literals as
  data; it rejects calls, attributes, and `**kwargs`. Validator-owned controls
  prove dynamic unprojected `Annotated`, `Field`, and `Literal` expressions
  reject while Literal and Field string data controls remain valid. Exact
  checker output, Ruff, Pyright (`0 errors`), `py_compile`, immutable report
  validation, and `git diff --check` pass.
- 2026-07-29: Final DREV-004 remediation rejects quoted ellipsis and bare
  `Field(...)` in every type position. Only native position-two ellipsis in
  exact `tuple[T, ...]` is admitted; all other collection children recurse
  through the type classifier after outer shape validation. Validator-owned
  tests now cover quoted-child ellipsis and Field-as-type cases across all
  collection owners, multiple native ellipsis variants, and valid quoted/data
  controls. Public CLI no-publication remains parent implementation evidence.
- 2026-07-29: Additional design revision 1 closes DREV-005 and DREV-006. The
  validator validates computed canonical bytes before publication, writes to a
  unique same-directory temporary file with exact-write, flush, file-fsync,
  atomic replace, and directory-fsync behavior, and never re-reads the target
  after a successful write. Deterministic failpoints prove absent/seeded target
  preservation for write, short-write, flush, and replace failures; concurrent
  readers observed only complete old/new canonical bytes. The test does not
  claim rollback after a post-replace directory-fsync error. Explicit tuple
  quoted-child cases and `tuple[()]` normalization now pass. Final validator
  SHA-256 was an intermediate candidate and was superseded by the final
  hermetic-checker correction below.
  Parent DREV-007 remains a revision-bound handoff: after design approval,
  implementation must repin all workflow/test consumers to this SHA and run
  public validator `--write` absent/preseeded/valid subprocess evidence.
- 2026-07-29: The coordinator authorized the smallest checker update: allow
  exactly `errno`, `os`, `tempfile`, and `threading`; retain every other import
  and audit prohibition; and allow only the authority parent, direct
  same-directory publication temporary sibling, and validator-owned namespaced
  self-test subtree. The exact hermetic checker passed with validator SHA-256
  `46af2e98583c524b21fe3202de695053dc6d939285604524e603c463f891e64c` and
  checker SHA-256 `9e7e28196e9bb7ca7b50365937266d8330e6f26b16b43b94b8b0b588629fb240`.
  The validator self-test reproduced authority `89a98fc1...`; Ruff, scoped
  Pyright (0 errors), `py_compile`, all immutable report validators, and
  `git diff --check` passed. Parent DREV-007 handoff is revision-bound to
  these exact validator/checker identities and requires parent implementation
  repinning plus public subprocess `--write` absent/preseeded/valid evidence
  only after this design candidate is approved.
- 2026-07-29: Fresh final review confirmed the classifier behavior and exact
  authority reproduction, then found that direct `Path.write_bytes` publication
  can truncate a valid authority before validation. Tuple-specific quoted-child
  and zero-item controls are also incomplete, and the parent public-CLI handoff
  is not revision-bound. The immutable round-3 report records DREV-005 through
  DREV-007. The 3/3 design budget is exhausted, so this WorkPlan is blocked.
- 2026-07-29: The user authorized up to 10 additional bounded design-revision
  rounds. The WorkPlan is reopened without changing scope: one writer will
  correct atomic publication and tuple boundary evidence, then fresh reviewers
  will inspect the stable candidate before any parent implementation repin.
- 2026-07-29: Additional review round 2 verified the closed grammar, tuple
  boundary, checker least privilege, and authority reproduction. It confirmed
  three publication issues: incomplete deterministic failure/cleanup/reader
  proof, access-mode regression from the private temporary inode, and
  unsupported directory-open errors misclassified as post-replace failure.
  These are consolidated in immutable `delta-round-04.md`.
- 2026-07-29: Additional design revision 3 remediates DREV-008 through
  DREV-010 in the single publication owner. The self-test now proves absent
  and seeded pre-replace preservation, including immediate, zero-progress, and
  partial-progress write failures, flush/file-fsync/replace failures, exact
  seeded permission mode, absence preservation, and no temporary sibling.
  Existing resolved regular targets retain `st_mode & 0o7777`; absent targets
  create deterministically as `0644`; restrictive and symlink-resolved cases
  are covered. `_fsync_directory` treats `EINVAL`, `ENOTSUP`, and
  `EOPNOTSUPP` identically at directory open and fsync, while an injected EIO
  surfaces after the exact new target is visible. A coordinated replacer proves
  reader observations exactly transition from old bytes to new bytes. This is
  design helper/failure-seam evidence, not the deferred parent public
  invalid-`--write` subprocess proof. Checker bytes remain unchanged because
  no new import or audited path was added. Candidate validator SHA-256 is
  `7a0f9563827ca7aa4a7683493914f00bcbd71e73d1d6c9924f80f446001002a4`;
  checker remains `9e7e28196e9bb7ca7b50365937266d8330e6f26b16b43b94b8b0b588629fb240`.
- 2026-07-29: Coordinator integrity follow-up within the same additional round
  found that applying the final target mode before the write exposed a partial
  temporary inode to the target's readers. The mode transition now occurs only
  after complete write and flush, before the content-and-mode file fsync. An
  injectable mode-set seam extends absent/seeded preservation and cleanup
  evidence, while a partial-writer control proves the temporary remains `0600`
  and the completed target receives its intended mode. Validator SHA-256 is
  `7a0f9563827ca7aa4a7683493914f00bcbd71e73d1d6c9924f80f446001002a4`;
  checker remains unchanged.
- 2026-07-29: Additional review round 4 approved the collection/publication
  specification but confirmed that the checker verifies source bytes and later
  rereads their paths for replica materialization. It also requires one real
  directory-open state assertion and a negative audit-hook known-answer probe.
  These are consolidated in immutable `delta-round-05.md`.
- 2026-07-29: Additional design revision 5 closes DREV-011 and DREV-012. The
  checker captures design, registry, checked authority, validator, and checker
  bytes once; hashes/validates those snapshots; and materializes each replica
  only through a shared byte-input owner. A per-source snapshot-swap known
  answer mutates a source path after capture and verifies the replica still
  contains captured design/registry/validator bytes. A derived import-valid
  validator probe attempts an undeclared sibling read through the real
  bootstrap; it fails with `undeclared file access` while its checked authority
  and owned temporaries remain unchanged. Validator self-test adds real EIO
  directory-open state proof and asserts bytes/existence/mode/no temporary for
  every unsupported and real post-replace open/fsync outcome. Candidate hashes
  are validator `facdcbd13c3149b5e481ab5d676a24694882d9a1c16200e2b51016222de97d44`
  and checker `a79736c0df54e6952f452c3004b22d6107457636566238dbf03e92fc3256257b`.
- 2026-07-29: Additional review round 6 approved snapshot binding and atomic
  publication, then confirmed two startup/proof gaps: the authoritative checker
  command omits Python isolated mode before imports, and the negative audit
  assertion is not bound to its injected path. The original test reviewer
  inspected an unrelated checker and was replaced; the substitute approved the
  correct design checker. Immutable evidence is `delta-round-06.md`.
- 2026-07-29: Additional design revision 7 closes DREV-013 and DREV-014. The
  canonical static-tooling command is `python3.12 -I`; checker main rejects a
  clean non-isolated invocation with the explicit isolation diagnostic. Because
  imports precede main, the canonical `-I` invocation remains the security
  boundary. A checker-owned scratch probe uses the same isolated interpreter
  pattern beside a malicious `hashlib.py` and proves the sibling neither
  executes nor replaces the stdlib digest. The audit probe now seeds and reads
  the same resolved replica path and requires the exact
  `undeclared file access: <path>` stderr diagnostic. Validator bytes remain
  `facdcbd13c3149b5e481ab5d676a24694882d9a1c16200e2b51016222de97d44`;
  checker SHA-256 is
  `ed90fb681c520cfb86dff67381cf3a664ab2f50044b5f7513860b24668cdc7cb`.
- 2026-07-29: Coordinator verification reproduced authority `89a98fc1...`
  under the exact isolated two-replica checker and observed the exact required
  non-isolated diagnostic. Ruff, `py_compile`, prior immutable-report
  validation, and `git diff --check` pass. Scoped Pyright independently found
  `initial_mode` possibly unbound in the atomic-publication failure assertion;
  no candidate bytes were changed while the fresh round-8 reviewers run.
- 2026-07-29: Additional review round 8 approved DREV-013/DREV-014 closure.
  DREV-015 is confirmed because the checker-owned suite proves isolation with a
  substitute startup script rather than the actual checker entry. DREV-016 is
  confirmed by the coordinator's reproducible scoped-Pyright failure. Both are
  `Not applicable / changes_required` verification findings; immutable
  evidence is `delta-round-07.md`.
- 2026-07-29: Additional design correction round 9 closes DREV-015 and
  DREV-016 without changing architecture, registry, authority, profile, grammar,
  publication ordering, or audit allowlists. Checker main passes its single
  captured/hash-verified checker snapshot into a clean scratch actual-entry
  control; the copied checker is launched without `-I` and proves exact exit
  `1`, empty stdout, and stderr equal to `ISOLATION_DIAGNOSTIC + "\n"` before
  argument parsing. The validator publication test initializes
  `initial_mode: int | None` and explicitly rejects missing seeded state before
  retaining the exact mode comparison. Exact candidate hashes are validator
  `538a01f1a37772b71b224cb4d1456509f0644850eb7ebbc67a64374f4a3d13fc`
  and checker
  `2ca3da2c69b453e2107ab4e901345b4b5420288666561c566732849d56c811c1`.
  Canonical isolated checker, direct clean non-isolated invocation, validator
  self-test, Ruff, Pyright 0/0/0, `py_compile`, immutable reports 01-07, and
  `git diff --check` pass; authority remains `89a98fc1...` with 56 schemas,
  240 enum rows, two replicas, and profile `20edd38a...`.
- 2026-07-29: The first round-10 attempt was invalidated when one reviewer
  reported a transient moving checker while the other two reviews were still
  running. Coordinator stopped the remaining reviewers. Recomputed checker
  `2ca3da2c...`, validator `538a01f1...`, architecture `67bf2620...`, registry
  `38c45adc...`, and authority `89a98fc1...` identities remain exact; the
  alleged duplicate lines are absent. The user confirmed no external edit.
  DREV-017 is therefore unsupported by persistent evidence, no immutable
  approval report was created, and a completely fresh three-role pass is
  required.
- 2026-07-29: Replacement final round 10 approved the unchanged candidate.
  Each fresh reviewer verified all five identities at review start and end and
  independently confirmed the exact isolated checker, DREV-015 actual-entry
  control, DREV-016 static closure, and VLC-001 through VLC-004 evidence.
  Immutable approval evidence is `delta-round-08.md`.

## Next Action

Resume `docs/work/semantic_ingestion/implementation.plan.md`: repin the
canonical workflow and both test consumers to validator `538a01f1...` and
checker `2ca3da2c...`, require `python3.12 -I`, and execute the public
absent/pre-seeded/valid publication matrix.

## Outcome And Retrospective

Approved after the replacement final round-10 three-role review. No unresolved
validated `blocks_approval` or `changes_required` design gap remains in
VLC-001 through VLC-004. Implementation consumer repins, public CLI evidence,
and remote CI remain parent-owned.

| Gap | Requirement | Severity | Attempts | Why unresolved | Required next step |
| --- | --- | --- | --- | --- | --- |
| Direct authority write can corrupt the prior artifact | VLC-004 | Not applicable / changes_required | 3 design corrections | Failure recovery was not exercised until final review | Reopen for one bounded atomic-publication correction and failpoint proof |
| Tuple quoted-child and zero-item proof incomplete | VLC-002 | Not applicable / changes_required | 3 design corrections | Final family matrix omitted tuple-specific quoted children and the recorded zero-item control | Add the complete tuple boundary matrix in the same correction |
| Parent handoff is not bound to the final candidate | VLC-003, VLC-004 | Not applicable / changes_required | 3 design corrections | Implementation consumers correctly remained frozen while design was under review, but the durable parent matrix is stale | Record the final identity/matrix before implementation repin |
| Publication failure/transition evidence incomplete | VLC-004 | Not applicable / changes_required | Additional rounds 1-2 | Core atomic behavior exists, but partial-write/file-fsync/directory-fsync/cleanup/public-process/reader transition proof is incomplete | Complete one deterministic filesystem-state matrix |
| Replacement changes target access mode | VLC-004 | Not applicable / changes_required | Additional rounds 1-2 | Private `mkstemp` inode replaces the compatible target mode | Preserve existing mode and define/test absent-target mode |
| Unsupported directory open is treated as failure | VLC-004 | Not applicable / changes_required | Additional rounds 1-2 | Unsupported errnos are classified only at fsync, not directory open | Classify unsupported open/fsync consistently |
| Checker executes path rereads rather than captured bytes | VLC-003 | Not applicable / changes_required | Additional rounds 3-4 | Hash verification and replica materialization use different reads | Materialize only captured verified snapshots and prove source swaps cannot affect replicas |
| Audit denial and real-open state proof incomplete | VLC-003, VLC-004 | Not applicable / changes_required | Additional rounds 3-4 | Positive replicas and real fsync proof do not exercise both branches | Add negative audit known-answer and real directory-open state assertions |
| Checker startup permits pre-hash import shadowing | VLC-003 | Not applicable / changes_required | Additional rounds 5-6 | Canonical command omits Python isolated mode | Require `-I`, assert isolated startup, and prove sibling shadow rejection |
| Audit denial is not bound to the injected path | VLC-003 | Not applicable / changes_required | Additional rounds 5-6 | Seeded file and injected read differ; generic denial is accepted | Align the exact path and assert the full denial diagnostic |
| Actual checker entry lacks checker-owned negative evidence | VLC-003 | Not applicable / changes_required | Additional rounds 7-8 | Separate executions prove the guard, but the deterministic checker suite exercises only a substitute startup script | Execute a clean copied checker without `-I` and assert its complete process contract |
| Validator candidate fails scoped Pyright | VLC-004 | Not applicable / changes_required | Additional rounds 7-8 | Seeded-target mode state is runtime-correlated but not statically initialized | Make the optional mode state explicit without weakening the mode assertion |

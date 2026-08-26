# Blocker Delta Review Round 9

## Scope and identity

This report reconciles the independent targeted review of frozen candidate v10,
lock `3677607e62f285c8fb9da63e380f501e1e11a362c26f0c959cdc32036e2d0ac8`,
for `VCC-DREV-008B` only. Reviewers verified all 96 tracked hashes. No
production code or repository tests changed.

## Reconciled findings

### VCC-DREV-008B-MUTATION-CORPUS

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Finding type: `verification`
- Classification: `confirmed`

The v10 validator executes 32 attacks, but it accepts the attack-name set
returned by inherited `_mutations()` as complete. Removing an inherited attack
can therefore shrink the executed corpus without failing the positive result.
The correction is determinate: independently freeze the exact attack-name set
in both ledger and oracle, reject missing and unexpected names, reject every
false result, and prove the omission detector with a deliberate self-test.

### VCC-DREV-008B-EXTERNAL-MONKEYPATCH

- Product priority: `Not applicable`
- Approval disposition: `follow_up`
- Finding type: `verification`
- Classification: `unsupported`

One reviewer proposed expanding the static source proof to arbitrary
post-definition assignments such as replacing a governed class method from an
external module. That is not an accepted production construction form in the
frozen ownership grammar. A same-module replacement changes a governed source
hash and fails closed. An arbitrary external runtime monkeypatch cannot be
closed by finite static syntax enumeration and would expand this targeted
design review beyond its frozen source and composition boundaries. Under the
convergence stop rule, it does not reopen `VCC-DREV-008B`.

## Decision

Targeted decision for candidate v10: `CHANGES_REQUIRED`, solely for the exact
mutation-corpus contract. Candidate v10 remains the immutable identity of this
decision. The bounded correction is candidate v11; no other grammar family is
admitted into this remediation round.

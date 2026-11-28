# Discover the packaged catalog through authenticated host tools

- Work ID: packaged-catalog-discovery-design
- Work type: design
- Delivery fidelity: Level 2 local work and household testing
- Status: blocked
- Coordinator: Codex
- Created: 2026-11-27
- Last updated: 2026-11-27
- Parent WorkPlan: [reviewed lifecycle audit](design-gap-closure.plan.md)
- Related WorkPlans: [implementation milestone](../ontology-gap-implementation/milestones/packaged-catalog-discovery.plan.md), [existing inspection design](design-catalog-inspection.plan.md)
- Canonical inputs: [ontology design sections 12–13](../../design/learned_ontology.md), [specification](../../design/memorii_spec.md), [storage](../../design/memorii_storage_details.md), [event model](../../design/event_model.md)
- Expected outputs: a reviewed tool, browse, and subject-selection contract for the installed no-key workflow

## Objective and scope

On either installed authenticated binding, expose a discoverable, read-only
workflow for finding the bill due-date relation and reading a current
authorized value. A work question can also clarify an ambiguous relation.
Use deterministic local reads and the signed-in account's current grants.
Preserve the exact request grammars, historical visibility, and same-version
handoff in Sections 12–13. No deployment, ontology mutation, fact writes,
or new storage authority is required for catalog browsing.

## Current production baseline

At `c0fa889a1791fe059b94347215ecf03ecac275f1`, both host roots expose
direct inspection and diagnosis through `CatalogReadBinding`. Neither
registers these operations in a discoverable tool list. Hermes's existing
`get_tool_schemas` may pin a captured turn. This makes it unsuitable as
the only source of read-tool registration. The generic root has no tool
list. Neither root's exact diagnosis resolves a subject from its name. The
installed integration supplies a canonical provisioned subject ID.

## Proposed contract and decision

Use a shared host-neutral tool schema and dispatcher behind the two
verified bindings, with the Hermes registration as a thin host adapter.
Expose the current exact inspection and diagnosis shapes unchanged.
Propose a separate bounded browse operation over the authorized catalog
projection sorted by exact predicate ID. Browse metadata follows the same
catalog snapshot and release checks and contains no fact or subject
payload. Define its page bounds, version handoff and typed outcomes when
freezing the design. Register the tool schema independently of captured-turn
state. A tool description confers no invocation authority.

The user-visible decision is **who resolves a bill or work-item name to
a verified subject identity**. The recommended Level 2 boundary uses a
canonical ID supplied by the authenticated host and returns clarification
when the host cannot identify the subject. This is the existing Sections
12–13 boundary. If the user needs a natural-language bill-name journey
with no host-supplied ID, a separate subject lookup may disclose candidate
identities. Its permission, discoverability, ambiguity, stale-selection,
and release semantics must be resolved in this design before implementation.
The ability to recall one fact by known ID supplies no authority to enumerate
subjects.

## Verification and completion

- Both registered bindings list and invoke the workflow without a completed
  turn, write grant, key, model, or network. Reopen and repeat. Use mutation
  tripwires to separate read-only listing from the existing turn pin.
- Exercise bill due date, ambiguous work relation, absent verified subject,
  stale selected version, and withdrawn or foreign account authority.
  Verify payload-free denial and no read-time mutation.
- Verify full retained behavior of existing exact ID and name inputs. If a
  subject lookup is approved, add a bounded same-account ambiguity and
  current-grant release witness to the matrix before coding.
- Freeze the decision and wire/result shapes, map both real composition
  roots, verify feasibility and obtain targeted independent design review.
  Link the approved revision or digest to the implementation packet.

## Next action

Record the user's subject-resolution decision and freeze the corresponding
tool and browse contract.

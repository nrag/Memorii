# Discover the packaged catalog through authenticated host tools

- Work ID: packaged-catalog-discovery-design
- Work type: design
- Delivery fidelity: Level 2 local work and household testing
- Status: complete (Level 2 design)
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

## Contract and decision

Use a shared host-neutral tool schema and dispatcher behind the two
verified bindings, with the Hermes registration as a thin host adapter.
Expose the current exact inspection and diagnosis shapes unchanged.
Use a separate bounded browse operation over the authorized catalog
projection sorted by exact predicate ID. Browse metadata follows the same
catalog snapshot and release checks and contains no fact or subject
payload. Section 13 defines its page bounds, version handoff and typed
outcomes. Register the tool schema independently of captured-turn
state. A tool description confers no invocation authority.

The user selected a verified canonical identifier from the host. When
absent, the host invokes unresolved recall and asks for clarification.
The normative tool names, closed browse grammar, page and version
semantics, release rules and compatibility behavior are specified in
Section 13. The existing inspected predicates and stored authority remain
unchanged. The read-only list has no captured-turn dependency, while
the combined Hermes list preserves the existing write-tool behavior.

## Verification and completion

- Both registered bindings list and invoke the workflow without a completed
  turn, write grant, key, model, or network. Reopen and repeat. Use mutation
  tripwires to separate read-only listing from the existing turn pin.
- Exercise bill due date, ambiguous work relation, absent verified subject,
  stale selected version, and withdrawn or foreign account authority.
  Verify payload-free denial and no read-time mutation.
- Verify full retained behavior of existing exact ID and name inputs, and
  page through a complete default catalog. Repeat with an invalid cursor
  and stale digest. Use the production catalog projection and protected
  release, with a tripwire on the fact reader.
- Freeze the decision and wire/result shapes, map both real composition
  roots, verify feasibility and obtain targeted independent design review.
  Link the approved revision or digest to the implementation packet.

## Review and handoff

The focused independent reviewer passed the Section 13 delta and installed
acceptance without approval findings. The targeted follow-up verified that
static advertisement requires operator read opt-in configuration and uses
the existing Hermes function schema envelope. The reviewed canonical
design SHA-256 is `408be6aa9a2d263e55a566a7889ce81c3c87b0e007eb9109e2448580aa3d2c45`.
The existing exact workflows and provider hooks establish the composition
seams. The implementation packet owns browse dispatch and release proof.

## Stock Hermes routing

The operator approved stock Hermes in this milestone. The pinned host's
`MemoryManager.add_provider` collects and registers schemas before
`initialize_all` and never refreshes its routing table. Section 13
defines a literal process opt-in and static pre-initialization registration
for this path. Only an existing verified primary CLI operator binding and
the current exact grants authorize a result. Use the current storage row and
grant identity conventions. No persisted format, new grant issuance, or
changes to the generic binding are required. Historical fact grants remain
authoritative. The Level 2 witness registers before initialize and exercises
the real manager's tool listing and dispatch with the candidate wheel.

The targeted design reviewer checked the registration, grant and scope
boundary. The canonical amendment now spells out the exact projection row
and live process opt-in recheck. Stock absent-user matching requires a
pre-existing operator binding for the same absent-ID coordinate and cannot
use the generic operator-binding recovery option.

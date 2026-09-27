# Default Ontology Catalog Contract

**Status:** Normative part of the approved design in [learned_ontology.md](learned_ontology.md). Not implemented.

This file binds each default relation to a typed value, lifecycle policy, grounding rule, scope class, and protected-read form. It is a contract for the catalog to be built, not a claim that the current three-predicate profile supports these entries. The twenty entity types and seven home subtypes are defined in the parent design. The relation identifiers below are stable semantic identities; an implementation cannot omit an entry and still claim the default catalog is complete.

## Shared policy vocabulary

**Domain and identity.** All rows below except the separately listed preference records route to semantic memory. Entity endpoints require source-grounded type evidence and canonical identity resolution in the same authorized fact scope. `Document` and `Message` are referent entities, never an alias for the retained source artifact. `Role` is an identified assignment instance, not a global job-title string: two people called "engineer" have distinct role instances. Its canonical identity key is `(fact scope, canonical holder ID, normalized role designation, explicit organization/group ID or null)`. The holder must be resolved before the assignment is created; unscoped and scoped assignments are distinct and cannot merge by title. `has_role` links that holder to the keyed instance, while `role_scoped_to` constrains where the instance applies. A title mention alone cannot create either edge. The identity resolver must use this assignment key rather than same-name/same-type alias merging. Subtype aliases (`Household`, `Chore`, and the other home forms) are resolved by the versioned type registry in the parent design; an unregistered subtype cannot be silently coerced to its parent. An `Unknown` entity type cannot satisfy a typed endpoint.

The type IDs below use the exact case-sensitive spelling shown. The catalog serializes each declaration as `(type_id, parent_id or null, identity_policy_id, scope_class, sorted aliases)` and sorts by `type_id`. The twenty roots have no parent. The seven home forms are **subtypes**, not ambiguous free-form aliases; their parent is fixed below. The alias set starts empty for every row, so a spelling not shown here has no special authority. Identity policy `introduced` uses an authenticated external ID when available, otherwise `(fact scope, first verified origin-lineage ID, exact introduction span)` until later explicit core-verified alias evidence links mentions; name equality alone cannot merge two entities. `event` additionally requires source-grounded event occurrence/time context and never merges solely on a title. `artifact` uses a stable referent/document/message ID plus version or source-grounded artifact introduction; raw retained source IDs are in a different namespace. `role_assignment` uses the holder/designation/scope key above. `account` requires an opaque provider-bound account ID; a bare account name is unresolved. `animal` requires an owner/household binding plus distinguishing source evidence or an opaque animal ID; two pets with one name remain distinct unless identity is proved. A subtype inherits its parent's policy and may add the narrower scope class. Unknown identity policy IDs fail closed.

| Type IDs | Parent | Identity policy | Scope class |
| --- | --- | --- | --- |
| `Person`, `Organization`, `Group`, `Project`, `Goal`, `Issue`, `Place`, `ProductService`, `Asset`, `Agreement`, `Obligation`, `Opportunity`, `WorkItem`, `Decision` | None | `introduced` | G, except `Person`, `Asset`, `Agreement`, `Obligation` use P |
| `Role` | None | `role_assignment` | G |
| `Event` | None | `event` | G |
| `Document`, `Message` | None | `artifact` | `Document`: G; `Message`: P |
| `Account` | None | `account` | P |
| `Animal` | None | `animal` | P |
| `Household` | `Group` | `introduced` | P |
| `Appointment` | `Event` | `event` | P |
| `Chore` | `WorkItem` | `introduced` | P |
| `Subscription` | `Agreement` | `introduced` | P |
| `Bill` | `Obligation` | `introduced` | P |
| `Vehicle` | `Asset` | `introduced` | P |
| `Recipe` | `Document` | `artifact` | P |

**Scope classes.** `G` means the authenticated source and caller grants must authorize the selected existing fact scope and both endpoint identities; it never widens a source's scope. `P` additionally treats the relation as private person, household, finance, legal, or account information. In the initial home journey, every `P` fact is scoped to the signed-in account's authenticated user ID; `Household` is only a source-grounded entity and never an access principal. An organizational `P` fact may use only an independently authorized existing fact scope, with no tenant-group sharing inferred from catalog ownership or graph membership. Effective restriction is the stricter of relation and endpoint type classes; a `G` row involving a `P` person, animal, account, or home subtype is treated as `P`. These are minimum restrictions. Agent-local catalog ownership is a separate coordinate. A person's relationship to another person does not grant either person's agent access to the other's private memory. The initial catalog defines no household or tenant-group fact-scope variant.

**Evidence classes.** `D` requires an exact, positive, asserted source proposition with independent subject, predicate, and object role evidence and a source allowed by the trust policy; quoted, hypothetical, reported, instructed, questioned, and unsupported speaker claims abstain. `A` also requires a source with authority for the claimed approval, obligation, payment, or legal/account state, or an explicit authorized owner confirmation; a document's presence alone is not an approval. `E` requires a source-grounded event or artifact identity and exact linkage to both endpoints. All classes require proposition-level semantic validation, provenance and current grant checks; model confidence cannot replace them. Negation and correction enter their own lifecycle paths, not a positive edge. For organizational sources, policy may distinguish official record, participant assertion, and attributed belief. Home sources may use the authenticated signed-in user as the confirming owner rather than an organizational official. A claim below the required authority remains attributed evidence, not global committed truth.

**Lifecycle classes.** `M` is a set of independently supported values, where a new value does not remove older values; explicit retraction or correction targets one value and preserves event history. `C` is one current value per `(scope, subject, relation)`; competing claims use the registered trust/time conflict rule, preserve earlier versions, and never mutate a structural node. `H` is a historical relation whose occurrence is append-only; correction creates a superseding or invalidating event with explicit target, not deletion. Every row records assertion and valid/system time; unknown valid time stays unknown. `LocalDate` is a date-only value with its source calendar and no implied UTC conversion. `TimeInterval` is a typed half-open interval with timezone-aware bounds or explicit open-bound status and verified source temporal evidence. `Money` is a decimal amount plus ISO 4217 currency; floats, missing currency, and inferred conversion reject. `StatusText` is a bounded canonical value whose relation-specific vocabulary and aliases are declared below; unknown status remains unresolved. `TimeInterval` and `Money` need new typed codecs and validators before their rows can be shipped; the current `ClaimValueType` has neither.

**Literal value policies.** Every literal relation declaration carries a versioned `value_policy_id` and its content digest. `work_item_due_on` and `obligation_due_on` use `local_date`; `event_time` uses `time_interval`; `obligation_amount` uses `money_iso4217`. `work_item_status` uses `work_item_status`: canonical `todo`, `in_progress`, `blocked`, `done`, `canceled`; accepted aliases `open`/`to do` -> `todo`, `started`/`working` -> `in_progress`, `complete`/`completed` -> `done`, `cancelled` -> `canceled`. `opportunity_stage` uses `opportunity_stage`: canonical `lead`, `qualified`, `proposal`, `negotiation`, `won`, `lost`; aliases `prospect` -> `lead`, `qualified lead` -> `qualified`, `offer` -> `proposal`, `negotiating` -> `negotiation`, `closed won` -> `won`, `closed lost` -> `lost`. Normalization uses the catalog's versioned Unicode/case-fold policy; a phrase with more than one possible canonical value is unresolved. Any canonical-to-canonical change is permitted only through an explicit grounded correction or later current assertion governed by trust/time; no stage progression is inferred. Unknown or conflicting status text cannot create a new catalog value by model suggestion. Changing a vocabulary, alias, or transition rule creates a new catalog/version protocol decision, not an in-place mutation.

**Read forms.** `set` renders all currently supported authorized objects and can query as-of history. `current` renders one selected current value and its authorized correction history. `history` renders dated events/links with provenance. All reads are by typed subject plus relation ID, pinned historical catalog declaration, caller scope, and as-of coordinate; an inverse read is allowed only if its own protected query checks both endpoint scopes. A missing historical declaration fails closed. The label in each ledger row is the user-facing relation wording, never a source of truth or a way to bypass the typed read policy.

**Read derivation.** The declaration field `read_derivation_policy` is `none` for every base relation except `partner_of` and `sibling_of`, which use registered `symmetric_view`. A symmetric view permits querying the asserted object as subject and renders the original assertion's provenance, version, valid time, and correction status in reverse order; it persists no reverse edge or independent belief. The protected reader checks caller grants for the fact scope, both endpoint identities, and the catalog-owner coordinate before returning a reverse result, snippet, or count. A retracted or expired assertion has no current inverse view, while its authorized as-of history remains visible. No other base relation gets an inverse view by implication.

Each row has four mandatory acceptance cases under a real fact-ingestion and protected-read path: direct authorized assertion, misleading or unauthorized near miss that abstains, explicit correction/retraction or historical supersession, and scoped current plus historical read. The fixture name is derived from the relation ID with behavioral suffixes `assertion`, `abstention`, `revision`, and `read`. At least one persona or home scenario in the parent design must invoke each row. Mandatory privacy rows also require a cross-scope denial case. A fixture passes only when committed records, zero-effect cases, and reads agree exactly; a model-shaped proposal alone is insufficient.

The `Coverage` column is normative: its code names a primary organizational persona or home journey that must exercise the row through those four cases. Multiple codes require both journeys. An implementation's generated corpus gate compares the exact set of 53 relation IDs with the ledger, rejects missing/duplicate/orphan coverage references and a fixture whose asserted predicate differs from its declared row, and checks every one of the twenty persona and ten home codes has at least one direct scenario. Code labels are test traceability, not persisted catalog identities.

| Code | Required journey | Code | Required journey |
| --- | --- | --- | --- |
| SE | Software engineer: ticket/project and status | EM | Engineering manager: reporting and team |
| SRE | SRE/DevOps: service incident impact | QA | QA engineer: issue resolution |
| DATA | Data analyst/scientist: document about analysis target | PM | Product manager: project and goal |
| DESIGN | Product designer: versioned approval | UX | UX researcher: event participation |
| OPS | Program/operations manager: assignment and dependency | EXEC | Executive/founder: goal and decision |
| MKT | Marketing manager: campaign event and product | CONTENT | Content writer/editor: authored/versioned document |
| SALES | Sales executive: opportunity owner/counterparty/stage | SALESOPS | Sales operations: account holder/provider |
| CS | Customer success manager: agreement and service | SUP | Customer support specialist: issue and messages |
| HR | Recruiter/HR specialist: team membership and role | FIN | Finance/accounting specialist: obligation and payment evidence |
| LEGAL | Legal counsel: agreement parties | IT | IT/security administrator: asset location/maintenance |
| H1 | Household membership and residence in one user's memory | H2 | Household chores in one user's memory |
| H3 | Appointments | H4 | Bills and subscriptions |
| H5 | Purchases and warranties | H6 | Travel plans |
| H7 | Home maintenance | H8 | Personal preferences in user-context memory |
| H9 | Pet care | H10 | Caregiving and family relationships |

## Relation ledger

| Relation ID | Subject -> object contract | Scope | Evidence | Lifecycle / read form | Source-grounded meaning | Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| `member_of` | Person -> Group or Organization | G | D | M / set | Person belongs to the named group, not merely attends its event. | HR |
| `has_role` | Person or Organization -> Role | G | D | M / set | Subject holds the named role; title mention alone is insufficient. | HR |
| `role_scoped_to` | Role -> Group or Organization | G | D | M / set | The particular role assignment applies within the named group. | HR |
| `reports_to` | Person -> Person | P | D | M / set | Explicit reporting line; project collaboration is insufficient. | EM |
| `group_part_of` | Group -> Group or Organization | G | D | M / set | Explicit organizational containment, acyclic under the active graph. | OPS |
| `parent_of` | Person -> Person | P | D | M / set | Source identifies subject as parent of object, with direction preserved. | H10 |
| `partner_of` | Person -> Person | P | D | M / set | Source asserts a current or historical partnership; symmetry is a read mapping, not a second fabricated assertion. | H10 |
| `sibling_of` | Person -> Person | P | D | M / set | Source asserts sibling relationship; symmetry is a read mapping. | H10 |
| `caregiver_for` | Person -> Person | P | D | M / set | Explicit caregiving responsibility, distinct from family relationship. | H10 |
| `project_owned_by` | Project -> Person, Group, or Organization | G | D | M / set | Accountable project owner, not any participant. | PM,H6 |
| `project_advances_goal` | Project -> Goal | G | D | M / set | Project is explicitly connected to the goal. | PM |
| `project_has_work_item` | Project -> WorkItem | G | D | M / set | Work item belongs to this project, not just mentioned alongside it. | SE |
| `work_item_assigned_to` | WorkItem -> Person or Group | G | D | M / set | Explicit assignee; creator and commenter are not assignees. | OPS |
| `work_item_depends_on` | WorkItem -> WorkItem | G | D | M / set | Directed dependency; self-edge and cycle reject. | OPS |
| `work_item_due_on` | WorkItem -> LocalDate | G | D | C / current | Due date, distinct from creation or completion date. | H2 |
| `work_item_status` | WorkItem -> StatusText | G | D | C / current | Explicit current workflow status with catalog-bound vocabulary. | SE |
| `goal_owned_by` | Goal -> Person, Group, or Organization | G | D | M / set | Responsible goal owner, not beneficiary. | EXEC |
| `decision_made_by` | Decision -> Person, Group, or Organization | G | A | M / set | Decision authority, not a participant expressing preference. | EXEC |
| `decision_concerns` | Decision -> Project, WorkItem, Issue, or Goal | G | E | M / set | Decision explicitly addresses the target. | EXEC |
| `decision_supersedes` | Decision -> Decision | G | A | H / history | Later decision explicitly replaces earlier one; self-edge/cycle reject. | EXEC |
| `issue_reported_by` | Issue -> Person or Organization | G | D | M / set | Reporter of issue, distinct from owner or resolver. | SUP |
| `issue_affects` | Issue -> Project, ProductService, Asset, or WorkItem | G | D | M / set | Explicit affected target; a nearby mention does not suffice. | SRE |
| `issue_resolved_by` | Issue -> WorkItem or Decision | G | A | H / history | Named resolution action or decision, not a proposed fix. | QA,H7 |
| `event_participant` | Event -> Person, Group, or Organization | G | E | M / set | Attendee or participant, not merely an invitee unless source confirms attendance. | UX |
| `event_time` | Event -> TimeInterval | G | E | C / current | Scheduled or observed interval with explicit temporal basis. | H3 |
| `event_place` | Event -> Place | G | E | C / current | Event location, not author's location. | H3 |
| `event_concerns` | Event -> Project, WorkItem, Goal, or Issue | G | E | M / set | Event topic or purpose. | MKT |
| `document_authored_by` | Document -> Person or Organization | G | E | M / set | Authorship evidenced by document or explicit attribution. | CONTENT |
| `document_about` | Document -> Project, ProductService, Issue, Decision, Asset, Agreement, or Obligation | G | E | M / set | Referent document materially concerns target; casual citation is insufficient. | DATA |
| `document_version_of` | Document -> Document | G | E | H / history | Source-backed version lineage; self-edge/cycle reject. | CONTENT |
| `document_approved_by` | Document -> Person or Group | P | A | H / history | Explicit approval of this version by authorized approver. | DESIGN |
| `message_sent_by` | Message -> Person or Organization | P | E | H / history | Sender grounded in message metadata or authenticated source. | SUP |
| `message_sent_to` | Message -> Person, Group, or Organization | P | E | M / set | Addressed recipient, distinct from copied text mentions. | SUP |
| `message_about` | Message -> Project, WorkItem, Issue, or Event | P | E | M / set | Message topic grounded in its content. | SUP |
| `product_provided_by` | ProductService -> Person or Organization | G | D | M / set | Supplier/provider of product or service, not customer. | MKT |
| `asset_owned_by` | Asset -> Person, Group, or Organization | P | A | M / set | Ownership, distinct from possession or maintenance. | H5 |
| `asset_located_at` | Asset -> Place | P | D | C / current | Current physical location; movement supersedes prior value. | IT |
| `asset_maintained_by` | Asset -> Person or Organization | G | D | M / set | Maintenance responsibility, distinct from ownership. | IT |
| `agreement_party` | Agreement -> Person or Organization | P | A | M / set | Party to agreement; mere mention in document is insufficient. | LEGAL |
| `agreement_governs` | Agreement -> ProductService, Asset, Project, or Account | P | A | M / set | Agreement explicitly governs target. | CS |
| `account_held_by` | Account -> Person, Group, or Organization | P | A | M / set | Account holder, not user merely accessing account. | SALESOPS |
| `account_with` | Account -> Organization | P | A | C / current | Institution or provider maintaining the account. | SALESOPS |
| `obligation_owed_by` | Obligation -> Person, Group, or Organization | P | A | M / set | Debtor or obligated party. | FIN |
| `obligation_owed_to` | Obligation -> Person or Organization | P | A | M / set | Creditor or beneficiary. | FIN |
| `obligation_due_on` | Obligation -> LocalDate | P | A | C / current | Due date of obligation, not invoice issue date. | H4 |
| `obligation_amount` | Obligation -> Money | P | A | C / current | Amount and currency of this obligation; revision preserves old amount. | FIN |
| `obligation_payment_evidence` | Obligation -> Document | P | E | H / history | Payment receipt or record linked to obligation; evidence does not itself settle it. | FIN |
| `opportunity_owned_by` | Opportunity -> Person or Group | G | D | M / set | Responsible opportunity owner. | SALES |
| `opportunity_with` | Opportunity -> Person or Organization | P | D | M / set | Counterparty to opportunity, not the owner. | SALES |
| `opportunity_stage` | Opportunity -> StatusText | P | D | C / current | Versioned stage value; a proposed stage is not current. | SALES |
| `group_resides_at` | Group -> Place | P | D | C / current | Household or other group residence; visiting is insufficient. | H1 |
| `animal_cared_for_by` | Animal -> Person or Group | P | D | M / set | Explicit care responsibility, distinct from ownership. | H9 |
| `animal_care_task` | Animal -> WorkItem | P | D | M / set | Care task concerning the named animal. | H9 |

There are 53 semantic relation IDs in this ledger. The three preference statements in the parent document are **not** semantic relation IDs. `H8` is the separate, versioned user-context record `Preference` with closed fields `holder: Person`, `topic: ProductService|Asset|Place`, `preference_key: bounded normalized text`, `value: bounded text`, `source_id`, exact assertion span, authenticated source/author, user scope, event and valid time, state, and superseded-record ID when applicable. The stable logical key is `(authenticated user ID, canonical topic ID, normalized preference_key)`; a candidate value is not part of identity. Unknown holder or topic identity, missing assertion span, and agent-generated repetition without an original user assertion cannot create a candidate. Retried observations with the same source digest and logical key coalesce.

The closed lifecycle is `candidate -> confirmed -> superseded|expired`, with `candidate -> rejected` and `confirmed -> retracted` also allowed. Candidate creation requires a source-grounded user assertion or an explicit user form under that user's authenticated scope; an agent's inference, quoted third-party text, or copied assistant summary is ineligible. Confirmation requires the holder's authenticated approval of the exact key, value, and source evidence, recorded as a separate event. A later value requires a new candidate and confirmation and supersedes the prior confirmed record atomically; an explicit holder correction may retract the current value while retaining history. Expiry follows an explicit user-supplied valid-until date or a confirmed revocation, never an inferred timeout. Only a confirmed, current record appears in ordinary protected recall. Historical recall returns authorized versions with confirmation and correction provenance. User-context reads and writes require current holder grant and their own domain policy; a second agent may read only if independently delegated by that holder, and a household member gets no access from a semantic `Household` edge. The semantic fact writer rejects this record shape. A user-context implementation must pass user-assertion, agent-repetition abstention, confirmation, duplicate, correction, expiry, cross-agent and cross-user denial, and historical-read cases through its actual writer and protected reader before H8 counts as shipped. This makes total default coverage 53 semantic relations plus one typed preference record shape.

## Catalog construction and acceptance

The normative source is the versioned typed catalog declaration, not prompt examples or this Markdown table at runtime. Each row compiles to a declaration with explicit subject/object types, value codec, scope/trust/evidence policy, state and temporal rule, read form, aliases, and acceptance fixture references. Generated provider schema, prompt projection, validator/policy bundle, writer and reader capability manifest, package fingerprint, frozen corpus, and CI aggregate all carry the source catalog digest. If a derived artifact is stale or missing, the profile is unavailable rather than loading a partial catalog. A relation counts as shipped only after its type and codec, producer, domain validator, writer, protected reader, assertion/abstention/revision/read cases, restart, and scope denial where applicable all pass through at least one production composition root. For the current codebase, that requires extension of the six-value `EntityType` and five-value `ClaimValueType` registries, the fixed three-predicate profile, source-grounding policies, and generated provider bindings. No current test proves this 53-relation bundle is implemented.

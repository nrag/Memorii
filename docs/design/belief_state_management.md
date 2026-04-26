
#Design: Memorii as a memory-backed decision-state engine

1. Core thesis

Memorii should not be only:

save transcript -> retrieve memories

It should become:

observe agent interaction
  -> persist transcript/events
  -> promote durable memory
  -> detect active work state
  -> update structured state graphs
  -> return memory + state summary
  -> expose next-step tools

This is directly aligned with the BLF paper’s key lesson: keep a structured, evolving belief/state object instead of appending all evidence into a growing context. BLF maintains a semi-structured linguistic belief state with probability, confidence, evidence, and open questions, and updates it in a sequential agent loop. Its ablations show the structured belief state is nearly as important as search access.  ￼

Memorii’s equivalent of BLF’s belief state is not one thing. It is a set of state graphs:

memory plane
execution graph
solver / investigation graph
decision graph
state overlays
promotion lifecycle

The goal is to make these graphs active state, not passive logs.

⸻

2. Current code assessment

What is already good

RuntimeStepService.step(...) already implements a structured loop:

load execution graph
pick execution node
resolve solver run
route observation
build retrieval plan
retrieve memory
call model / accept model output
apply solver update
persist solver nodes, edges, overlays, events
create writeback candidates

That is close to the BLF-style state-update loop.  ￼

The solver output is already schema-first. It includes:

decision
evidence_ids
missing_evidence
next_best_test
rationale_short
confidence_band

and validates important invariants like “supported/refuted decisions require evidence.”  ￼

The verifier prevents unsupported commitments by downgrading decisions when evidence IDs are missing or not available.  ￼

The overlay model already has the right state-search concepts:

belief
status
frontier_priority
is_frontier
unexplained
reopenable

￼

What is still weak

The graph mostly records state. It does not yet strongly drive the agent’s next action.

Belief values are currently coarse constants like 0.8, 0.35, and 1.0, not real state updates based on prior belief, evidence, contradiction, verifier result, or missing evidence.  ￼

The execution graph is task-shaped, but it does not yet carry enough active decision/search state. ExecutionNode has status, acceptance criteria, artifacts, constraints, and timestamps, which is good, but it lacks explicit links to active frontier, current decision state, blocked reason, and next-step recommendations.  ￼

⸻

3. Design goal

Build Memorii as a decision-state engine that works through ordinary agent-memory interfaces.

Hermes does not call:

start execution
try hypothesis
update solver graph

So Memorii should not require that.

Instead:

storage path:
  transcript / provider event
    -> memory save + promotion
    -> detect work state
    -> update execution/solver/decision state if warranted
recall path:
  prefetch(query)
    -> relevant memories
    -> active state summaries
    -> open questions
    -> recommended next steps
tool path:
  agent explicitly asks:
    what should I do next?
    record this outcome
    open/resume work
    update decision

⸻

4. Architecture

Hermes / agent framework
  |
  | provider hooks: sync_turn, memory_write, prefetch, session_end, delegation
  v
Memorii Provider Adapter
  |
  v
AgentEventNormalizer
  |
  v
MemoryPlaneService
  |
  +--> PromotionService
  +--> WorkStateDetector
  +--> WorkStateEngine
         |
         +--> ExecutionStateService
         +--> SolverStateService
         +--> DecisionStateService
         +--> FrontierPlanner
         +--> NextStepEngine

The provider API remains the canonical integration surface.

Runtime-step becomes an internal compatibility path, not the product interface.

⸻

5. New concepts

5.1 Work state

A WorkState represents structured ongoing work detected from an agent session.

class WorkStateKind(str, Enum):
    NONE = "none"
    TASK_EXECUTION = "task_execution"
    INVESTIGATION = "investigation"
    DECISION = "decision"
    RESEARCH = "research"
class WorkStateRecord(BaseModel):
    work_state_id: str
    kind: WorkStateKind
    task_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    title: str
    summary: str
    status: str  # active, paused, resolved, abandoned
    confidence: float
    source_event_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

5.2 Work state detection

Add:

class WorkStateDetectionDecision(BaseModel):
    action: Literal[
        "no_state_update",
        "create_candidate_state",
        "update_existing_state",
        "commit_state_update",
    ]
    kind: WorkStateKind
    confidence: float
    task_id: str | None = None
    work_state_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)

Initial implementation:

rules first:
  explicit task words, tool results, delegation, failure reports
LLM later:
  ambiguous “are we solving/planning/deciding?” cases

Important: if confidence is low, do not create committed state. Store a candidate only.

⸻

6. Storage path

Every sync_turn, memory_write, session_end, delegation, and pre_compress event should follow the same pipeline.

Provider event
  -> normalize into AgentEventEnvelope
  -> append transcript/event
  -> create promotion candidates
  -> run promotion policy
  -> run WorkStateDetector
  -> update relevant state graph
  -> persist trace

6.1 Agent event envelope

class AgentEventEnvelope(BaseModel):
    event_id: str
    provider: str  # hermes, openclaw, custom
    operation: str # turn_complete, memory_write, delegation_result, session_end, pre_compress
    session_id: str | None = None
    parent_session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    content: str
    assistant_content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime

6.2 Storage behavior

sync_turn

Do:

save raw transcript
stage episodic candidate if useful
run promotion
detect work state
update state graph if confidence allows

Do not:

blindly infer semantic/user memory
blindly create solver graph

memory_write

Do:

stage semantic/user/episodic candidate
run promotion
optionally update work state if memory write references task progress

delegation

Do:

save delegation result
create episodic candidate
if active work state exists:
    add observation node to solver/execution graph

session_end / pre_compress

Do:

summarize state
preserve open questions
create promotion candidates
mark paused work states

⸻

7. Recall path

prefetch(query, session_id) should return a RecallStateBundle internally.

class RecallStateBundle(BaseModel):
    query: str
    memory_items: list[RetrievedMemoryItem]
    active_work_states: list[WorkStateSummary]
    open_questions: list[str]
    constraints: list[str]
    recent_progress: list[str]
    recommended_next_steps: list[NextStepRecommendation]
    trace: dict[str, Any]

The provider can format this as text for Hermes:

Relevant memory:
- ...
Current state:
- Active task: ...
- Current decision: ...
- Open questions: ...
Recommended next step:
- ...

This means recall is no longer just “top K memory chunks.” It becomes “top K memories plus current structured state.”

⸻

8. Tool path

Expose tools for agents that want direct state guidance.

8.1 memorii_get_next_step

Input:

{
  "query": "what should I do next?",
  "session_id": "session:123",
  "task_id": null
}

Output:

{
  "kind": "investigation",
  "next_step": {
    "action_type": "inspect_file",
    "description": "Check the provider prefetch trace for missing promoted memory.",
    "expected_evidence": "ranked ids include promoted record",
    "success_condition": "promoted record appears in top_k",
    "failure_condition": "trace excludes committed memory"
  },
  "why": "Highest-priority unresolved frontier node",
  "evidence_ids": ["mem:...", "solver:..."],
  "confidence": "medium"
}

8.2 memorii_record_progress

Input:

{
  "task_id": "task:123",
  "content": "BM25 reranker was merged and tests passed.",
  "evidence_ids": ["pr:29"]
}

8.3 memorii_record_outcome

Input:

{
  "task_id": "task:123",
  "outcome": "supported|refuted|needs_test",
  "rationale": "...",
  "evidence_ids": ["..."]
}

8.4 memorii_get_state_summary

Input:

{
  "session_id": "session:123",
  "task_id": "optional"
}

Output:

{
  "active_states": [...],
  "open_questions": [...],
  "frontier": [...],
  "recent_progress": [...]
}

⸻

9. State graph design

9.1 Execution graph

Keep current ExecutionNode, but add optional active-state metadata:

class ExecutionNodeState(BaseModel):
    execution_node_id: str
    active_solver_run_id: str | None = None
    active_decision_state_id: str | None = None
    current_frontier_node_ids: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    next_step_id: str | None = None
    last_progress_summary: str | None = None

9.2 Solver graph

Keep current solver graph. Add structured next-test.

class NextTestAction(BaseModel):
    action_type: Literal[
        "inspect_file",
        "run_command",
        "ask_user",
        "search_memory",
        "call_tool",
        "delegate",
        "wait",
    ]
    description: str
    expected_evidence: str | None = None
    success_condition: str | None = None
    failure_condition: str | None = None
    required_tool: str | None = None
    target_ref: str | None = None

Extend SolverDecisionOutput:

next_test_action: NextTestAction | None = None

Keep next_best_test: str | None for compatibility.

9.3 Decision graph

Add a new graph type for choices/tradeoffs.

class DecisionState(BaseModel):
    decision_id: str
    question: str
    options: list[DecisionOption]
    criteria: list[DecisionCriterion]
    evidence_for: list[EvidenceRef]
    evidence_against: list[EvidenceRef]
    constraints: list[str]
    current_recommendation: str | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    status: Literal["open", "decided", "abandoned"]

This prevents forcing all decisions into debugging-style solver graphs.

⸻

10. Frontier and next-step engine

Add:

class FrontierPlanner:
    def select_next_step(
        self,
        *,
        work_state_id: str,
        execution_state: ExecutionNodeState | None,
        solver_overlay: SolverOverlayVersion | None,
        decision_state: DecisionState | None,
        memory_context: list[RetrievedMemoryItem],
    ) -> NextStepRecommendation:
        ...

Selection rule v1:

1. unresolved NEEDS_TEST solver node
2. unexplained active node
3. decision state with unresolved criteria
4. blocked execution node
5. stale/reopenable node with new contradictory evidence
6. otherwise summarize progress and ask for next user input

⸻

11. Belief update

Replace fixed overlay beliefs with deterministic update v1.

def update_belief(
    prior: float,
    decision: SolverDecision,
    evidence_count: int,
    missing_count: int,
    verifier_downgraded: bool,
    conflict_count: int,
) -> float:
    delta = 0.0
    if decision == SolverDecision.SUPPORTED:
        delta += 0.25
    elif decision == SolverDecision.REFUTED:
        delta -= 0.25
    elif decision == SolverDecision.NEEDS_TEST:
        delta -= 0.05
    elif decision == SolverDecision.INSUFFICIENT_EVIDENCE:
        delta -= 0.10
    delta += min(0.15, 0.05 * evidence_count)
    delta -= min(0.20, 0.05 * missing_count)
    delta -= min(0.20, 0.10 * conflict_count)
    if verifier_downgraded:
        delta -= 0.20
    return max(0.0, min(1.0, prior + delta))

This is not final science. It is a deterministic, testable baseline.

Later, LLM or learned models can propose updates, but the executor still applies them deterministically.

⸻

12. LLM role

Do not let the LLM mutate state directly.

LLM produces structured proposals:

class WorkStateUpdateProposal(BaseModel):
    update_type: Literal[
        "none",
        "create_task",
        "update_task",
        "create_investigation",
        "update_investigation",
        "create_decision",
        "update_decision",
    ]
    confidence: float
    title: str | None = None
    summary: str | None = None
    hypotheses: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_test_action: NextTestAction | None = None
    evidence_event_ids: list[str] = Field(default_factory=list)

Then deterministic code validates and applies.

This is exactly the BLF lesson: LLM updates structured state; the system controls persistence and calibration.  ￼

⸻

13. Implementation plan

PR 1: shared models and passive state detection

Add:

core/work_state/models.py
core/work_state/detector.py
core/work_state/service.py

Implement:

* AgentEventEnvelope
* WorkStateKind
* WorkStateRecord
* WorkStateDetectionDecision
* deterministic detector v1
* store detection trace

Acceptance tests:

* generic chat creates no state
* explicit task discussion creates candidate task state
* tool failure creates investigation state
* low confidence does not commit state

PR 2: recall bundle

Add:

* RecallStateBundle
* provider prefetch includes active work summaries
* no behavior change when no active state exists

Acceptance tests:

* prefetch returns memory only if no state
* prefetch returns memory + active state when task exists
* trace shows state sources

PR 3: tool interface

Add provider tools:

* memorii_get_next_step
* memorii_get_state_summary
* memorii_record_progress
* memorii_record_outcome

Acceptance tests:

* tools appear in get_tool_schemas
* handle_tool_call dispatches correctly
* unknown tool returns clear error

PR 4: structured next-test action

Add:

* NextTestAction
* extend solver output
* maintain backward compatibility with next_best_test

Acceptance tests:

* NEEDS_TEST requires either string next test or structured next action
* invalid structured next action fails schema
* runtime result includes structured next action

PR 5: frontier planner

Add:

* FrontierPlanner
* overlay-based next-step selection
* use is_frontier, frontier_priority, unexplained, reopenable

Acceptance tests:

* highest-priority frontier selected
* resolved nodes not selected
* reopenable stale node selected when new evidence exists

PR 6: deterministic belief update

Replace fixed overlay beliefs with update function.

Acceptance tests:

* support with evidence increases belief
* refutation lowers belief
* verifier downgrade lowers belief
* missing evidence keeps frontier open

PR 7: LLM state proposal interface

Add interface only, not full production model dependency:

class WorkStateModelProvider(Protocol):
    def propose_update(input: WorkStateModelInput) -> WorkStateUpdateProposal:
        ...

Acceptance tests use fake provider.

⸻

14. Safety rules

1. Generic transcript must not create committed task/solver/decision state without enough evidence.
2. Agent tool calls can explicitly create/update state.
3. Non-primary delegated contexts should not promote durable user memory by default.
4. LLM proposals must be schema validated.
5. Unsupported evidence IDs must downgrade commitments.
6. State updates must preserve lineage to event IDs.
7. Old state should not be overwritten in place; create new overlay/version.

⸻

15. Success criteria

This phase is complete when Memorii can do this:

User and agent discuss a task over several turns.
Memorii stores transcript and promotes durable memories.
Memorii detects an active task or investigation.
Memorii creates/updates execution and solver state.
Prefetch returns relevant memories plus current state.
Agent calls memorii_get_next_step.
Memorii returns the highest-value next action with evidence and rationale.

This moves Memorii from a memory harness to a real memory-backed decision-state system.
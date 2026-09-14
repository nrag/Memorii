# Memorii: Persistent Cognitive State & Learning Layer

## 1. Product Goal

Memorii provides persistent state, memory, execution control, and learning for long-running AI agents.

The core design principle is:

> **Execution state is not memory. Memory informs execution, while an authoritative control layer governs progress, validation, recovery, and completion.**

Memorii should allow agents to:

- Resume long-running work without reconstructing state from transcripts.
- Know what work remains and what conditions must be satisfied.
- Retrieve or activate the right knowledge for the current execution state.
- Reason explicitly through uncertain problems when necessary.
- Learn from prior executions.
- Convert repeated lessons into both reusable knowledge and enforceable runtime behavior.

---

## 2. Architecture

Memorii has four first-class planes.

### 2.1 Execution Control Plane

Authoritative source of truth for task execution.

Responsibilities:

- Current execution state.
- Outstanding obligations.
- State transitions.
- Preconditions and exit conditions.
- Verification checks.
- Evidence and completion receipts.
- Checkpoints and durable resume.
- Failure recovery.
- Stop conditions.
- Task dependencies when required.

A state is both:

1. **A context boundary** — entering the state activates relevant information.
2. **A contract boundary** — leaving the state requires defined obligations to pass.

Example:

```text
Plan → Execute → Verify → Complete
                  ↓
                Repair
                  ↓
                Verify
```

---

### 2.2 Solver Plane

Used only when the correct next action is uncertain.

Responsibilities:

- Hypotheses.
- Observations.
- Beliefs/confidence.
- Alternative solution branches.
- Experiments.
- Search frontier.
- Decisions and rejected alternatives.

The Solver Plane is subordinate to execution control.

Example:

```text
Execute
   ↓
complex uncertainty
   ↓
Solver Graph
 H1 ─ H2 ─ H3
  ↘ evidence ↙
     beliefs
```

Not every task should create a Solver Graph.

---

### 2.3 Knowledge & Experience Plane

Stores reusable information across tasks and sessions.

Memory domains:

- Semantic knowledge.
- Episodic memory.
- User preferences/context.
- Transcript history.
- Skills and domain knowledge.

Memory must support two activation mechanisms.

#### State-triggered activation

Deterministic information activated when entering a known state.

Examples:

- Verification requirements.
- Previous failures in this task.
- Applicable procedures.
- Required artifacts.

#### Search-triggered retrieval

Semantic retrieval for information whose relevance cannot be known deterministically.

Examples:

- Similar past incidents.
- Related technical knowledge.
- Prior decisions.
- User-specific context.

State-triggered activation should be preferred for mandatory procedural information.

---

### 2.4 Learning & Consolidation Plane

Converts execution experience into durable improvements.

The system must learn two kinds of artifacts.

#### Knowledge artifacts

Examples:

- Semantic facts.
- Episodic lessons.
- Skills.
- Reusable strategies.

#### Control artifacts

Examples:

- New validation checks.
- Transition guards.
- Entry hooks.
- Recovery procedures.
- Required evidence.
- Stop conditions.
- Routing rules.

Example:

```text
Failure
  ↓
Root-cause classification
  ↓
Candidate lesson
  ↓
┌───────────────┬─────────────────┐
│ Knowledge     │ Runtime control │
│ "remember X"  │ "enforce X"     │
└───────────────┴─────────────────┘
```

Control changes must not become active immediately.

They follow:

```text
Candidate
   ↓
support / counterexamples
   ↓
shadow evaluation
   ↓
regression testing
   ↓
promotion
   ↓
Committed control
```

---

## 3. Execution Complexity Levels

Memorii must avoid imposing heavy orchestration on every task.

### Level 0 — Stateless

Use normal model execution.

Suitable for:

- Simple questions.
- One-shot transformations.
- Low-cost, easily retryable tasks.

### Level 1 — Coarse Execution State

```text
Plan → Execute → Verify → Complete
```

Default for multi-step agent tasks.

### Level 2 — Structured Execution Graph

Adds:

- Work items.
- Dependencies.
- Artifacts.
- Invariants.
- Risks.
- Tests.
- Blockers.

Use for long-running or multi-component work.

### Level 3 — Solver Graph

Adds explicit hypothesis/search state.

Use only for problems requiring:

- Investigation.
- Backtracking.
- Competing explanations.
- Experiments.
- Significant uncertainty.

The runtime should escalate complexity only when needed.

---

## 4. Core Runtime Requirements

### R1. Authoritative State

The model must never infer authoritative execution state solely from conversation history.

State changes follow:

```text
Model proposes
      ↓
Runtime validates
      ↓
Runtime commits
```

---

### R2. Durable Resume

After interruption, the agent must be able to reconstruct:

- Current state.
- Completed obligations.
- Remaining work.
- Evidence.
- Active blockers.
- Relevant memories.
- Solver state, when present.

without replaying the full transcript.

---

### R3. Checked Transitions

Transitions may have:

- Preconditions.
- Required artifacts.
- Deterministic validators.
- External verification.
- Evidence requirements.
- LLM-based checks only where deterministic verification is unavailable.

The agent cannot declare completion when mandatory checks fail.

---

### R4. Context Refresh on State Entry

Entering a state triggers appropriate context activation.

Example:

```text
ENTER VERIFY
  ↓
load requirements
load produced artifacts
load relevant previous failures
activate verification procedure
  ↓
agent executes
```

Mandatory state-specific information must not depend on semantic retrieval succeeding.

---

### R5. Evidence-backed Completion

Completion claims must reference evidence where practical.

Examples:

- Test output.
- Tool execution receipt.
- Artifact ID.
- External observation.
- Validator result.

---

### R6. Procedural Learning

Repeated failures or successful strategies can become runtime behavior.

Example:

Instead of remembering:

> Preserve the database before repair.

Memorii should be capable of learning:

```text
repair.precondition:
    preservation_snapshot_exists == true
```

---

### R7. Controlled Promotion

No lesson becomes a global rule solely because it worked once.

Every learned control must track:

- Source episodes.
- Scope.
- Support count.
- Counterexamples.
- Confidence.
- Evaluation results.
- Version.
- Rollback history.

---

## 5. Core Objects

### ExecutionState

```yaml
id:
type:
status:
entered_at:
context_refs:
obligations:
allowed_transitions:
entry_hooks:
exit_checks:
evidence_refs:
```

### Transition

```yaml
source:
destination:
preconditions:
checks:
recovery_transition:
```

### ExecutionArtifact

```yaml
id:
type:
producer:
state:
content_ref:
verification_status:
evidence_refs:
```

### SolverState

```yaml
hypotheses:
observations:
beliefs:
frontier:
decisions:
open_questions:
```

### MemoryItem

```yaml
type:
content:
scope:
source:
confidence:
activation_conditions:
```

### CandidatePractice

```yaml
lesson:
scope:
source_episodes:
support_count:
counterexamples:
proposed_control_change:
evaluation_status:
promotion_status:
```

---

## 6. Product Principles

1. **State over transcript reconstruction.**
2. **Contracts over model self-attestation.**
3. **Deterministic activation for mandatory context.**
4. **Semantic retrieval for opportunistic context.**
5. **Reasoning freedom inside coarse control boundaries.**
6. **Use the lightest orchestration that works.**
7. **Store evidence, not only conclusions.**
8. **Learn behavior, not only text.**
9. **Treat learned procedures as candidates until validated.**
10. **Keep execution state, solver state, and long-term memory distinct.**

---

## 7. Non-Goals

V0 does not attempt to:

- Turn every model thought into a graph node.
- Encode every task as a complex workflow.
- Replace the underlying model's reasoning loop.
- Automatically promote every successful behavior into policy.
- Guarantee correctness from LLM self-evaluation.
- Treat transcripts as authoritative state.

---

## 8. V0 Scope

V0 should implement:

1. Coarse execution state machine.
2. Durable execution checkpoints.
3. Candidate → validate → commit state changes.
4. State entry hooks.
5. Transition checks.
6. Evidence-backed completion.
7. Semantic + episodic memory retrieval.
8. State-triggered memory activation.
9. Optional Solver Graph integration.
10. Failure → CandidatePractice generation.
11. Manual or evaluation-gated promotion of learned practices.

Rich execution DAGs and automatic control-policy learning can follow after V0.

---

## 9. Success Metrics

Evaluate Memorii against the same model without Memorii.

Primary metrics:

- Long-horizon task completion rate.
- Single-run success rate.
- Premature-completion rate.
- Missed-obligation rate.
- Recovery success after interruption.
- Context/token consumption.
- Number of repeated failures across runs.
- Improvement from learned practices on future tasks.

Critically, evaluations should separately ablate:

1. Persistent execution state.
2. Verification checks.
3. State-triggered context activation.
4. Long-term memory.
5. Procedural learning.
6. Solver Graphs.
7. Retry/test-time-compute effects.

This is necessary to distinguish genuine state/memory gains from improvements caused simply by additional attempts or stronger harnessing.
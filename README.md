# Memorii

Memorii is a **framework-neutral memory plane for agent systems**.

It is built for agents that need more than transcript history and vector recall. Memorii separates different kinds of memory, controls how information is written, and lets an agent resume work with explicit execution state and task-local reasoning state.

> Memorii lets agents remember work, not just conversations.

---

## What Memorii is

Memorii is:

- a **typed multi-memory system**
- a **memory router** that decides where new information should go
- a **retrieval planner** that decides which memories matter for the current step
- a **persistent execution graph** for tracking work, dependencies, artifacts, tests, and statuses
- a **solver graph** for task-local reasoning, debugging, hypothesis testing, and branch revision
- an **event-sourced system** with replay and deterministic reconstruction
- a **runtime API** for starting, stepping, resuming, and inspecting tasks

It separates memory into distinct domains:

- transcript memory  
- semantic memory  
- episodic memory  
- user memory  
- execution plan memory  
- solver / state-space search memory  

That separation is the core idea.

---

## What Memorii is not

Memorii is **not**:

- a vector database  
- a chat history wrapper  
- a RAG library  
- a single unified memory graph  
- a system that writes model guesses directly into long-term memory  

Most systems flatten memory into “stuff you retrieve.”  
Memorii treats memory as **part of the agent runtime**.

---

## Architecture Overview

### Memory Plane + Execution vs Solver Graph

<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/44d7b3ee-1559-49d9-87e3-b070bb8185aa" />

---

## Benchmark report example

If you want a concrete benchmark artifact for documentation/README usage, see:

- Canonical JSON report: `docs/examples/benchmarks/hotpotqa_sample_report.json`
- Markdown summary: `docs/examples/benchmarks/hotpotqa_sample_report.md`

These files are generated from the local deterministic HotpotQA sample benchmark path (`seed=7`, `subset_size=2`).

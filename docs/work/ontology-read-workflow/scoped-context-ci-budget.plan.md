# Fit the scoped-context gate to the installed journey

- Work type: testing
- Delivery fidelity: Level 2
- Status: active
- Coordinator: Codex
- Parent WorkPlan: [ontology read workflow](implementation.plan.md)
- Last updated: 2026-11-27

The installed workflow in the 146-case Scoped Context Integration gate
provisions and reopens a v8 store through the real bindings. The exact local
suite passed in 472.80 seconds, including 464.89 seconds for the installed
case. In [PR run 46079693423](https://github.com/nrag/Memorii/actions/runs/46079693423/job/140775551397),
dependency setup left 8 minutes 12 seconds before the job was canceled
at its 10-minute limit. Pytest had collected all 146 cases.

Set the job limit to 20 minutes, the same budget as Durable Storage
Integration. Keep its Python version, pytest arguments, job identity,
selection, warnings-as-errors policy, triggers and aggregate dependencies.
This dedicated integration job owns installed-host evidence outside the
duration-balanced unit shards. Refresh the workflow pin for Package Smoke.

## Next action

Confirm the hosted job completes under the new budget and record the
GitHub run and executed revision.

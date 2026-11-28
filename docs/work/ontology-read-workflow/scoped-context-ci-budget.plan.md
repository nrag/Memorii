# Fit the scoped-context gate to the installed journey

- Work ID: scoped-context-ci-budget
- Work type: testing
- Delivery fidelity: Level 2
- Status: complete (Level 2)
- Coordinator: Codex
- Parent WorkPlan: [ontology read workflow](implementation.plan.md)
- Created: 2026-11-27
- Last updated: 2026-11-27

The installed workflow in the 146-case Scoped Context Integration gate
provisions and reopens a v8 store through the real bindings. The exact local
suite passed in 472.80 seconds, including 464.89 seconds for the installed
case. In [PR run 46079693423](https://github.com/nrag/Memorii/actions/runs/46079693423/job/140775551397),
dependency setup left 8 minutes 12 seconds before the job was canceled
at its 10-minute limit. Pytest had collected all 146 cases.

The initial trial used 20 minutes. The repository's workflow-structure
contract caps this job at 15 minutes. Set the final limit to 15 minutes
and record 780 seconds of budget with 120 seconds of headroom in the
dedicated timing-owner ledger. Keep the Python version, pytest arguments,
job identity, selection, warnings-as-errors policy, triggers and
aggregate dependencies.
This dedicated integration job owns installed-host evidence outside the
duration-balanced unit shards. Refresh the workflow pin for Package Smoke.

The [hosted timing trial](https://github.com/nrag/Memorii/actions/runs/46082294793/job/140783782353)
at `95a95749` passed all 146 cases in 615.20 seconds. The complete job
took 12 minutes 32 seconds, leaving 148 seconds under the 15-minute cap.
The updated timing ledger and workflow-structure checks passed locally.
Independent review confirmed unchanged test selection, warning handling
and aggregation.

## Hosted result

[PR Gates run 46083808916](https://github.com/nrag/Memorii/actions/runs/46083808916/job/140788634761)
passed 146 scoped-context tests in 486.74 seconds with the 15-minute cap.
The complete job took 10 minutes. PR head `524fd8c6` was tested on
`refs/pull/126/merge` at `5386369702013cd0d859be33331227fe39624fbd`
against main `885c7db7`. Package Smoke and Static Analysis passed in the
same workflow. The parent plan tracks the rest of the PR gate results.

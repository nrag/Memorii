# Prompt Contracts

## Summary

Memorii prompt behavior is governed by checked-in YAML prompt contracts, strict
JSON schemas, typed adapter inputs, and no-leakage tests. These contracts are the
runtime and benchmark source of truth.

The executable manifest in `memorii.core.prompts.manifest` records ownership,
representative render inputs, fake valid outputs, intentionally invalid outputs,
and no-leakage rules for every checked-in prompt. See
`docs/design/prompt_contracts_and_offline_prompt_search_policy.md` for the
prompt-change gate and offline prompt-search policy.

Prompt optimization frameworks are out of scope for v1. Any future prompt-search
tooling must export accepted prompt candidates back into the YAML contract system
before evaluation or shipping.

## Contract Ownership

Each production or benchmark prompt must have:

- a stable prompt ref such as `memory_extraction:v1`;
- a YAML contract under `prompts/`;
- an owning adapter or runner path;
- a strict output schema compatible with structured output providers;
- representative render variables for tests;
- a fake valid output fixture or equivalent deterministic test payload;
- no-leakage tests for oracle fields, hidden IDs, expected IDs, judge outputs,
  API keys, and benchmark-only excluded IDs where relevant.

The prompt renderer and registry remain the public API for loading and rendering
prompts. Runtime code should not bypass these APIs.

## Out Of Scope For V1

Do not add prompt-optimization frameworks to the runtime, benchmark runner, or
prompt registry path in v1. In particular:

- do not import external prompt-optimization frameworks from runtime or benchmark
  modules;
- do not treat generated signatures or generated prompt variants as schema
  source of truth;
- do not let generated prompt variants bypass prompt-contract tests;
- do not add prompt-optimization frameworks as core dependencies.

## Acceptance Gate For Any Prompt Change

A prompt change is acceptable only when:

- the YAML validates as a prompt contract;
- the prompt renders with representative variables;
- the output schema is strict and parseable;
- fake valid output passes;
- intentionally invalid output fails;
- rendered live prompts do not include forbidden oracle or hidden fields;
- relevant dry-run benchmark gates remain green.

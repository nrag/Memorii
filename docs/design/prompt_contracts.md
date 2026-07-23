# Prompt Contracts

## Summary

Memorii prompt behavior is governed by checked-in YAML prompt contracts, strict
JSON schemas, typed adapter inputs, and no-leakage tests. These contracts are the
runtime and benchmark source of truth.

The runtime registry in `memorii.core.prompts.runtime_manifest` records only the
ownership, expected variables, and visibility policy needed to load a prompt in
production. The conformance manifest in `memorii.core.prompts.manifest` adds
representative render inputs, fake valid outputs, intentionally invalid outputs,
and adversarial no-leakage rules for tests and audits. Production adapters do
not import the conformance manifest. See
`docs/design/prompt_contracts_and_offline_prompt_search_policy.md` for the
prompt-change gate and offline prompt-search policy.

Prompt optimization frameworks are out of scope. Any future prompt-search
tooling must export accepted prompt candidates back into the YAML contract system
before evaluation or shipping.

## Canonical Redaction Boundary

Prompt variables are recursively redacted by one production-owned sanitizer
before rendering and trace construction. The sanitizer applies the YAML
redaction policy to nested mappings and sequences, rejects non-string mapping
keys, and returns a detached value so downstream mutation cannot recover the
original secret. Prompt runners and trace builders use this same boundary;
benchmark code does not maintain a parallel allowlist or test-only sanitizer.
Adversarial tests cover nested API keys, tokens, credentials, and mixed
container shapes.

## Contract Ownership

Each production or benchmark prompt must have:

- a stable prompt ref such as `memory_extraction:v1`;
- a package-owned YAML contract under `memorii/memorii/prompts/`;
- an owning adapter or runner path;
- a strict output schema compatible with structured output providers;
- representative render variables for tests;
- a fake valid output fixture or equivalent deterministic test payload;
- no-leakage tests for oracle fields, hidden IDs, expected IDs, judge outputs,
  API keys, and benchmark-only excluded IDs where relevant.

The prompt renderer and registry remain the public API for loading and rendering
prompts. Runtime code should not bypass these APIs.

## Out Of Scope

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

## Atomic Registration

`PromptRegistry.load` returns a `RegisteredPromptContract`, which binds the YAML
prompt, output schema, owning adapter, redaction/no-leakage policy, and a digest
over that complete registration. `PromptRenderer` accepts only this registered
object. It does not own a second manifest and rejects a contract whose prompt
identity, policy, or content changed after registration. Prompt text, schema,
and security policy therefore form one deployable decision package.

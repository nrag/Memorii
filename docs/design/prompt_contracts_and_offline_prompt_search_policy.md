# Prompt Contracts And Offline Prompt Search Policy

## Summary

Memorii prompts are governed by checked-in YAML prompt contracts plus two
deliberately separate registries. `memorii.core.prompts.runtime_manifest`
contains the minimal ownership, input-variable, and visibility policy required
by production. `memorii.core.prompts.manifest` is the conformance registry and
adds representative render variables, fake valid outputs, intentionally invalid
outputs, and no-leakage rules for every prompt YAML file.

The YAML contract remains the source of truth for runtime rendering and
structured-output schemas. The conformance manifest is a test and audit layer;
production adapters must not import it, and it must not replace
`PromptRegistry` or `PromptRenderer`.

## Required Prompt Change Gate

Every production or benchmark prompt must pass these checks before a change can
land:

- the prompt YAML validates as `PromptContract`;
- the prompt is covered by `PromptContractManifestEntry`;
- the manifest input variables exactly match the YAML `input_schema.required`;
- representative variables render successfully through `PromptRenderer`;
- the output schema is recursively strict for object payloads;
- the fake valid output parses against the YAML output schema;
- the fake invalid output fails schema validation;
- rendered representative prompts contain no forbidden oracle, hidden, judge, or
  secret fragments.

These tests intentionally exercise the public prompt loading and rendering APIs.
Runtime and benchmark code should continue to use `PromptRegistry` and
`PromptRenderer` directly.

## No-Leakage Policy

Benchmark prompts must never receive hidden graph items, oracle expected IDs,
oracle answers, excluded expected IDs, judge votes, or hidden distractor metadata
in live paths. Runtime prompts must never receive API keys, tokens, passwords,
authorization headers, cookies, or other credential material.

The manifest checks representative prompt variables and rendered prompt text for
those risks. This is not a license for adapters to pass unsanitized payloads.
Adapters and candidate-card builders are still responsible for constructing
model-facing inputs that exclude oracle and hidden state.

## Offline Prompt Search

Prompt optimization or prompt-search tooling is out of scope for the core
runtime and benchmark path in v1. Future offline tools may propose prompt
variants, but accepted variants must be exported back into the YAML prompt
contract system and pass the same manifest, render, fake-output, no-leakage, sim,
and runtime gates before use.

No prompt-search framework should be imported by Memorii runtime code, benchmark
runners, prompt registry, prompt renderer, or prompt manifest.

## Operational Guidance

When adding a new prompt:

1. Add the YAML contract under `memorii/memorii/prompts/<prompt_id>/<version>.yaml`.
2. Add a `PromptContractManifestEntry` for the prompt.
3. Include a minimal representative input that reflects the live adapter payload.
4. Include a fake valid output that satisfies the prompt output schema.
5. Keep intentionally invalid output invalid.
6. Add prompt-specific leakage rules when the prompt handles benchmark or oracle
   derived context.
7. Run `python -m pytest memorii/tests/unit/core/test_prompt_contracts.py -p no:cacheprovider`.

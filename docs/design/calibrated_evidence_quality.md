# Calibrated Evidence Quality Design

## Purpose

The current belief-update eval is now useful because it separates simple rule behavior from semantic reasoning:

```text
rule   43/61
llm    61/61
hybrid 61/61
```

That shape should be preserved as the regression baseline. The 18 rule failures are intentional semantic traps around duplicate evidence, wrong entity linking, stale evidence, partial tool failures, delayed corrections, and soft falsification.

The next architecture step is to stop encoding every new trap as another prompt threshold. Prompt examples are still useful as calibration anchors, but final belief movement should come from explicit evidence-quality dimensions and deterministic belief math.

## Problem

`BeliefUpdateContext` currently gives the updater mostly scalar counts:

```text
decision
prior_belief
evidence_count
missing_evidence_count
verifier_downgraded
conflict_count
```

Those fields are not enough to distinguish:

- three independent observations vs. three copies of one log line
- a relevant source vs. a wrong-customer source
- current evidence vs. stale pre-rewrite evidence
- a failed search returning no results vs. a successful search proving absence
- a hard refutation vs. soft falsification with missing logs

The LLM can infer these distinctions from text, but if each case maps directly to a one-off prompt cap, the system becomes hard to maintain.

## Design

Add an evidence-quality layer between raw solver decision and final belief update:

```text
BeliefUpdateContext
  -> EvidenceQualityScorer
  -> EvidenceQualityAssessment
  -> CalibratedBeliefUpdater
  -> BeliefUpdateDecision
```

The LLM may be used to extract semantic quality dimensions, but the belief update itself should be deterministic once those dimensions are known.

## Evidence Quality Assessment

Introduce a typed assessment model:

```python
class EvidenceQualityAssessment(BaseModel):
    relevance: EvidenceQualityBand
    independence: EvidenceQualityBand
    entity_alignment: EntityAlignment
    temporal_freshness: TemporalFreshness
    observability: Observability
    source_reliability: EvidenceQualityBand
    contradiction_status: ContradictionStatus
    support_strength: EvidenceStrength
    refutation_strength: EvidenceStrength
    requires_judge_review: bool
    reason_codes: list[str]
    rationale: str
```

Recommended enums:

```text
EvidenceQualityBand:
  high, medium, low, invalid

EntityAlignment:
  aligned, ambiguous, wrong_entity

TemporalFreshness:
  current, time_bound, stale, superseded

Observability:
  complete, partial, failed_tool, missing

ContradictionStatus:
  none, conflict_present, delayed_correction, superseded

EvidenceStrength:
  strong, moderate, weak, none
```

The assessment should be explicit about why evidence is discounted. For example, a wrong-customer ticket should set `entity_alignment=wrong_entity`, not merely lower confidence.

## Deterministic Belief Math

After assessment, belief movement should be computed from a small set of rules:

```text
clean support:
  increase based on support_strength

clean refutation:
  decrease based on refutation_strength

wrong entity:
  no meaningful support increase, require review

duplicate/non-independent evidence:
  count as weak support at most

stale or superseded evidence:
  cap support and require review

failed-tool absence:
  do not treat absence as refutation

soft falsification:
  decrease modestly and require review
```

The numeric thresholds in evals should remain, but they should test the deterministic updater, not become policy scattered through prompt prose.

## Provider Responsibilities

### Rule Provider

The rule provider can start with conservative defaults from existing scalar fields:

- clean `SUPPORTED` with enough evidence -> high relevance, medium/high support
- `REFUTED` with enough evidence -> high relevance, medium/high refutation
- missing evidence, verifier downgrade, or conflicts -> lower quality and review

It will not detect most semantic traps. That is acceptable and should preserve the current `43/61` rule baseline until a better deterministic extractor exists.

### LLM Provider

The LLM provider should produce an `EvidenceQualityAssessment` from:

- scalar context fields
- evidence and missing-evidence summaries
- scenario metadata
- hypothesis text

The LLM should not directly invent final belief thresholds. It should classify the evidence quality dimensions and explain the classification.

### Hybrid Provider

Hybrid should route simple low-risk cases to rule logic and semantic-risk cases to the LLM assessment path.

Semantic-risk signals include:

- `related_memory_ids` or merge/supersession hints
- wrong entity or ambiguous entity mentions
- stale/superseded/corrected evidence
- duplicate/copied evidence
- partial or failed tool observations
- soft falsification
- multiple plausible hypotheses
- conflict or verifier downgrade

## Eval Strategy

Keep the current 61-case benchmark as the baseline.

Expected behavior:

```text
rule   43/61
llm    61/61
hybrid 61/61
```

Add a new assessment-level eval before changing belief math:

```text
snapshot -> EvidenceQualityAssessment -> expected dimensions
```

Example expected dimensions:

```json
{
  "entity_alignment": "wrong_entity",
  "independence": "low",
  "support_strength": "weak",
  "requires_judge_review": true
}
```

This lets new adversarial cases test dimensions first. Only after the assessment is correct should the final belief score be judged.

## Migration Plan

### Phase 1: Models and Deterministic Updater

Add:

- `memorii.core.belief.evidence_quality`
- `EvidenceQualityAssessment`
- deterministic `calibrated_belief_update(...)`
- unit tests for known dimensions and belief bands

Keep existing providers unchanged.

### Phase 2: Rule Assessment Provider

Add a rule-based assessment provider that maps current scalar fields into conservative quality dimensions.

Expected result:

- unit behavior equivalent or close to current rule scorer
- current 61-case rule baseline remains intentionally discriminative

### Phase 3: LLM Assessment Prompt

Add a prompt that returns only `EvidenceQualityAssessment`.

The final belief update becomes:

```text
LLM assessment + deterministic updater
```

not:

```text
LLM final belief number
```

### Phase 4: Hybrid Integration

Route hybrid semantic-risk cases through LLM assessment, then deterministic updater.

Keep trace output for both:

- quality assessment
- final belief update

### Phase 5: Expand Golden Set

Future adversarial cases should specify expected quality dimensions first, then final belief constraints second.

This prevents benchmark growth from becoming a sequence of one-off threshold patches.

## Open Questions

- Should `EvidenceQualityAssessment` live inside `BeliefUpdateContext`, or should it be a sibling artifact traced separately?
- Should final belief math use fixed lookup tables first, or a small calibrated regression later?
- Should promotion decisions use the same evidence-quality layer for duplicate/stale/wrong-entity handling?
- How much of source lineage can be extracted deterministically before asking an LLM?

## Recommendation

Start with models and assessment-level evals. Do not immediately replace the current passing belief provider path. Once the assessment layer passes the 61-case semantic traps, move LLM/hybrid belief update to:

```text
semantic assessment -> deterministic calibrated belief update
```

That keeps the current benchmark win while giving the next adversarial batch somewhere principled to land.

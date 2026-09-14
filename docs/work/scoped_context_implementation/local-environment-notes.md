# Local Environment Evidence Limits

The workflow-derived local runs use macOS x86_64/Python 3.12.14, rather than
GitHub Ubuntu/Python 3.11. Runtime, dependency-resolution, checkout/action and
hosted aggregate behavior are not claimed equivalent. No GitHub run URL,
event, synthetic merge revision or required-check result is claimed.

Initial unit shard 2: 839 passed, 1 skipped. The coordinator separately ran
`../.venv/bin/python -W error -m pytest -q tests/unit/core/test_prompt_contracts.py
-k test_prompt_renderer_redacts_adversarial_nested_oracle_fields -rs -p no:cacheprovider`
from memorii/: 18 passed, 1 skipped, 116 deselected, 5.94 seconds. The existing
skip is `semantic_ingestion_proposal:v1 has no structured prompt input` at
line 576, not a new feature skip or hidden failure. The file is unchanged from
the baseline. No test selector or warning policy was weakened.

Initial shard 1 took 906.678 seconds including collector/wrapper under local
concurrency; its tests passed in 887.84 seconds. The hosted job timeout is 15
minutes and the planner estimate is 583.978 seconds. This local timing does
not prove hosted timeout headroom. Timing merge will be retained as execution
evidence rather than silently replacing the frozen duration baseline.

The initial package shell wrapper lacked fail-fast mode and returned zero
after a build-dependency DNS failure. That result was rejected. The exact
workflow script was rerun with `bash -e -o pipefail`, network approval and an
isolated wheel/site directory; all wheel import/smoke/artifact commands passed.
The corrected run is the package evidence. Deterministic benchmark row logs
independently show zero failed scenarios and successful artifact validation;
they are dry/fake executions, not live provider quality evidence.

Initial shard5 also has an existing optional-asset skip in
`test_linguistic_adapters.py::test_shipped_manifests_verify_real_local_english_assets`:
its fixed `/private/tmp/memorii-stanza-en-1.14.0` asset directory is unavailable.
That test and its skip condition are unchanged. No new scoped test is skipped.

All six initial shards completed:0/1/2/3/4 passed;5 failed only the determinate
stale exact workflow aggregate assertion recorded in initial-gate-progress.json.
Shard3 passed697 tests in1369.51seconds (wrapper1385.247seconds), exceeding
hosted timeout locally under shared-host concurrency. No local timing is
claimed as hosted headroom. No broad-gate process remains active. Initial logs
are retained under gate-results-initial; initial timing merge was correctly
withheld because shard5 failed.

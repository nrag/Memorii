#!/bin/sh
# The caller freezes this launcher and lock externally. This process then hashes
# every Python/JSON authority before the isolated grammar verifier or runner
# target starts. Result locks are externally hashed before Python can parse an
# evidence record.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../../../.." && pwd)
lock="$root/docs/design/semantic_ingestion_canonical_evidence/candidate-lock-v1.json"
grammar_verifier_interpreter="$root/.venv/bin/python"
runner_target_interpreter="$root/.venv/bin/python"
expected_lock=${1:?expected lock SHA-256 required}
expected_launcher=${2:?expected launcher SHA-256 required}
command=${3:?capture or validate required}
shift 3
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
record_hash() { /usr/bin/jq -cS . "$1" | /usr/bin/tr -d '\n' | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}'; }
[ -x "$grammar_verifier_interpreter" ] && [ -x "$runner_target_interpreter" ] || { echo "repository virtualenv interpreter unavailable" >&2; exit 64; }
[ "$(hash "$lock")" = "$expected_lock" ] || { echo "candidate lock hash mismatch" >&2; exit 64; }
[ "$(hash "$0")" = "$expected_launcher" ] || { echo "launcher hash mismatch" >&2; exit 64; }
case "$command" in capture) target=runner ;; validate) target=artifact_validator ;; bind) target=bind ;; *) echo "unknown command" >&2; exit 64 ;; esac
for authority in lock_resolver recipe runner artifact_validator design verification_contract binding_map performance_schema standard_fixture_schema fixture_manifest production_sources event_schema receipt_schema thin_fixture_grammar preimport_launcher evidence_manifest_schema result_lock_schema comparison_authority_schema comparison_schedule_authority comparison_result_binding_schema; do
  path=$(/usr/bin/jq -r ".artifacts[\"$authority\"].path" "$lock")
  expected=$(/usr/bin/jq -r ".artifacts[\"$authority\"].sha256" "$lock")
  [ "$path" != null ] && [ "$expected" != null ] && [ "$(hash "$root/$path")" = "$expected" ] || { echo "pre-import authority mismatch: $authority" >&2; exit 64; }
done
if [ "$command" = capture ]; then
  source_manifest=$root/$(/usr/bin/jq -r '.artifacts.production_sources.path' "$lock")
  binding_map=$root/$(/usr/bin/jq -r '.artifacts.binding_map.path' "$lock")
  /usr/bin/jq -e --slurpfile bindings "$binding_map" '
    .capture_status == "capture_ready" and
    (keys | sort) == ["capture_ready_transition", "capture_status", "schema", "source_frames", "sources"] and
    (.capture_ready_transition | keys | sort) == ["required_paths", "required_symbols", "rule"] and
    (.sources | type == "array" and length > 0) and
    (.source_frames | type == "array" and length > 0) and
    (.capture_ready_transition.required_paths | type == "array") and
    ((.capture_ready_transition.required_paths | length) == (.capture_ready_transition.required_paths | unique | length)) and
    (.capture_ready_transition.required_symbols | type == "array") and
    ((.capture_ready_transition.required_symbols | length) == (.capture_ready_transition.required_symbols | unique | length)) and
    (.sources | length) == (.capture_ready_transition.required_paths | length) and
    (.source_frames | length) == (.capture_ready_transition.required_symbols | length) and
    ([.sources[] | select(type == "object" and (keys | sort) == ["path", "sha256"] and (.path | type == "string") and (.sha256 | type == "string" and test("^[0-9a-f]{64}$")))] | length) == (.sources | length) and
    ([.sources[].path] | unique | length) == (.sources | length) and
    ([.sources[].path] | sort) == (.capture_ready_transition.required_paths | sort) and
    ([.source_frames[] | select(type == "object" and (keys | sort) == ["path", "sha256", "symbol"] and (.symbol | type == "string") and (.path | type == "string") and (.sha256 | type == "string" and test("^[0-9a-f]{64}$")))] | length) == (.source_frames | length) and
    ([.source_frames[].symbol] | unique | length) == (.source_frames | length) and
    ([.source_frames[].symbol] | sort) == (.capture_ready_transition.required_symbols | sort) and
    ([.source_frames[].path] | unique | sort) == ([.sources[].path] | sort) and
    ([.source_frames[] as $frame | select($frame.sha256 == ([.sources[] | select(.path == $frame.path) | .sha256] | .[0]))] | length) == (.source_frames | length) and
    ((.source_frames | map({key: .symbol, value: {path: .path, sha256: .sha256}}) | from_entries) == $bindings[0].production_entrypoint_bindings[0].source_frame_map)
  ' "$source_manifest" >/dev/null || { echo "capture-ready source-frame inventory mismatch before Python" >&2; exit 64; }
  /usr/bin/jq -r '.sources[] | .path + " " + .sha256' "$source_manifest" | while IFS=' ' read -r path expected; do
    [ "$(hash "$root/$path")" = "$expected" ] || { echo "capture production source mismatch: $path" >&2; exit 64; }
  done
  locked_runner="$root/$(/usr/bin/jq -r '.artifacts.runner.path' "$lock")"
  locked_grammar_validator="$root/$(/usr/bin/jq -r '.artifacts.recipe.path' "$lock")"
  if ! "$grammar_verifier_interpreter" -I "$locked_grammar_validator" --isolated-locked-runner "$locked_runner" --binding-map "$binding_map"; then
    echo "locked static AST grammar rejected runner before capture locks" >&2
    exit 64
  fi
  capture_execution_lock=
  capture_result_lock=
  capture_diagnostic=
  capture_latency=
  capture_kind=
  for_capture_args() {
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --execution-lock) capture_execution_lock=${2:?execution lock required}; shift 2 ;;
        --result-lock) capture_result_lock=${2:?result lock required}; shift 2 ;;
        --diagnostic) capture_diagnostic=${2:?diagnostic artifact required}; shift 2 ;;
        --latency) capture_latency=${2:?latency artifact required}; shift 2 ;;
        --kind) capture_kind=${2:?capture kind required}; shift 2 ;;
        *) shift ;;
      esac
    done
  }
  for_capture_args "$@"
  [ -n "$capture_execution_lock" ] && [ -n "$capture_result_lock" ] && [ -n "$capture_diagnostic" ] && [ -n "$capture_latency" ] && [ -n "$capture_kind" ] || { echo "capture requires execution lock, result lock, kind, diagnostic, and latency paths" >&2; exit 64; }
  set -C
  /usr/bin/jq -n --arg lock "$(hash "$lock")" --arg schedule "$(hash "$root/$(/usr/bin/jq -r '.artifacts.comparison_schedule_authority.path' "$lock")")" --arg kind "$capture_kind" --arg diagnostic "$capture_diagnostic" --arg latency "$capture_latency" '{schema:"memorii.semantic-ingestion.canonical-evidence.execution-lock.v2",kind:$kind,candidate_lock_hash:$lock,comparison_schedule_authority_hash:$schedule,artifacts:[{role:"diagnostic",path:$diagnostic},{role:"latency",path:$latency}]}' > "$capture_execution_lock"
  set +C
fi
if [ "$command" = validate ]; then
  verify_result_locks() {
    (
    baseline_result_lock=
    candidate_result_lock=
    expected_result_locks=
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --baseline-result-lock) baseline_result_lock=${2:?baseline result lock path required}; shift 2 ;;
        --candidate-result-lock) candidate_result_lock=${2:?candidate result lock path required}; shift 2 ;;
        --expected-result-lock-sha256) expected_result_locks="$expected_result_locks ${2:?expected result lock SHA-256 required}"; shift 2 ;;
        *) shift ;;
      esac
    done
    set -- $expected_result_locks
    [ -n "$baseline_result_lock" ] && [ -n "$candidate_result_lock" ] && [ "$#" -eq 2 ] || { echo "two result locks and --expected-result-lock-sha256 values are required" >&2; exit 64; }
    [ "$(hash "$baseline_result_lock")" = "$1" ] && [ "$(hash "$candidate_result_lock")" = "$2" ] || { echo "expected result lock hash mismatch before Python" >&2; exit 64; }
    )
  }
  verify_result_locks "$@"
  (
  comparison_result_binding=
  expected_comparison_result_binding=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --comparison-result-binding) comparison_result_binding=${2:?comparison result binding required}; shift 2 ;;
      --expected-comparison-result-binding-sha256) expected_comparison_result_binding=${2:?comparison result binding SHA-256 required}; shift 2 ;;
      *) shift ;;
    esac
  done
  [ -n "$comparison_result_binding" ] && [ -n "$expected_comparison_result_binding" ] && [ "$(hash "$comparison_result_binding")" = "$expected_comparison_result_binding" ] || { echo "comparison result binding hash mismatch before Python" >&2; exit 64; }
  )
fi
unset PYTHONPATH
case "$command" in
  capture) script="$root/$(/usr/bin/jq -r '.artifacts.runner.path' "$lock")" ;;
  validate) script="$root/memorii/tests/fixtures/semantic_ingestion/canonical_evidence_artifact_validator.py" ;;
esac
if [ "$command" = validate ]; then
  exec "$runner_target_interpreter" -I -c 'import runpy, sys; sys.path.insert(0, sys.argv[1]); sys.argv = sys.argv[2:]; runpy.run_path(sys.argv[0], run_name="__main__")' "$root/memorii/tests/fixtures/semantic_ingestion" "$script" "$@"
fi
if [ "$command" = bind ]; then
  binding=
  baseline_diagnostic=
  baseline_latency=
  baseline_execution=
  baseline_result=
  baseline_authority=
  candidate_diagnostic=
  candidate_latency=
  candidate_execution=
  candidate_result=
  candidate_authority=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --comparison-result-binding) binding=${2:?comparison result binding required}; shift 2 ;;
      --baseline-diagnostic) baseline_diagnostic=${2:?baseline diagnostic required}; shift 2 ;;
      --baseline-latency) baseline_latency=${2:?baseline latency required}; shift 2 ;;
      --baseline-evidence-manifest) baseline_execution=${2:?baseline execution lock required}; shift 2 ;;
      --baseline-result-lock) baseline_result=${2:?baseline result lock required}; shift 2 ;;
      --baseline-authority-lock) baseline_authority=${2:?baseline authority lock required}; shift 2 ;;
      --candidate-diagnostic) candidate_diagnostic=${2:?candidate diagnostic required}; shift 2 ;;
      --candidate-latency) candidate_latency=${2:?candidate latency required}; shift 2 ;;
      --candidate-evidence-manifest) candidate_execution=${2:?candidate execution lock required}; shift 2 ;;
      --candidate-result-lock) candidate_result=${2:?candidate result lock required}; shift 2 ;;
      --candidate-authority-lock) candidate_authority=${2:?candidate authority lock required}; shift 2 ;;
      *) echo "unknown bind argument: $1" >&2; exit 64 ;;
    esac
  done
  [ -n "$binding" ] && [ -n "$baseline_diagnostic" ] && [ -n "$baseline_latency" ] && [ -n "$baseline_execution" ] && [ -n "$baseline_result" ] && [ -n "$baseline_authority" ] && [ -n "$candidate_diagnostic" ] && [ -n "$candidate_latency" ] && [ -n "$candidate_execution" ] && [ -n "$candidate_result" ] && [ -n "$candidate_authority" ] || { echo "bind requires both captured sides and authority locks" >&2; exit 64; }
  set -C
  if ! /usr/bin/jq -n --arg schedule "$(hash "$root/$(/usr/bin/jq -r '.artifacts.comparison_schedule_authority.path' "$lock")")" --arg balock "$(hash "$baseline_authority")" --arg bimpl "$(/usr/bin/jq -r '.implementation_identity' "$baseline_latency")" --arg bsource "$(/usr/bin/jq -r '.production_source_manifest.sha256' "$baseline_latency")" --arg bexec "$(hash "$baseline_execution")" --arg bresult "$(hash "$baseline_result")" --arg bdiag "$(record_hash "$baseline_diagnostic")" --arg blat "$(record_hash "$baseline_latency")" --arg calock "$(hash "$candidate_authority")" --arg cimpl "$(/usr/bin/jq -r '.implementation_identity' "$candidate_latency")" --arg csource "$(/usr/bin/jq -r '.production_source_manifest.sha256' "$candidate_latency")" --arg cexec "$(hash "$candidate_execution")" --arg cresult "$(hash "$candidate_result")" --arg cdiag "$(record_hash "$candidate_diagnostic")" --arg clat "$(record_hash "$candidate_latency")" '{schema:"memorii.semantic-ingestion.canonical-evidence.comparison-result-binding.v1",comparison_schedule_authority_hash:$schedule,baseline:{kind:"baseline",authority_lock_hash:$balock,implementation_identity:$bimpl,source_identity:$bsource,execution_lock_hash:$bexec,result_lock_hash:$bresult,diagnostic_record_hash:$bdiag,latency_record_hash:$blat},candidate:{kind:"candidate",authority_lock_hash:$calock,implementation_identity:$cimpl,source_identity:$csource,execution_lock_hash:$cexec,result_lock_hash:$cresult,diagnostic_record_hash:$cdiag,latency_record_hash:$clat}}' > "$binding"; then
    echo "comparison result binding already exists or cannot be created" >&2
    exit 64
  fi
  set +C
  hash "$binding"
  exit 0
fi
"$runner_target_interpreter" -I "$script" "$@"
[ -f "$capture_execution_lock" ] && [ -f "$capture_diagnostic" ] && [ -f "$capture_latency" ] || { echo "execution lock and capture artifacts must exist before result lock" >&2; exit 64; }
set -C
/usr/bin/jq -n --arg lock "$(hash "$lock")" --arg execution "$(hash "$capture_execution_lock")" --arg schedule "$(hash "$root/$(/usr/bin/jq -r '.artifacts.comparison_schedule_authority.path' "$lock")")" --arg diagnostic "$capture_diagnostic" --arg diagnostic_hash "$(hash "$capture_diagnostic")" --arg latency "$capture_latency" --arg latency_hash "$(hash "$capture_latency")" --slurpfile diagnostic_record "$capture_diagnostic" '{schema:"memorii.semantic-ingestion.canonical-evidence.result-lock.v2",candidate_lock_hash:$lock,execution_lock_hash:$execution,comparison_schedule_authority_hash:$schedule,artifacts:[{role:"diagnostic",path:$diagnostic,sha256:$diagnostic_hash},{role:"latency",path:$latency,sha256:$latency_hash}],terminal_durable_effect_receipts:$diagnostic_record[0].cells|map(.terminal_durable_effect_receipt)}' > "$capture_result_lock"
set +C
hash "$capture_result_lock"

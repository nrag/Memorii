"""Capture the provider envelope compatibility corpus from a pinned Git archive.

The generated corpus is deliberately not an executable target oracle.  It is
produced in a temporary archive extraction, and the committed legacy reader is
an independent, dependency-free consumer of its public JSON bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

BASELINE_REVISION = "f76850fc45f09d21a40b5a7302d173ce642ec9d6"
BASELINE_TREE = "1aef4aa4364dad9cf4e0063fb64a8e26c5783614"
SOURCE_BLOB = "307921e7648fcaf5e11244200a7fb3c1f402e817"
SOURCE_SHA256 = "38b80a29a991ebfb1076cccc437c2406d43da031982a6c8fe57f755e1e58dbbd"
_SOURCE_PATH = "memorii/memorii/core/provider/models.py"
_JCS_PROGRAM = r'''const fs=require("fs");
function keyOrder(a,b){const A=Array.from(a).flatMap(c=>{const n=c.codePointAt(0);return n>0xffff?[0xd800+((n-0x10000)>>10),0xdc00+((n-0x10000)&1023)]:[n]});const B=Array.from(b).flatMap(c=>{const n=c.codePointAt(0);return n>0xffff?[0xd800+((n-0x10000)>>10),0xdc00+((n-0x10000)&1023)]:[n]});for(let i=0;i<Math.min(A.length,B.length);i++){if(A[i]!==B[i])return A[i]-B[i]}return A.length-B.length}
function jcs(v){if(v===null||typeof v==="boolean"||typeof v==="number"||typeof v==="string")return JSON.stringify(v);if(Array.isArray(v))return "["+v.map(jcs).join(",")+"]";return "{"+Object.keys(v).sort(keyOrder).map(k=>JSON.stringify(k)+":"+jcs(v[k])).join(",")+"}"}
process.stdout.write(jcs(JSON.parse(fs.readFileSync(0,"utf8"))));'''
# This program is evaluated inside the archive.  Keep it self-contained so it
# cannot import the checkout being tested.
_CAPTURE = r'''
import itertools, json
from datetime import UTC, datetime
from memorii.core.provider.models import ProviderEvolutionOutcome, ProviderSyncResult, ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.integrations.hermes_provider import HermesMemoryProvider
from memorii.core.memory_evolution import EnglishRuleMemoryExtractor, HybridMemoryExtractor, LLMMemoryExtractor
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.domain.enums import MemoryDomain, ExtractionFailureCode, ExtractionRunStatus, FallbackOutcome, FinalExtractionSource, ProviderAttemptStatus

def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8").decode("utf-8")

def dump(model): return model.model_dump(mode="json", exclude_none=False)

def result_cases():
    base = {"operation_id":"op", "status":"evolution_pending", "attempt_count":0}
    valid = {
      "pending": base,
      "running_retryable": {**base,"status":"evolution_running","attempt_count":2,"retryable":True},
      "failed_retryable": {**base,"status":"evolution_failed","attempt_count":1,"failure_code":"provider_unavailable","retryable":True},
      "failed_fallback": {**base,"status":"evolution_failed","attempt_count":2,"failure_code":"provider_unavailable","extraction_status":"failed","provider_attempt_status":"provider_error","fallback_outcome":"failed","final_extraction_source":"none","fallback_provider":"fallback-v1"},
      "committed_primary": {**base,"status":"evolution_committed","attempt_count":1,"extraction_status":"succeeded","provider_attempt_status":"succeeded","final_extraction_source":"primary"},
      "committed_fallback": {**base,"status":"evolution_committed","attempt_count":2,"extraction_status":"succeeded","provider_attempt_status":"provider_error","fallback_outcome":"succeeded","final_extraction_source":"fallback","fallback_provider":"fallback-v1"},
      "committed_abstained": {**base,"status":"evolution_committed","extraction_status":"abstained","provider_attempt_status":"not_attempted","final_extraction_source":"none"},
      "unicode_boundary": {**base,"operation_id":"op-\x00-\U0001f642-e\u0301","failure_code":"line\nquote\""},
      "string_attempt_coercion": {**base,"attempt_count":"1"},
    }
    invalid = {
      "committed_without_extraction": {**base,"status":"evolution_committed"},
      "failed_without_failure": {**base,"status":"evolution_failed"},
      "fallback_missing_provider": {**base,"fallback_outcome":"succeeded","final_extraction_source":"fallback"},
      "failed_fallback_wrong_source": {**base,"fallback_outcome":"failed","fallback_provider":"x","final_extraction_source":"primary"},
      "unused_fallback_provider": {**base,"fallback_provider":"x"},
      "negative_attempt": {**base,"attempt_count":-1},
      "unknown_status": {**base,"status":"unknown"},
      "unknown_field": {**base,"extra":True},
      "null_required": {**base,"operation_id":None},
      "float_attempt": {**base,"attempt_count":1.5},
    }
    return valid, invalid

valid, invalid = result_cases()
accepted = {name: dump(ProviderEvolutionOutcome.model_validate(value)) for name,value in valid.items()}
rejected = {}
for name, value in invalid.items():
  try: ProviderEvolutionOutcome.model_validate(value)
  except Exception as error: rejected[name] = type(error).__name__
  else: raise RuntimeError("invalid vector accepted: " + name)

# Exhaust validator branches independent of target tests: all lifecycle inputs
# used by the after-validator, including null/known enum values and provenance.
branch = {}
for status, extraction, attempt, fallback, final, fallback_provider, failure in itertools.product(
  ["evolution_pending","evolution_running","evolution_committed","evolution_failed"],
  [None] + [x.value for x in ExtractionRunStatus],
  [None] + [x.value for x in ProviderAttemptStatus],
  [x.value for x in FallbackOutcome], [None] + [x.value for x in FinalExtractionSource],
  [None,"fallback-v1"], [None,"failure"]):
  key = "|".join(str(x) for x in (status, extraction, attempt, fallback, final, fallback_provider, failure))
  value={"operation_id":"matrix","status":status,"attempt_count":0,"extraction_status":extraction,"provider_attempt_status":attempt,"fallback_outcome":fallback,"final_extraction_source":final,"fallback_provider":fallback_provider,"failure_code":failure}
  try:
    output = dump(ProviderEvolutionOutcome.model_validate(value))
    branch[key] = {"input": value, "accepted": True, "output_bytes": canonical(output)}
  except Exception as error: branch[key] = {"input": value, "accepted": False, "error": type(error).__name__}

# The failure-code and coercion dimensions are independently crossed with each
# lifecycle state.  This keeps the committed corpus tractable while making the
# coverage inventory explicit rather than silently sampling those dimensions.
for status, extraction_failure, primary_failure, retryable, attempt_count in itertools.product(
  ["evolution_pending","evolution_running","evolution_committed","evolution_failed"],
  [None] + [x.value for x in ExtractionFailureCode],
  [None] + [x.value for x in ExtractionFailureCode], [False, True], [0, 1, "1", -1, 1.5]):
  key="failure-axis|"+"|".join(str(x) for x in (status, extraction_failure, primary_failure, retryable, attempt_count))
  value={"operation_id":"failure-axis","status":status,"attempt_count":attempt_count,"retryable":retryable,"extraction_failure_code":extraction_failure,"primary_failure_code":primary_failure}
  if status == "evolution_failed": value["failure_code"]="failure"
  try:
   output=dump(ProviderEvolutionOutcome.model_validate(value)); branch[key]={"input":value,"accepted":True,"output_bytes":canonical(output)}
  except Exception as error: branch[key]={"input":value,"accepted":False,"error":type(error).__name__}

def sync(**changes):
  value={"transcript_ids":[],"candidate_ids":[],"blocked_domains":[],"blocked_reasons":{},"allowed_candidate_domains":[],"raw_append_domains":[],"blocked_commit_domains":[],"evolution_outcomes":[]}
  value.update(changes); return dump(ProviderSyncResult.model_validate(value))

sync_cases={
  "empty": sync(),
  "blocked": sync(blocked_domains=[MemoryDomain.SEMANTIC], blocked_reasons={"semantic":"policy"}, blocked_commit_domains=[MemoryDomain.SEMANTIC]),
  "candidate": sync(transcript_ids=["t1"], candidate_ids=["c1"], allowed_candidate_domains=[MemoryDomain.EPISODIC], raw_append_domains=[MemoryDomain.TRANSCRIPT]),
  "retryable_failure": sync(evolution_outcomes=[accepted["failed_retryable"]]),
  "nonretryable_failure": sync(evolution_outcomes=[accepted["failed_fallback"]]),
  "terminal": sync(evolution_outcomes=[accepted["committed_primary"]]),
  "multiple_ordered": sync(evolution_outcomes=[accepted["failed_retryable"],accepted["committed_fallback"],accepted["committed_abstained"]]),
}
sync_inputs={
 "bare": {}, "omit_transcript_ids": {"candidate_ids":["c"]}, "omit_candidate_ids":{"transcript_ids":["t"]},
 "explicit_null": {"transcript_ids":None}, "unknown": {"unknown":True}, "invalid_domain":{"blocked_domains":["unknown"]},
 "invalid_mapping":{"blocked_reasons":[]}, "invalid_nested":{"evolution_outcomes":[{"status":"unknown"}]},
 "non_string_transcript_id":{"transcript_ids":[1]}, "non_string_candidate_id":{"candidate_ids":[False]},
 "non_string_reason":{"blocked_reasons":{"semantic":1}},
 "wrong_transcript_container":{"transcript_ids":{}}, "wrong_domains_container":{"blocked_domains":{}},
 "wrong_outcomes_container":{"evolution_outcomes":{}},
}
sync_validation={}
for name, value in sync_inputs.items():
 try: sync_validation[name]={"input":value,"accepted":True,"expected_bytes":canonical(sync(**value))}
 except Exception as error: sync_validation[name]={"input":value,"accepted":False,"error":type(error).__name__}

now=lambda: datetime(2026,1,2,tzinfo=UTC)
service=ProviderMemoryService(now_provider=now)
service_result=dump(service.sync_event(operation=ProviderOperation.MEMORY_WRITE_DAILYLOG, content="Provider compatibility service bytes", operation_id="compatibility-service", task_id="provider-compatibility"))
hermes=HermesMemoryProvider(ProviderMemoryService(now_provider=now))
hermes_result=dump(hermes.sync_turn("Provider compatibility user bytes", "Provider compatibility assistant bytes", operation_id="compatibility-turn", task_id="provider-compatibility"))
def failing_extractor():
 return LLMMemoryExtractor(runner=PromptLLMRunner(client=FakeLLMStructuredClient(raise_on_request=True), config=LLMRuntimeConfig(provider="none")))
def service_path(extractor, operation_id, content="Atlas owner is Bob."):
 return dump(ProviderMemoryService(memory_evolution_extractor=extractor, now_provider=now).sync_event(operation=ProviderOperation.MEMORY_WRITE_DAILYLOG, content=content, operation_id=operation_id, task_id="provider-compatibility"))
class FailFirst(EnglishRuleMemoryExtractor):
 def __init__(self): self.calls=0
 def extract(self, observations):
  self.calls += 1
  if self.calls == 1: raise OSError("injected retryable failure")
  return super().extract(observations)
service_paths={
 "deterministic_abstention": dump(ProviderMemoryService(memory_evolution_extractor=EnglishRuleMemoryExtractor(), now_provider=now).sync_event(operation=ProviderOperation.MEMORY_WRITE_DAILYLOG, content="ignored", operation_id="compatibility-abstained", task_id="provider-compatibility", source_modality="noise")),
 "retryable_failure": service_path(failing_extractor(), "compatibility-retryable"),
 "terminal_nonretryable": service_path(LLMMemoryExtractor(runner=PromptLLMRunner(client=FakeLLMStructuredClient(default_response="{}"), config=LLMRuntimeConfig(provider="none"))), "compatibility-terminal"),
 "committed_primary": service_path(EnglishRuleMemoryExtractor(), "compatibility-primary"),
 "committed_fallback": service_path(HybridMemoryExtractor(llm_extractor=failing_extractor()), "compatibility-fallback"),
}
mixed=HermesMemoryProvider(ProviderMemoryService(memory_evolution_extractor=FailFirst(), now_provider=now))
service_paths["hermes_ordered_mixed"] = dump(mixed.sync_turn("Atlas owner is Bob.", "Atlas owner is Carol.", operation_id="compatibility-mixed", task_id="provider-compatibility"))

print(json.dumps({
 "provider_evolution_outcome_schema":ProviderEvolutionOutcome.model_json_schema(),
 "provider_sync_result_schema":ProviderSyncResult.model_json_schema(),
 "field_order":{"ProviderEvolutionOutcome":list(ProviderEvolutionOutcome.model_fields),"ProviderSyncResult":list(ProviderSyncResult.model_fields)},
 "accepted_outcomes":accepted,"accepted_outcome_bytes":{k:canonical(v) for k,v in accepted.items()},"invalid_outcomes":invalid,"invalid_outcome_results":rejected,
 "validator_branch_matrix":branch,
 "enum_members":{name:[x.value for x in enum] for name,enum in {"ExtractionFailureCode":ExtractionFailureCode,"ExtractionRunStatus":ExtractionRunStatus,"FallbackOutcome":FallbackOutcome,"FinalExtractionSource":FinalExtractionSource,"ProviderAttemptStatus":ProviderAttemptStatus}.items()},
 "sync_cases":sync_cases,"sync_case_bytes":{k:canonical(v) for k,v in sync_cases.items()},"sync_validation":sync_validation,
 "service_public_bytes":canonical(service_result),"hermes_public_bytes":canonical(hermes_result),"service_path_bytes":{k:canonical(v) for k,v in service_paths.items()},
}, ensure_ascii=True, sort_keys=True, separators=(",",":")))
'''


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    """Encode RFC 8785 using the bound ECMAScript JSON primitive encoder."""
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("RFC 8785 capture requires the pinned Node.js runtime")
    source = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return subprocess.run([node, "-e", _JCS_PROGRAM], input=source, check=True, capture_output=True).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--legacy-reader", type=Path)
    args = parser.parse_args(argv)
    if shutil.which("node") is None:
        raise RuntimeError("RFC 8785 capture requires the pinned Node.js runtime")
    repository, interpreter = args.repository.resolve(), args.python.expanduser().absolute()
    archive = subprocess.run(["git", "archive", "--format=tar", BASELINE_REVISION], cwd=repository, check=True, capture_output=True).stdout
    source = subprocess.run(["git", "show", f"{BASELINE_REVISION}:{_SOURCE_PATH}"], cwd=repository, check=True, capture_output=True).stdout
    blob = subprocess.run(["git", "rev-parse", f"{BASELINE_REVISION}:{_SOURCE_PATH}"], cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(["git", "rev-parse", f"{BASELINE_REVISION}^{{tree}}"], cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    if (blob, tree, _sha256(source)) != (SOURCE_BLOB, BASELINE_TREE, SOURCE_SHA256):
        raise RuntimeError("pinned baseline commit/tree/blob/source mismatch")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        archive_path = root / "baseline.tar"
        archive_path.write_bytes(archive)
        with tarfile.open(archive_path) as tar:
            members = tar.getmembers()
            if any(member.name.startswith("/") or ".." in Path(member.name).parts for member in members):
                raise RuntimeError("baseline archive contains an unsafe member")
            tar.extractall(root / "tree", members=members, filter="data")
        child_environment = {"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"}
        # setup-python distributions on Linux need their tool-cache library
        # directory to load libpython. This does not add a Python import path.
        if loader_path := os.environ.get("LD_LIBRARY_PATH"):
            child_environment["LD_LIBRARY_PATH"] = loader_path
        captured = subprocess.run(
            [str(interpreter), "-s", "-c", _CAPTURE],
            cwd=root / "tree" / "memorii",
            check=False,
            capture_output=True,
            text=True,
            env=child_environment,
        )
        if captured.returncode:
            raise RuntimeError(f"isolated baseline capture failed: {captured.stderr}")
    payload = json.loads(captured.stdout)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Capture never owns the separately authored frozen legacy reader.
    files = {"ProviderEvolutionOutcome.baseline.py": source}
    for name, data in files.items():
        (output / name).write_bytes(data)
    corpus = _canonical(payload)
    (output / "provider_envelope_corpus.json").write_bytes(corpus)
    # The manifest deliberately does not hash itself. It binds only immutable
    # inputs and generated siblings, eliminating the self-digest paradox.
    manifest = {"format":"memorii.provider-envelope-capture.v4","baseline":{"commit":BASELINE_REVISION,"tree":tree,"source_path":_SOURCE_PATH,"blob":blob,"source_sha256":_sha256(source),"archive_sha256":_sha256(archive)},"capture":{"method":"git_archive_isolated_runtime","tool_sha256":_sha256(Path(__file__).read_bytes()),"program_sha256":_sha256(_CAPTURE.encode()),"jcs_program_sha256":_sha256(_JCS_PROGRAM.encode("utf-8"))},"generated_files":{name:_sha256(data) for name,data in {**files,"provider_envelope_corpus.json":corpus}.items()},"corpus_sha256":_sha256(corpus),"coverage":{"required_sections":["provider_evolution_outcome_schema","provider_sync_result_schema","field_order","accepted_outcomes","invalid_outcomes","validator_branch_matrix","enum_members","sync_cases","service_public_bytes","hermes_public_bytes"],"validator_vector_count":len(payload["validator_branch_matrix"]),"sync_case_names":list(payload["sync_cases"]),"outcome_case_names":list(payload["accepted_outcomes"])} }
    reader = (args.legacy_reader or output / "legacy_reader.py").resolve()
    if not reader.is_file():
        raise RuntimeError("frozen legacy reader is required and capture will not create it")
    manifest["capture"]["inputs"] = {
        "legacy_reader": {
            "path": "legacy_reader.py",
            "sha256": _sha256(reader.read_bytes()),
        }
    }
    manifest["coverage"]["required_sections"].extend(["accepted_outcome_bytes", "sync_case_bytes", "sync_validation"])
    manifest["coverage"]["failure_code_axis_count"] = 4 * 6 * 6 * 2 * 5
    (output / "capture_manifest.json").write_bytes(_canonical(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

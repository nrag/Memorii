"""Capture the pinned provider envelope from an isolated Git archive.

This command is intentionally a one-way fixture capture tool.  Target tests
only read the committed bytes it emits and never call this module.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

BASELINE_REVISION = "f76850fc45f09d21a40b5a7302d173ce642ec9d6"
SOURCE_BLOB = "307921e7648fcaf5e11244200a7fb3c1f402e817"
SOURCE_SHA256 = "38b80a29a991ebfb1076cccc437c2406d43da031982a6c8fe57f755e1e58dbbd"
_SOURCE_PATH = "memorii/memorii/core/provider/models.py"
_CAPTURE = r"""
import json
from memorii.core.provider.models import ProviderEvolutionOutcome, ProviderSyncResult
from memorii.domain.enums import MemoryDomain
from memorii.domain.enums import ExtractionFailureCode, ExtractionRunStatus, FallbackOutcome, FinalExtractionSource, ProviderAttemptStatus

def canonical_json(value):
    if value is None or isinstance(value, bool):
        return b"true" if value is True else b"false" if value is False else b"null"
    if isinstance(value, (int, float, str)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if isinstance(value, list):
        return b"[" + b",".join(canonical_json(item) for item in value) + b"]"
    if isinstance(value, dict):
        return b"{" + b",".join(canonical_json(key) + b":" + canonical_json(item) for key, item in value.items()) + b"}"
    raise TypeError(type(value))

valid = {
    "pending": {"operation_id": "op-pending", "status": "evolution_pending", "attempt_count": 0},
    "running": {"operation_id": "op-running", "status": "evolution_running", "attempt_count": 2, "retryable": True},
    "failed": {"operation_id": "op-failed", "status": "evolution_failed", "attempt_count": 1, "failure_code": "provider_unavailable", "retryable": True},
    "failed_fallback": {"operation_id": "op-fallback-failed", "status": "evolution_failed", "attempt_count": 2, "failure_code": "provider_unavailable", "extraction_status": "failed", "provider_attempt_status": "provider_error", "fallback_outcome": "failed", "final_extraction_source": "none", "fallback_provider": "fallback-v1"},
    "committed_primary": {"operation_id": "op-primary", "status": "evolution_committed", "attempt_count": 1, "extraction_status": "succeeded", "provider_attempt_status": "succeeded", "final_extraction_source": "primary"},
    "committed_fallback": {"operation_id": "op-fallback", "status": "evolution_committed", "attempt_count": 2, "extraction_status": "succeeded", "provider_attempt_status": "provider_error", "fallback_outcome": "succeeded", "final_extraction_source": "fallback", "fallback_provider": "fallback-v1"},
    "committed_abstained": {"operation_id": "op-abstained", "status": "evolution_committed", "attempt_count": 0, "extraction_status": "abstained", "provider_attempt_status": "not_attempted", "final_extraction_source": "none"},
}
invalid = {
    "committed_without_extraction": {"operation_id": "bad", "status": "evolution_committed", "attempt_count": 0},
    "failed_without_failure_code": {"operation_id": "bad", "status": "evolution_failed", "attempt_count": 0},
    "fallback_without_provider": {"operation_id": "bad", "status": "evolution_pending", "attempt_count": 0, "fallback_outcome": "succeeded", "final_extraction_source": "fallback"},
    "null_required_field": {"operation_id": None, "status": "evolution_pending", "attempt_count": 0},
    "null_defaulted_enum": {"operation_id": "bad", "status": "evolution_pending", "attempt_count": 0, "fallback_outcome": None},
    "negative_attempt_count": {"operation_id": "bad", "status": "evolution_pending", "attempt_count": -1},
    "unknown_status": {"operation_id": "bad", "status": "semantic_rejected", "attempt_count": 0},
    "committed_with_failure": {"operation_id": "bad", "status": "evolution_committed", "attempt_count": 1, "failure_code": "bad", "extraction_status": "succeeded", "provider_attempt_status": "succeeded", "final_extraction_source": "primary"},
    "unused_fallback_provider": {"operation_id": "bad", "status": "evolution_pending", "attempt_count": 0, "fallback_provider": "fallback-v1"},
    "unknown_field": {"operation_id": "bad", "status": "evolution_pending", "attempt_count": 0, "unexpected": True},
}
validated = {name: ProviderEvolutionOutcome.model_validate(value).model_dump(mode="json", exclude_none=False) for name, value in valid.items()}
sync_sample = ProviderSyncResult(
    transcript_ids=["transcript-1"], candidate_ids=["candidate-1"],
    blocked_domains=[MemoryDomain.SEMANTIC], blocked_reasons={"semantic": "policy"},
    allowed_candidate_domains=[MemoryDomain.EPISODIC], raw_append_domains=[MemoryDomain.TRANSCRIPT],
    blocked_commit_domains=[MemoryDomain.USER], evolution_outcomes=[ProviderEvolutionOutcome.model_validate(valid["failed"])],
).model_dump(mode="json", exclude_none=False)
payload = {
    "json_schema": ProviderEvolutionOutcome.model_json_schema(),
    "provider_sync_result_schema": ProviderSyncResult.model_json_schema(),
    "provider_sync_result_canonical_json_utf8": canonical_json(sync_sample).decode("utf-8"),
    "valid_cases": validated,
    "canonical_json_utf8": {name: canonical_json(value).decode("utf-8") for name, value in validated.items()},
    "invalid_cases": invalid,
    "enum_members": {
        "ExtractionFailureCode": [item.value for item in ExtractionFailureCode],
        "ExtractionRunStatus": [item.value for item in ExtractionRunStatus],
        "FallbackOutcome": [item.value for item in FallbackOutcome],
        "FinalExtractionSource": [item.value for item in FinalExtractionSource],
        "ProviderAttemptStatus": [item.value for item in ProviderAttemptStatus],
    },
}
print(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args(argv)
    repository = args.repository.resolve()
    interpreter = args.python.expanduser().absolute()
    version = subprocess.run(
        [str(interpreter), "-c", "import sys; print('.'.join(map(str, sys.version_info[:2])))"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tuple(int(part) for part in version.split(".")) < (3, 11):
        raise RuntimeError("fixture capture requires Python 3.11 or newer")
    archive = subprocess.run(
        ["git", "archive", "--format=tar", BASELINE_REVISION], cwd=repository, check=True, capture_output=True
    )
    source = subprocess.run(
        ["git", "show", f"{BASELINE_REVISION}:{_SOURCE_PATH}"], cwd=repository, check=True, capture_output=True
    ).stdout
    resolved_blob = subprocess.run(
        ["git", "rev-parse", f"{BASELINE_REVISION}:{_SOURCE_PATH}"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if resolved_blob != SOURCE_BLOB:
        raise RuntimeError("pinned source Git object does not match the frozen architecture")
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("pinned source blob digest does not match the frozen architecture")
    with tempfile.TemporaryDirectory() as temporary:
        isolated_root = Path(temporary)
        archive_path = isolated_root / "baseline.tar"
        archive_path.write_bytes(archive.stdout)
        with tarfile.open(archive_path) as tar:
            tar.extractall(isolated_root / "tree", filter="data")
        captured = subprocess.run(
            [str(interpreter), "-c", _CAPTURE],
            cwd=isolated_root / "tree" / "memorii",
            check=True,
            capture_output=True,
            text=True,
            env={"PYTHONNOUSERSITE": "1", "PATH": "/usr/bin:/bin"},
        )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "ProviderEvolutionOutcome.baseline.py").write_bytes(source)
    data = json.loads(captured.stdout)
    dependencies: dict[str, str] = {}
    distribution_fingerprints: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        metadata = distribution.metadata
        if "Name" not in metadata:
            continue
        name = metadata["Name"]
        if not name:
            continue
        dependencies[name.lower()] = distribution.version
        files = distribution.files or ()
        file_rows: list[tuple[str, str]] = []
        for file in files:
            # ``importlib.metadata`` exposes an abstract SimplePath here.  This
            # capture is intentionally archive/filesystem based, so normalize the
            # concrete location before reading and omit directory-only entries.
            path = Path(str(distribution.locate_file(file)))
            if path.is_file():
                file_rows.append((str(file), hashlib.sha256(path.read_bytes()).hexdigest()))
        distribution_fingerprints[name.lower()] = hashlib.sha256(
            json.dumps(sorted(file_rows), separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    capture_tool_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    archive_digest = hashlib.sha256(archive.stdout).hexdigest()
    corpus_bytes = json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    data["provenance"] = {
        "baseline_revision": BASELINE_REVISION,
        "source_blob": SOURCE_BLOB,
        "resolved_source_blob": resolved_blob,
        "source_sha256": SOURCE_SHA256,
        "capture_method": "git_archive_isolated_source_tree",
        "capture_tool_sha256": capture_tool_digest,
        "archive_sha256": archive_digest,
        "interpreter": str(interpreter),
        "python_version": version,
        "interpreter_sha256": hashlib.sha256(interpreter.read_bytes()).hexdigest(),
        "pydantic_version": dependencies.get("pydantic"),
        "pydantic_distribution_sha256": distribution_fingerprints.get("pydantic"),
        "dependency_fingerprint": hashlib.sha256(
            json.dumps(dependencies, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "dependency_distribution_fingerprint": hashlib.sha256(
            json.dumps(distribution_fingerprints, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "model_path": "memorii.core.provider.models.ProviderEvolutionOutcome",
    }
    output = json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (args.output / "provider_evolution_outcome.json").write_bytes(output)
    (args.output / "capture_manifest.json").write_bytes(
        json.dumps({"corpus_sha256": hashlib.sha256(output).hexdigest(), "capture_payload_sha256": hashlib.sha256(corpus_bytes).hexdigest(), "fixture_digests": {"ProviderEvolutionOutcome.baseline.py": SOURCE_SHA256, "provider_evolution_outcome.json": hashlib.sha256(output).hexdigest()}}, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

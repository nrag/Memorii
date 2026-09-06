#!/usr/bin/env python3
"""Fail-closed verifier for manifest-defined indexed WorkPlan splits."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class VerificationError(RuntimeError):
    """Raised when a manifest or its declared WorkPlan split is invalid."""


FORMAT = "memorii.workplan-split-manifest.v2"
METRIC_KINDS = {
    "byte_count",
    "newline_count",
    "non_whitespace_word_count",
    "level_2_heading_count",
    "level_2_or_3_heading_count",
    "decision_entry_count",
    "closure_marker_count",
}
REQUIREMENT_IDS = {f"SIA-R{number:02d}" for number in range(1, 24)}


def _require_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown or missing:
        raise VerificationError(f"{context}: unknown={sorted(unknown)} missing={sorted(missing)}")


def _relative_path(root: Path, value: str, context: str) -> Path:
    candidate = (root / value).resolve()
    if candidate != root and root not in candidate.parents:
        raise VerificationError(f"{context}: path escapes repository root: {value}")
    if not candidate.is_file():
        raise VerificationError(f"{context}: required file is missing: {value}")
    return candidate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metric(kind: str, text: str, data: bytes) -> int:
    if kind == "byte_count":
        return len(data)
    if kind == "newline_count":
        return data.count(b"\n")
    if kind == "non_whitespace_word_count":
        return len(re.findall(r"\S+", text))
    if kind == "level_2_heading_count":
        return len(re.findall(r"^## ", text, flags=re.MULTILINE))
    if kind == "level_2_or_3_heading_count":
        return len(re.findall(r"^(?:##|###) ", text, flags=re.MULTILINE))
    if kind == "decision_entry_count":
        return len(re.findall(r"^- Decision:", text, flags=re.MULTILINE))
    if kind == "closure_marker_count":
        return len(
            re.findall(
                r"remaining_(?:validated_p1_p2|blocks_approval|changes_required)",
                text,
            )
        )
    raise VerificationError(f"unsupported metric extractor: {kind}")


def _manifest_pin_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def _verify_manifest_pin(path: Path) -> None:
    pin_path = _manifest_pin_path(path)
    if not pin_path.is_file():
        raise VerificationError(f"manifest pin is missing: {pin_path}")
    fields = pin_path.read_text(encoding="utf-8").split()
    if len(fields) != 2 or fields[1] != path.name or fields[0] != _sha256(path):
        raise VerificationError("manifest pin mismatch")


def _bundle_sha256(root: Path, artifacts: list[dict[str, Any]], manifest_path: Path) -> str:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    entries: list[str] = []
    manifest_relative = str(manifest_path.relative_to(root))
    for artifact in artifacts:
        path = artifact["path"]
        if path == manifest_relative:
            continue
        entries.append(f"{path}\0{_sha256(_relative_path(root, path, 'bundle artifact'))}\n")
    return hashlib.sha256("".join(sorted(entries)).encode("utf-8")).hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise VerificationError("manifest root must be an object")
    _require_keys(
        data,
        {
            "format",
            "bundle_sha256",
            "candidate_identity",
            "canonical_path",
            "archive",
            "artifacts",
            "milestones",
            "reference_corpus",
            "obligations",
            "required_paths",
            "section_counts",
        },
        "manifest root",
    )
    if data["format"] != FORMAT:
        raise VerificationError(f"unsupported manifest format: {data['format']!r}")
    return data


def _command_bytes(root: Path, *command: str) -> bytes:
    try:
        return subprocess.check_output(command, cwd=root)
    except subprocess.CalledProcessError as exc:
        raise VerificationError(f"identity command failed: {' '.join(command)}") from exc


def _status_records(status: bytes) -> list[bytes]:
    return [record for record in status.split(b"\0") if record]


def _untracked_content_digest(root: Path, status: bytes) -> tuple[int, str]:
    paths = [record[3:] for record in _status_records(status) if record.startswith(b"?? ")]
    entries = [
        path
        + b"\0"
        + _sha256(_relative_path(root, os.fsdecode(path), "untracked candidate file")).encode("ascii")
        + b"\n"
        for path in paths
    ]
    return len(paths), hashlib.sha256(b"".join(sorted(entries))).hexdigest()


def _verify_candidate_identity(root: Path, relative_path: str) -> None:
    identity_path = _relative_path(root, relative_path, "candidate identity")
    _verify_manifest_pin(identity_path)
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VerificationError(f"candidate identity is invalid JSON: {exc}") from exc
    if not isinstance(identity, dict):
        raise VerificationError("candidate identity root must be an object")
    _require_keys(
        identity,
        {
            "format",
            "created",
            "git_head",
            "tree_state",
            "review_scope",
            "git_status",
            "tracked_diff",
            "staged_diff",
            "untracked_content_manifest",
            "coordination_artifact_digest",
            "coordination_artifacts",
            "self_exclusions",
            "evidence_limitations",
        },
        "candidate identity",
    )
    if identity["format"] != "memorii.dirty-coordination-candidate.v1":
        raise VerificationError("unsupported candidate identity format")
    actual_head = _command_bytes(root, "git", "rev-parse", "HEAD").decode().strip()
    if actual_head != identity["git_head"]:
        raise VerificationError("candidate identity git HEAD mismatch")

    status = _command_bytes(
        root, "git", "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    status_contract = identity["git_status"]
    _require_keys(status_contract, {"command", "entry_count", "sha256"}, "git_status")
    if (
        status_contract["command"]
        != "git status --porcelain=v1 -z --untracked-files=all"
        or len(_status_records(status)) != status_contract["entry_count"]
        or hashlib.sha256(status).hexdigest() != status_contract["sha256"]
    ):
        raise VerificationError("candidate identity git status mismatch")

    tracked_diff = _command_bytes(root, "git", "diff", "--binary")
    diff_contract = identity["tracked_diff"]
    _require_keys(diff_contract, {"command", "sha256"}, "tracked_diff")
    if (
        diff_contract["command"] != "git diff --binary"
        or hashlib.sha256(tracked_diff).hexdigest() != diff_contract["sha256"]
    ):
        raise VerificationError("candidate identity tracked diff mismatch")

    staged_diff = _command_bytes(root, "git", "diff", "--cached", "--binary")
    staged_contract = identity["staged_diff"]
    _require_keys(staged_contract, {"command", "sha256"}, "staged_diff")
    if (
        staged_contract["command"] != "git diff --cached --binary"
        or hashlib.sha256(staged_diff).hexdigest() != staged_contract["sha256"]
    ):
        raise VerificationError("candidate identity staged diff mismatch")

    untracked_count, untracked_digest = _untracked_content_digest(root, status)
    untracked_contract = identity["untracked_content_manifest"]
    _require_keys(
        untracked_contract,
        {"algorithm", "file_count", "sha256"},
        "untracked_content_manifest",
    )
    if (
        untracked_contract["file_count"] != untracked_count
        or untracked_digest != untracked_contract["sha256"]
    ):
        raise VerificationError("candidate identity untracked content mismatch")

    artifacts = identity["coordination_artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise VerificationError("candidate coordination artifacts must be nonempty")
    coordination_entries: list[str] = []
    paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise VerificationError("candidate coordination artifact must be an object")
        _require_keys(artifact, {"path", "sha256"}, "candidate coordination artifact")
        path, expected = artifact["path"], artifact["sha256"]
        if not isinstance(path, str) or path in paths or not isinstance(expected, str):
            raise VerificationError("invalid candidate coordination artifact")
        paths.add(path)
        resolved = (
            Path.home() / path.removeprefix("~/")
            if path.startswith("~/")
            else _relative_path(root, path, "candidate coordination artifact")
        )
        if not resolved.is_file() or _sha256(resolved) != expected:
            raise VerificationError(f"candidate coordination artifact mismatch: {path}")
        coordination_entries.append(f"{path}\0{expected}\n")
    digest_contract = identity["coordination_artifact_digest"]
    _require_keys(
        digest_contract,
        {"algorithm", "artifact_count", "sha256"},
        "coordination_artifact_digest",
    )
    if (
        digest_contract["artifact_count"] != len(artifacts)
        or hashlib.sha256("".join(sorted(coordination_entries)).encode()).hexdigest()
        != digest_contract["sha256"]
    ):
        raise VerificationError("candidate coordination artifact digest mismatch")
    if not identity["self_exclusions"] or not identity["evidence_limitations"]:
        raise VerificationError("candidate identity must record exclusions and limitations")


def verify(manifest_path: Path, *, verify_candidate: bool = True) -> None:
    manifest_path = manifest_path.resolve()
    _verify_manifest_pin(manifest_path)
    root = manifest_path.parents[4]
    manifest = _load_manifest(manifest_path)
    if not isinstance(manifest["candidate_identity"], str):
        raise VerificationError("candidate_identity must be a string")
    canonical_path = manifest["canonical_path"]
    if not isinstance(canonical_path, str):
        raise VerificationError("canonical_path must be a string")
    _relative_path(root, canonical_path, "canonical_path")

    archive = manifest["archive"]
    if not isinstance(archive, dict):
        raise VerificationError("archive must be an object")
    _require_keys(archive, {"path", "sha256", "metrics"}, "archive")
    if not isinstance(archive["path"], str) or not isinstance(archive["sha256"], str):
        raise VerificationError("archive path and sha256 must be strings")
    archive_path = _relative_path(root, archive["path"], "archive")
    archive_bytes = archive_path.read_bytes()
    archive_text = archive_bytes.decode("utf-8")
    if _sha256(archive_path) != archive["sha256"]:
        raise VerificationError("archive sha256 mismatch")
    metrics = archive["metrics"]
    if not isinstance(metrics, list) or not metrics:
        raise VerificationError("archive metrics must be a nonempty list")
    metric_names: set[str] = set()
    metric_extractors: set[str] = set()
    for metric in metrics:
        if not isinstance(metric, dict):
            raise VerificationError("archive metric must be an object")
        _require_keys(metric, {"name", "extractor", "expected"}, "archive metric")
        name, extractor, expected = metric["name"], metric["extractor"], metric["expected"]
        if not isinstance(name, str) or name in metric_names or extractor not in METRIC_KINDS or not isinstance(expected, int):
            raise VerificationError("invalid archive metric declaration")
        metric_names.add(name)
        metric_extractors.add(extractor)
        if _metric(extractor, archive_text, archive_bytes) != expected:
            raise VerificationError(f"archive metric mismatch: {name}")
    if metric_extractors != METRIC_KINDS:
        raise VerificationError(
            f"required archive metric missing: {sorted(METRIC_KINDS - metric_extractors)}"
        )

    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise VerificationError("artifacts must be a nonempty list")
    artifact_paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise VerificationError("artifact must be an object")
        _require_keys(artifact, {"path", "sha256"}, "artifact")
        artifact_path, expected_hash = artifact["path"], artifact["sha256"]
        if not isinstance(artifact_path, str) or not isinstance(expected_hash, str) or artifact_path in artifact_paths:
            raise VerificationError("invalid or duplicate artifact declaration")
        artifact_paths.add(artifact_path)
        resolved = _relative_path(root, artifact_path, "artifact")
        if artifact_path == str(manifest_path.relative_to(root)):
            if expected_hash != "self":
                raise VerificationError("manifest artifact must use sha256 self")
        elif expected_hash == "self" or _sha256(resolved) != expected_hash:
            raise VerificationError(f"artifact sha256 mismatch: {artifact_path}")
    if canonical_path not in artifact_paths or archive["path"] not in artifact_paths:
        raise VerificationError("artifact set must include canonical plan and archive")
    if not isinstance(manifest["bundle_sha256"], str) or _bundle_sha256(
        root, artifacts, manifest_path
    ) != manifest["bundle_sha256"]:
        raise VerificationError("artifact bundle sha256 mismatch")

    corpus = manifest["reference_corpus"]
    if not isinstance(corpus, dict):
        raise VerificationError("reference_corpus must be an object")
    _require_keys(
        corpus,
        {"paths", "matcher", "expected_path_count", "expected_count"},
        "reference_corpus",
    )
    corpus_paths = corpus["paths"]
    if (
        not isinstance(corpus_paths, list)
        or not corpus_paths
        or len(corpus_paths) != len(set(corpus_paths))
        or any(not isinstance(path, str) for path in corpus_paths)
        or not isinstance(corpus["matcher"], str)
        or not isinstance(corpus["expected_path_count"], int)
        or not isinstance(corpus["expected_count"], int)
    ):
        raise VerificationError("invalid reference corpus declaration")
    if len(corpus_paths) != corpus["expected_path_count"]:
        raise VerificationError(
            f"reference corpus path-count mismatch: {len(corpus_paths)}"
        )
    actual_references = sum(
        _relative_path(root, path, "reference corpus").read_text(encoding="utf-8").count(
            corpus["matcher"]
        )
        for path in corpus_paths
    )
    if actual_references != corpus["expected_count"]:
        raise VerificationError(f"canonical reference count mismatch: {actual_references}")

    milestones = manifest["milestones"]
    if not isinstance(milestones, list) or not milestones:
        raise VerificationError("milestones must be a nonempty list")
    milestone_ids: set[str] = set()
    allocated: set[str] = set()
    for milestone in milestones:
        if not isinstance(milestone, dict):
            raise VerificationError("milestone must be an object")
        _require_keys(milestone, {"id", "path", "status", "requirements"}, "milestone")
        milestone_id, path, status, requirements = (
            milestone["id"], milestone["path"], milestone["status"], milestone["requirements"]
        )
        if not isinstance(milestone_id, str) or milestone_id in milestone_ids or not isinstance(path, str) or not isinstance(status, str) or not isinstance(requirements, list):
            raise VerificationError("invalid milestone declaration")
        milestone_ids.add(milestone_id)
        milestone_text = _relative_path(root, path, "milestone").read_text(encoding="utf-8")
        if f"- Status: {status}" not in milestone_text:
            raise VerificationError(f"milestone status mismatch: {milestone_id}")
        for requirement in requirements:
            if requirement not in REQUIREMENT_IDS:
                raise VerificationError(f"unknown requirement allocation: {requirement!r}")
            allocated.add(requirement)
            if requirement not in milestone_text:
                raise VerificationError(f"milestone requirement literal missing: {milestone_id} {requirement}")
    if allocated != REQUIREMENT_IDS:
        raise VerificationError(f"incomplete requirement allocation: {sorted(REQUIREMENT_IDS - allocated)}")

    required_paths = manifest["required_paths"]
    if not isinstance(required_paths, list) or not all(isinstance(value, str) for value in required_paths):
        raise VerificationError("required_paths must be a string list")
    for value in required_paths:
        _relative_path(root, value, "required_paths")

    section_counts = manifest["section_counts"]
    if not isinstance(section_counts, list):
        raise VerificationError("section_counts must be a list")
    for expectation in section_counts:
        if not isinstance(expectation, dict):
            raise VerificationError("section count must be an object")
        _require_keys(expectation, {"owner", "literal", "expected_count"}, "section count")
        owner, literal, expected_count = (
            expectation["owner"], expectation["literal"], expectation["expected_count"]
        )
        if not isinstance(owner, str) or not isinstance(literal, str) or not isinstance(expected_count, int):
            raise VerificationError("invalid section count declaration")
        actual_count = _relative_path(root, owner, "section count owner").read_text(encoding="utf-8").count(literal)
        if actual_count != expected_count:
            raise VerificationError(f"section count mismatch: {owner}: {literal!r}")

    owners = artifact_paths | set(required_paths)
    obligations = manifest["obligations"]
    if not isinstance(obligations, list) or not obligations:
        raise VerificationError("obligations must be a nonempty list")
    obligation_ids: set[str] = set()
    for obligation in obligations:
        if not isinstance(obligation, dict):
            raise VerificationError("obligation must be an object")
        _require_keys(obligation, {"id", "detail_owner", "summary_owners", "required_literals", "archive_anchors"}, "obligation")
        identifier = obligation["id"]
        detail_owner = obligation["detail_owner"]
        summaries = obligation["summary_owners"]
        if not isinstance(identifier, str) or identifier in obligation_ids or not isinstance(detail_owner, str) or detail_owner not in owners or not isinstance(summaries, list) or not summaries:
            raise VerificationError("invalid obligation ownership")
        obligation_ids.add(identifier)
        if detail_owner in summaries or any(not isinstance(owner, str) or owner not in owners for owner in summaries):
            raise VerificationError(f"obligation must have exactly one distinct detail owner: {identifier}")
        literals = obligation["required_literals"]
        if not isinstance(literals, list) or not literals:
            raise VerificationError("obligation literals must be nonempty")
        for literal in literals:
            if not isinstance(literal, dict):
                raise VerificationError("obligation literal must be an object")
            _require_keys(literal, {"owner", "literal"}, "obligation literal")
            owner, value = literal["owner"], literal["literal"]
            if owner not in owners or not isinstance(value, str) or not value:
                raise VerificationError("invalid obligation literal")
            if value not in _relative_path(root, owner, "obligation owner").read_text(encoding="utf-8"):
                raise VerificationError(f"obligation literal missing: {identifier} in {owner}")
        anchors = obligation["archive_anchors"]
        if not isinstance(anchors, list) or not anchors or any(not isinstance(anchor, str) or not anchor for anchor in anchors):
            raise VerificationError("obligation archive anchors must be nonempty strings")
        for anchor in anchors:
            if anchor not in archive_text:
                raise VerificationError(f"archive anchor missing: {identifier}: {anchor}")
    if verify_candidate:
        _verify_candidate_identity(root, manifest["candidate_identity"])


def _copy_declared_files(source_manifest: Path, destination_root: Path) -> Path:
    source_manifest = source_manifest.resolve()
    source_root = source_manifest.parents[4]
    manifest = _load_manifest(source_manifest)
    paths = (
        {item["path"] for item in manifest["artifacts"]}
        | set(manifest["required_paths"])
        | set(manifest["reference_corpus"]["paths"])
        | {manifest["candidate_identity"]}
    )
    for relative in paths:
        source = source_root / relative
        target = destination_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    copied_manifest = destination_root / source_manifest.relative_to(source_root)
    source_pin = _manifest_pin_path(source_manifest)
    copied_pin = _manifest_pin_path(copied_manifest)
    copied_pin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_pin, copied_pin)
    identity_source = source_root / manifest["candidate_identity"]
    identity_target = destination_root / manifest["candidate_identity"]
    identity_pin_target = _manifest_pin_path(identity_target)
    identity_pin_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_manifest_pin_path(identity_source), identity_pin_target)
    return copied_manifest


def _write_manifest_and_pin(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _manifest_pin_path(path).write_text(f"{_sha256(path)}  {path.name}\n", encoding="utf-8")


def _refresh_bundle(root: Path, manifest_path: Path, data: dict[str, Any]) -> None:
    for artifact in data["artifacts"]:
        if artifact["sha256"] != "self":
            artifact["sha256"] = _sha256(root / artifact["path"])
    data["bundle_sha256"] = _bundle_sha256(root, data["artifacts"], manifest_path)
    _write_manifest_and_pin(manifest_path, data)


def _expect_failure_with_message(
    manifest_path: Path, label: str, expected_message: str
) -> None:
    try:
        verify(manifest_path, verify_candidate=False)
    except VerificationError as exc:
        if expected_message and expected_message not in str(exc):
            raise VerificationError(
                f"self-test mutation {label!r} failed for the wrong reason: {exc}"
            ) from exc
        return
    raise VerificationError(f"self-test mutation unexpectedly passed: {label}")


def _write_test_candidate_identity(root: Path, relative_path: str) -> Path:
    status = _command_bytes(
        root, "git", "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    untracked_count, untracked_digest = _untracked_content_digest(root, status)
    anchor_path = "anchor.txt"
    anchor_sha = _sha256(root / anchor_path)
    coordination_entry = f"{anchor_path}\0{anchor_sha}\n".encode()
    identity = {
        "format": "memorii.dirty-coordination-candidate.v1",
        "created": "self-test",
        "git_head": _command_bytes(root, "git", "rev-parse", "HEAD").decode().strip(),
        "tree_state": "dirty-local",
        "review_scope": "candidate identity self-test",
        "git_status": {
            "command": "git status --porcelain=v1 -z --untracked-files=all",
            "entry_count": len(_status_records(status)),
            "sha256": hashlib.sha256(status).hexdigest(),
        },
        "tracked_diff": {
            "command": "git diff --binary",
            "sha256": hashlib.sha256(
                _command_bytes(root, "git", "diff", "--binary")
            ).hexdigest(),
        },
        "staged_diff": {
            "command": "git diff --cached --binary",
            "sha256": hashlib.sha256(
                _command_bytes(root, "git", "diff", "--cached", "--binary")
            ).hexdigest(),
        },
        "untracked_content_manifest": {
            "algorithm": "self-test raw Git path bytes + NUL + file sha256 + newline",
            "file_count": untracked_count,
            "sha256": untracked_digest,
        },
        "coordination_artifact_digest": {
            "algorithm": "self-test displayed path + NUL + file sha256 + newline",
            "artifact_count": 1,
            "sha256": hashlib.sha256(coordination_entry).hexdigest(),
        },
        "coordination_artifacts": [
            {"path": anchor_path, "sha256": anchor_sha},
        ],
        "self_exclusions": [relative_path, f"{relative_path}.sha256"],
        "evidence_limitations": ["self-test only"],
    }
    identity_path = root / relative_path
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    _manifest_pin_path(identity_path).write_text(
        f"{_sha256(identity_path)}  {identity_path.name}\n", encoding="utf-8"
    )
    return identity_path


def _expect_identity_failure_with_message(
    root: Path, relative_path: str, label: str, expected_message: str
) -> None:
    try:
        _verify_candidate_identity(root, relative_path)
    except VerificationError as exc:
        if expected_message not in str(exc):
            raise VerificationError(
                f"identity self-test {label!r} failed for the wrong reason: {exc}"
            ) from exc
        return
    raise VerificationError(f"identity self-test unexpectedly passed: {label}")


def _candidate_identity_self_test(parent: Path) -> None:
    root = parent / "candidate-identity"
    root.mkdir()
    root = root.resolve()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Memorii Self Test"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "self-test@invalid"], cwd=root, check=True
    )
    (root / "anchor.txt").write_text("anchor\n", encoding="utf-8")
    candidate = root / "candidate.txt"
    candidate.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "anchor.txt", "candidate.txt"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "base"],
        cwd=root,
        check=True,
    )
    (root / ".git" / "info" / "exclude").write_text(".review/\n", encoding="utf-8")
    identity_relative = ".review/identity.json"

    candidate.write_text("staged-a\n", encoding="utf-8")
    subprocess.run(["git", "add", "candidate.txt"], cwd=root, check=True)
    _write_test_candidate_identity(root, identity_relative)
    _verify_candidate_identity(root, identity_relative)
    candidate.write_text("staged-b\n", encoding="utf-8")
    subprocess.run(["git", "add", "candidate.txt"], cwd=root, check=True)
    _expect_identity_failure_with_message(
        root, identity_relative, "staged content change", "staged diff mismatch"
    )

    odd_path = root / "odd\nname.txt"
    odd_path.write_text("first\n", encoding="utf-8")
    _write_test_candidate_identity(root, identity_relative)
    _verify_candidate_identity(root, identity_relative)
    odd_path.write_text("second\n", encoding="utf-8")
    _expect_identity_failure_with_message(
        root, identity_relative, "newline path content change", "untracked content mismatch"
    )


def self_test(manifest_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="workplan-split-") as directory:
        copied_manifest = _copy_declared_files(manifest_path, Path(directory))
        verify(copied_manifest, verify_candidate=False)
        root = copied_manifest.parents[4]
        data = _load_manifest(copied_manifest)

        archive_path = root / data["archive"]["path"]
        archive_path.write_bytes(archive_path.read_bytes() + b"x")
        _expect_failure_with_message(
            copied_manifest, "archive byte change", "archive sha256 mismatch"
        )

        copied_manifest = _copy_declared_files(manifest_path, Path(directory) / "missing")
        data = _load_manifest(copied_manifest)
        (copied_manifest.parents[4] / data["milestones"][0]["path"]).unlink()
        _expect_failure_with_message(
            copied_manifest, "missing milestone", "required file is missing"
        )

        copied_manifest = _copy_declared_files(manifest_path, Path(directory) / "owner")
        data = _load_manifest(copied_manifest)
        literal = next(
            literal
            for obligation in data["obligations"]
            for literal in obligation["required_literals"]
            if literal["literal"] == "sole detailed owner"
        )
        owner_path = copied_manifest.parents[4] / literal["owner"]
        owner_path.write_text(owner_path.read_text(encoding="utf-8").replace(literal["literal"], "", 1), encoding="utf-8")
        _refresh_bundle(copied_manifest.parents[4], copied_manifest, data)
        _expect_failure_with_message(
            copied_manifest, "owner literal deletion", "obligation literal missing"
        )

        copied_manifest = _copy_declared_files(manifest_path, Path(directory) / "manifest")
        data = _load_manifest(copied_manifest)
        data["archive"]["metrics"][0]["expected"] += 1
        _write_manifest_and_pin(copied_manifest, data)
        _expect_failure_with_message(
            copied_manifest, "manifest metric error", "archive metric mismatch"
        )

        copied_manifest = _copy_declared_files(manifest_path, Path(directory) / "substitution")
        data = _load_manifest(copied_manifest)
        data["reference_corpus"]["matcher"] = "missing canonical reference"
        _write_manifest_and_pin(copied_manifest, data)
        _expect_failure_with_message(
            copied_manifest,
            "manifest substitution error",
            "canonical reference count mismatch",
        )

        copied_manifest = _copy_declared_files(manifest_path, Path(directory) / "pin")
        data = _load_manifest(copied_manifest)
        data["section_counts"][0]["expected_count"] += 1
        copied_manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        _expect_failure_with_message(
            copied_manifest, "unpinned manifest substitution", "manifest pin mismatch"
        )

        copied_manifest = _copy_declared_files(manifest_path, Path(directory) / "escape")
        data = _load_manifest(copied_manifest)
        data["required_paths"].append("../../escape")
        _write_manifest_and_pin(copied_manifest, data)
        _expect_failure_with_message(
            copied_manifest, "path escape", "path escapes repository root"
        )

        copied_manifest = _copy_declared_files(
            manifest_path, Path(directory) / "requirements"
        )
        data = _load_manifest(copied_manifest)
        for milestone in data["milestones"]:
            if "SIA-R01" in milestone["requirements"]:
                milestone["requirements"].remove("SIA-R01")
        _write_manifest_and_pin(copied_manifest, data)
        _expect_failure_with_message(
            copied_manifest,
            "requirement allocation",
            "incomplete requirement allocation",
        )

        copied_manifest = _copy_declared_files(
            manifest_path, Path(directory) / "ownership"
        )
        data = _load_manifest(copied_manifest)
        data["obligations"][0]["summary_owners"].append(
            data["obligations"][0]["detail_owner"]
        )
        _write_manifest_and_pin(copied_manifest, data)
        _expect_failure_with_message(
            copied_manifest,
            "detail owner collision",
            "exactly one distinct detail owner",
        )

        copied_manifest = _copy_declared_files(
            manifest_path, Path(directory) / "artifact"
        )
        data = _load_manifest(copied_manifest)
        resume_path = copied_manifest.parents[4] / next(
            artifact["path"]
            for artifact in data["artifacts"]
            if artifact["path"].endswith("/resume.md")
        )
        resume_path.write_text(
            resume_path.read_text(encoding="utf-8") + "mutation\n", encoding="utf-8"
        )
        _expect_failure_with_message(
            copied_manifest, "ordinary artifact mutation", "artifact sha256 mismatch"
        )

        copied_manifest = _copy_declared_files(
            manifest_path, Path(directory) / "detailed-owner-artifact"
        )
        data = _load_manifest(copied_manifest)
        debug_path = copied_manifest.parents[4] / next(
            artifact["path"]
            for artifact in data["artifacts"]
            if artifact["path"].endswith("/conflict-authority-proof-failures-2026-08-04/debug.plan.md")
        )
        debug_path.write_text(
            debug_path.read_text(encoding="utf-8") + "mutation\n", encoding="utf-8"
        )
        _expect_failure_with_message(
            copied_manifest,
            "detailed owner artifact mutation",
            "artifact sha256 mismatch",
        )

        copied_manifest = _copy_declared_files(
            manifest_path, Path(directory) / "corpus"
        )
        data = _load_manifest(copied_manifest)
        data["reference_corpus"]["paths"].pop()
        data["reference_corpus"]["expected_count"] = sum(
            (
                copied_manifest.parents[4] / path
            ).read_text(encoding="utf-8").count(data["reference_corpus"]["matcher"])
            for path in data["reference_corpus"]["paths"]
        )
        _write_manifest_and_pin(copied_manifest, data)
        _expect_failure_with_message(
            copied_manifest,
            "corpus scope reduction",
            "reference corpus path-count mismatch",
        )

        copied_manifest = _copy_declared_files(
            manifest_path, Path(directory) / "metrics"
        )
        data = _load_manifest(copied_manifest)
        data["archive"]["metrics"] = [
            metric
            for metric in data["archive"]["metrics"]
            if metric["extractor"] != "closure_marker_count"
        ]
        _write_manifest_and_pin(copied_manifest, data)
        _expect_failure_with_message(
            copied_manifest,
            "metric scope reduction",
            "required archive metric missing",
        )
        _candidate_identity_self_test(Path(directory))
    print("workplan split self-test: passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", type=Path, default=Path("docs/work/semantic_ingestion/history/implementation-split-manifest.json"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        verify(args.manifest)
        if args.self_test:
            self_test(args.manifest)
    except VerificationError as exc:
        print(f"workplan split verification failed: {exc}")
        return 1
    print("workplan split verification: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

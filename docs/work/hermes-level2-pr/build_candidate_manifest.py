"""Build the revision-bound Hermes Level 2 candidate manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "docs/work/hermes-conversation-memory-trial/candidate-manifest.json"


def _git(*args: str) -> bytes:
    return subprocess.check_output(("git", *args), cwd=ROOT)


def _included(path: str) -> bool:
    return not path.startswith("docs/work/")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: build_candidate_manifest.py BASE_REVISION CANDIDATE_REVISION")
    base, candidate = sys.argv[1:]
    changed: list[tuple[str, str]] = []
    for line in _git("diff", "--name-status", f"{base}...{candidate}").decode().splitlines():
        columns = line.split("\t")
        status = columns[0]
        if status.startswith(("R", "C")):
            path = columns[2]
        else:
            path = columns[1]
        if _included(path):
            changed.append((path, status))

    files: list[dict[str, object]] = []
    for path, status in sorted(changed):
        content_revision = base if status == "D" else candidate
        content = _git("show", f"{content_revision}:{path}")
        files.append({
            "path": path,
            "status": status,
            "content_revision": content_revision,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        })
    files_digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest = {
        "schema": "memorii.implementation_candidate_manifest.v2",
        "base_revision": base,
        "candidate_revision": candidate,
        "branch": "codex/hermes-level2",
        "tree_state_at_candidate_revision": "clean",
        "exclusions": [
            "docs/work/**",
            "local caches, environments, and build outputs",
        ],
        "changed_file_count": len(files),
        "changed_files_sha256": files_digest,
        "files": files,
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()

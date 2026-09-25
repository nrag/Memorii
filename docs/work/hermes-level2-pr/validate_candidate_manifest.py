"""Validate the frozen Hermes Level 2 candidate manifest against Git."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "docs/work/hermes-conversation-memory-trial/candidate-manifest.json"


def _git(*args: str) -> bytes:
    return subprocess.check_output(("git", *args), cwd=ROOT)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = manifest["base_revision"]
    candidate = manifest["candidate_revision"]
    observed: dict[str, str] = {}
    for line in _git("diff", "--name-status", f"{base}...{candidate}").decode().splitlines():
        columns = line.split("\t")
        status = columns[0]
        path = columns[2] if status.startswith(("R", "C")) else columns[1]
        if not path.startswith("docs/work/"):
            observed[path] = status
    entries = manifest["files"]
    declared = {entry["path"]: entry["status"] for entry in entries}
    if declared != observed:
        raise SystemExit(f"candidate changed-surface mismatch: declared={declared!r} observed={observed!r}")
    for entry in entries:
        revision = entry["content_revision"]
        content = _git("show", f"{revision}:{entry['path']}")
        if len(content) != entry["size"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise SystemExit(f"candidate content mismatch: {entry['path']}")
    digest = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != manifest["changed_files_sha256"]:
        raise SystemExit("candidate file-list digest mismatch")
    if manifest["changed_file_count"] != len(entries):
        raise SystemExit("candidate file count mismatch")
    print(json.dumps({
        "base_revision": base,
        "candidate_revision": candidate,
        "changed_file_count": len(entries),
        "changed_files_sha256": digest,
        "deletions": sorted(path for path, status in declared.items() if status == "D"),
        "result": "valid",
    }, sort_keys=True))


if __name__ == "__main__":
    main()

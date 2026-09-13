"""Verify retained historical evidence without requiring a Git checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def contained_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root):
        raise ValueError(f"evidence path escapes repository: {relative}")
    return path


def checked_bytes(root: Path, relative: str, expected: str) -> bytes:
    data = contained_path(root, relative).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"evidence digest mismatch: {relative}")
    return data


def verify(root: Path) -> dict[str, int]:
    retention = json.loads(
        (root / "docs/work/scoped_context_implementation/evidence-retention.json").read_text()
    )
    if retention["version"] != 1:
        raise ValueError("unsupported evidence retention version")
    reviewed = json.loads(checked_bytes(
        root, retention["review_manifest"], retention["review_manifest_sha256"]
    ))
    source = json.loads(checked_bytes(
        root, retention["source_manifest"], retention["source_manifest_sha256"]
    ))
    overrides = retention["archived_review_metadata"]
    allowed = {
        "docs/work/scoped_context_implementation/implementation.plan.md",
        "docs/work/scoped_context_implementation/testing.plan.md",
        "docs/work/scoped_context_implementation/resume.md",
    }
    if set(overrides) != allowed or not allowed.issubset(reviewed["files"]):
        raise ValueError("only the three completion metadata snapshots may be redirected")
    logs = 0
    for relative, expected in reviewed["files"].items():
        retained = overrides.get(relative, relative)
        if relative in overrides:
            exact = f"docs/work/scoped_context_implementation/history/{expected}.md"
            if retained != exact:
                raise ValueError("review metadata archive must be content-addressed")
        data = checked_bytes(root, retained, expected)
        if relative.endswith(".log"):
            logs += 1
        elif relative.endswith(".json"):
            receipt = json.loads(data)
            if isinstance(receipt, dict) and "log_sha256" in receipt:
                checked_bytes(root, str(Path(relative).with_suffix(".log")), receipt["log_sha256"])
    for relative, expected in source["files"].items():
        checked_bytes(root, relative, expected)
    return {"reviewed_files": len(reviewed["files"]), "source_files": len(source["files"]), "logs": logs}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    try:
        result = verify(args.root.resolve())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"retained evidence verification failed: {exc}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

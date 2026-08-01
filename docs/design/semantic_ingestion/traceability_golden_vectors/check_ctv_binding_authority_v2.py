"""Hermetically reproduce and validate the CTV binding authority v2."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


EXPECTED_SCHEMAS = 56
EXPECTED_ENUM_ROWS = 249
EXPECTED_PROFILE_DIGEST = (
    "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f"
)
V1_RAW_SHA256 = "9137fcadaf511b8d8953b628b9689764eb79c0bfbf787ee1d7f6462abb83efe1"
V1_CANONICAL_SHA256 = (
    "e67556e7c61bce1f0686195c5f4219c6e8143d99a71795bf2d371168c8262506"
)
ISOLATION_DIAGNOSTIC = (
    "CTV v2 authority checker requires Python isolated mode; invoke with -I"
)
ALLOWED_VALIDATOR_IMPORTS = {
    "__future__",
    "argparse",
    "ast",
    "base64",
    "copy",
    "errno",
    "hashlib",
    "json",
    "os",
    "pathlib",
    "re",
    "tempfile",
    "threading",
    "typing",
}
BOOTSTRAP = r'''from __future__ import annotations
import os
import runpy
import sys
from pathlib import Path

validator, design, registry, authority, *arguments = sys.argv[1:]
authority_path = Path(authority).resolve(strict=False)
allowed = {
    Path(validator).resolve(strict=False),
    Path(design).resolve(strict=False),
    Path(registry).resolve(strict=False),
    authority_path,
}
runtime_roots = {
    Path(sys.base_prefix).resolve(strict=False),
    Path(sys.prefix).resolve(strict=False),
}
denied_prefixes = (
    "socket.", "subprocess.", "ctypes.", "urllib.", "http.", "ftplib.",
)
denied_events = {
    "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork",
    "os.forkpty", "os.putenv", "os.unsetenv",
}

def audit(event, args):
    if event in denied_events or event.startswith(denied_prefixes):
        raise PermissionError(f"forbidden audit event: {event}")
    if event != "open" or not args or not isinstance(args[0], (str, bytes)):
        return
    raw = os.fsdecode(args[0])
    if raw in {"/dev/null", os.devnull}:
        return
    path = Path(raw).resolve(strict=False)
    is_authority_temp = (
        path.parent == authority_path.parent
        and path.name.startswith(f".{authority_path.name}.")
        and path.name.endswith(".tmp")
    )
    try:
        authority_relative = path.relative_to(authority_path.parent)
    except ValueError:
        is_authority_scratch = False
    else:
        is_authority_scratch = bool(authority_relative.parts) and (
            authority_relative.parts[0].startswith(
                f".{authority_path.name}.self-test."
            )
        )
    if path in allowed or any(path.is_relative_to(root) for root in runtime_roots):
        return
    if path == authority_path.parent or is_authority_temp or is_authority_scratch:
        return
    raise PermissionError(f"undeclared file access: {path}")

sys.addaudithook(audit)
sys.argv = [validator, "--design", design, "--registry", registry,
            "--authority", authority, *arguments]
runpy.run_path(validator, run_name="__main__")
'''


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        .encode("ascii")
        + b"\n"
    )


def strict_json_loads(value: str | bytes) -> Any:
    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object name: {key}")
            result[key] = item
        return result

    return json.loads(value, object_pairs_hook=closed_object)


def marked_v1(document: bytes) -> bytes:
    pattern = (
        rb"^`\[SIA-CTV-ENUM-REGISTRY-V1-BEGIN\]`\n```json\n"
        rb"(.*?)"
        rb"```\n`\[SIA-CTV-ENUM-REGISTRY-V1-END\]`$"
    )
    matches = re.findall(pattern, document, re.DOTALL | re.MULTILINE)
    if len(matches) != 1:
        raise ValueError("expected exactly one v1 enum baseline block")
    return matches[0]


def validate_v1_baseline(document: bytes) -> None:
    payload = marked_v1(document)
    if sha256(payload) != V1_RAW_SHA256:
        raise ValueError("v1 enum baseline raw digest mismatch")
    parsed = strict_json_loads(payload)
    if sha256(canonical(parsed)) != V1_CANONICAL_SHA256:
        raise ValueError("v1 enum baseline canonical digest mismatch")


def imported_modules(source: bytes) -> set[str]:
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise ValueError("validator relative imports are forbidden")
            imported.add((node.module or "").split(".", 1)[0])
    return imported


def validate_import_boundary(source: bytes) -> None:
    tree = ast.parse(source)
    imported = imported_modules(source)
    forbidden = imported - ALLOWED_VALIDATOR_IMPORTS
    if forbidden:
        raise ValueError(f"validator imports outside closed stdlib set: {forbidden}")
    for statement in tree.body:
        if isinstance(
            statement,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom),
        ):
            continue
        if (
            isinstance(statement, ast.If)
            and isinstance(statement.test, ast.Compare)
            and isinstance(statement.test.left, ast.Name)
            and statement.test.left.id == "__name__"
        ):
            continue
        if any(isinstance(node, ast.Call) for node in ast.walk(statement)):
            raise ValueError("validator top-level reads or calls are forbidden")


def require_sha256(label: str, value: bytes, expected: str) -> None:
    actual = sha256(value)
    if actual != expected:
        raise ValueError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")


def _run_validator(
    root: Path, *, write: bool, check: bool
) -> subprocess.CompletedProcess[str]:
    arguments = ["--self-test"]
    if write:
        arguments.append("--write")
    command = [
        sys.executable,
        "-I",
        str(root / "bootstrap.py"),
        str(root / "validator.py"),
        str(root / "design.md"),
        str(root / "registry.json"),
        str(root / "authority.json"),
        *arguments,
    ]
    return subprocess.run(
        command,
        cwd=root,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
        check=check,
        capture_output=True,
        text=True,
    )


def run_validator(root: Path, *, write: bool) -> bytes:
    return _run_validator(root, write=write, check=True).stdout.encode("utf-8")


def materialize_replica(
    root: Path,
    *,
    design: bytes,
    registry: bytes,
    validator: bytes,
    authority: bytes = b"",
) -> None:
    """Materialize a replica solely from the already verified byte snapshots."""
    root.mkdir()
    (root / "bootstrap.py").write_bytes(BOOTSTRAP.encode("ascii"))
    (root / "design.md").write_bytes(design)
    (root / "registry.json").write_bytes(registry)
    (root / "validator.py").write_bytes(validator)
    (root / "authority.json").write_bytes(authority)


def validate_snapshot_materialization(
    *, design: bytes, registry: bytes, validator: bytes
) -> None:
    """Prove replica materialization does not consult mutable source paths."""
    with tempfile.TemporaryDirectory() as temporary:
        parent = Path(temporary)
        source_paths = {
            "design": parent / "source-design.md",
            "registry": parent / "source-registry.json",
            "validator": parent / "source-validator.py",
        }
        snapshots = {"design": design, "registry": registry, "validator": validator}
        for name, path in source_paths.items():
            path.write_bytes(snapshots[name])
        for name, path in source_paths.items():
            captured = {key: value for key, value in snapshots.items()}
            path.write_bytes(b"substituted-after-capture\n")
            root = parent / f"replica-{name}"
            materialize_replica(root, **captured)
            for field, filename in (
                ("design", "design.md"),
                ("registry", "registry.json"),
                ("validator", "validator.py"),
            ):
                if (root / filename).read_bytes() != captured[field]:
                    raise AssertionError(f"replica materialization reread {field} path")


def validate_audit_denial(
    *, design: bytes, registry: bytes, validator: bytes, checked: bytes
) -> None:
    """Exercise the real bootstrap audit hook against an undeclared read probe."""
    marker = b"\nif __name__ == \"__main__\":\n"
    with tempfile.TemporaryDirectory() as temporary:
        parent = Path(temporary)
        root = parent / "replica"
        undeclared = (root / "undeclared-probe.txt").resolve()
        probe_read = (
            "\nPath(" + json.dumps(str(undeclared), ensure_ascii=True) + ").read_bytes()"
        ).encode("ascii")
        probe = validator.replace(marker, probe_read + marker, 1)
        if probe == validator:
            raise AssertionError("validator main guard missing for audit probe")
        if imported_modules(probe) != imported_modules(validator):
            raise AssertionError("audit probe changed the reviewed validator imports")
        materialize_replica(
            root,
            design=design,
            registry=registry,
            validator=probe,
            authority=checked,
        )
        undeclared.write_bytes(b"audit-denial-known-answer\n")
        probe_identity = sha256(probe)
        if sha256((root / "validator.py").read_bytes()) != probe_identity:
            raise AssertionError("audit probe identity changed during materialization")
        before_authority = (root / "authority.json").read_bytes()
        completed = _run_validator(root, write=False, check=False)
        expected_denial = f"undeclared file access: {undeclared}"
        if completed.returncode == 0 or expected_denial not in completed.stderr:
            raise AssertionError("undeclared validator read was not denied by audit")
        if before_authority != checked or (root / "authority.json").read_bytes() != checked:
            raise AssertionError("audit denial changed authority bytes")
        if list(root.glob(".authority.json.*.tmp")):
            raise AssertionError("audit denial left an authority temporary")


def validate_isolated_startup() -> None:
    """Prove the canonical isolated interpreter ignores a sibling stdlib shadow."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        marker = root / "shadow-executed"
        shadow = (
            "open("
            + repr(str(marker))
            + ", 'wb').write(b'shadow executed')\n"
            + "raise RuntimeError('sibling hashlib shadow executed')\n"
        )
        (root / "hashlib.py").write_text(shadow, encoding="ascii")
        expected_digest = hashlib.sha256(b"isolated-startup-known-answer").hexdigest()
        probe = (
            "import sys\n"
            f"if not sys.flags.isolated: raise SystemExit({ISOLATION_DIAGNOSTIC!r})\n"
            "import hashlib\n"
            "print(hashlib.sha256(b'isolated-startup-known-answer').hexdigest())\n"
        )
        script = root / "startup-probe.py"
        script.write_text(probe, encoding="ascii")
        completed = subprocess.run(
            [sys.executable, "-I", str(script)],
            cwd=root,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
        )
        if (
            completed.returncode != 0
            or completed.stdout.strip() != expected_digest
            or marker.exists()
        ):
            raise AssertionError("isolated startup admitted a sibling stdlib shadow")


def validate_nonisolated_checker_entry(checker: bytes) -> None:
    """Prove the captured checker entry rejects a clean non-isolated launch."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        copied_checker = root / "check_ctv_binding_authority_v2.py"
        copied_checker.write_bytes(checker)
        completed = subprocess.run(
            [sys.executable, str(copied_checker)],
            cwd=root,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
        )
        if (
            completed.returncode != 1
            or completed.stdout != ""
            or completed.stderr != ISOLATION_DIAGNOSTIC + "\n"
        ):
            raise AssertionError(
                "captured checker entry did not reject clean non-isolated startup"
            )


def validate_authority_shape(authority_bytes: bytes) -> None:
    authority = strict_json_loads(authority_bytes)
    if len(authority["schemas"]) != EXPECTED_SCHEMAS:
        raise ValueError("authority schema count mismatch")
    if len(authority["enum_registry"]["rows"]) != EXPECTED_ENUM_ROWS:
        raise ValueError("authority enum-row count mismatch")
    if authority["profile"]["digest"] != EXPECTED_PROFILE_DIGEST:
        raise ValueError("authority profile digest mismatch")


def validate_authority_duplicate_rejection(authority_bytes: bytes) -> None:
    authority = strict_json_loads(authority_bytes)
    root_key = next(iter(sorted(authority)))
    duplicate_root = (
        "{"
        + json.dumps(root_key, ensure_ascii=True)
        + ":"
        + json.dumps(
            authority[root_key],
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + ","
    ).encode("ascii") + authority_bytes[1:]
    binding = authority["schemas"][0]["binding_digest"]
    nested = (
        '"binding_digest":' + json.dumps(binding, ensure_ascii=True)
    ).encode("ascii")
    duplicate_nested = authority_bytes.replace(nested, nested + b"," + nested, 1)
    for value in (duplicate_root, duplicate_nested):
        try:
            validate_authority_shape(value)
        except ValueError:
            continue
        raise AssertionError("duplicate checked-authority JSON was accepted")


def main() -> None:
    if not sys.flags.isolated:
        raise SystemExit(ISOLATION_DIAGNOSTIC)
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("--expected-design-sha256", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--expected-authority-sha256", required=True)
    parser.add_argument("--expected-validator-sha256", required=True)
    parser.add_argument("--expected-checker-sha256", required=True)
    args = parser.parse_args()

    design = args.design.read_bytes()
    registry = args.registry.read_bytes()
    checked = args.authority.read_bytes()
    validator = args.validator.read_bytes()
    checker = Path(__file__).read_bytes()
    for label, value, expected in (
        ("design", design, args.expected_design_sha256),
        ("registry", registry, args.expected_registry_sha256),
        ("authority", checked, args.expected_authority_sha256),
        ("validator", validator, args.expected_validator_sha256),
        ("checker", checker, args.expected_checker_sha256),
    ):
        require_sha256(label, value, expected)
    validate_v1_baseline(design)
    validate_authority_shape(checked)
    validate_authority_duplicate_rejection(checked)
    validate_import_boundary(validator)
    validate_nonisolated_checker_entry(checker)

    v1_payload = marked_v1(design)
    mutated = design.replace(v1_payload, v1_payload.replace(b"\n", b"\n ", 1), 1)
    try:
        validate_v1_baseline(mutated)
    except ValueError:
        pass
    else:
        raise AssertionError("v1 baseline mutation passed integrity validation")

    validate_snapshot_materialization(
        design=design, registry=registry, validator=validator
    )
    validate_audit_denial(
        design=design, registry=registry, validator=validator, checked=checked
    )
    validate_isolated_startup()

    generated: list[bytes] = []
    with tempfile.TemporaryDirectory() as temporary:
        parent = Path(temporary)
        for name in ("a", "b"):
            root = parent / name
            materialize_replica(
                root, design=design, registry=registry, validator=validator
            )
            run_validator(root, write=True)
            generated.append((root / "authority.json").read_bytes())
            run_validator(root, write=False)

    if generated[0] != generated[1] or generated[0] != checked:
        raise ValueError(
            "hermetic authority outputs differ from each other or checked bytes"
        )
    print(
        "CTV v2 authority checked: "
        f"sha256={sha256(checked)} schemas={EXPECTED_SCHEMAS} "
        f"enum_rows={EXPECTED_ENUM_ROWS} replicas=2"
    )


if __name__ == "__main__":
    main()

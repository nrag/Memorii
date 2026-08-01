"""Hermetic checker for lifecycle-root signer-provenance design evidence."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

EXPECTED = {
    "design": "e7de038a5cad8f8d95536d60d35621472a79588e100c2da8633a9dd1fcfb5e7a",
    "matrix": "a3375bd0d8d01cf7a7c9d7d16d90945d792d932eca7161097f6ee5ba44d3f604",
    "fixture": "d3c1dce10624365647cbb00926f63b6deabe681e51a138bc3de88d7c60faef69",
    "validator": "46bbda1afb6ccbec5a49ea668752c19a7b1354b94515a33365191cee01745edb",
}
ALLOWED_VALIDATOR_IMPORTS = {
    "__future__",
    "argparse",
    "copy",
    "datetime",
    "json",
    "pathlib",
    "re",
    "typing",
}
FIXTURE_KEYS = {
    "format",
    "authority_anchor",
    "accepted_roots",
    "successor_history",
    "boundary_witnesses",
    "history_negative_cases",
    "negative_cases",
}
ISOLATION_DIAGNOSTIC = (
    "lifecycle-root semantic checker requires Python isolated mode; invoke with -I"
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict_json(raw: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    return json.loads(raw, object_pairs_hook=object_pairs)


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
    forbidden = imported_modules(source) - ALLOWED_VALIDATOR_IMPORTS
    if forbidden:
        raise ValueError(f"validator imports outside closed stdlib set: {sorted(forbidden)}")


def validate_matrix(matrix: Any, fixture: Any) -> None:
    if not isinstance(matrix, dict) or not isinstance(matrix.get("cases"), list):
        raise ValueError("matrix shape invalid")
    if not isinstance(fixture, dict) or set(fixture) != FIXTURE_KEYS:
        raise ValueError("fixture shape invalid")
    matrix_cases = {
        case.get("case_id")
        for case in matrix["cases"]
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    fixture_cases = {
        case.get("case_id")
        for case in (
            fixture["negative_cases"]
            + fixture["boundary_witnesses"]
            + fixture["history_negative_cases"]
        )
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    if len(fixture_cases) != len(
        fixture["negative_cases"]
        + fixture["boundary_witnesses"]
        + fixture["history_negative_cases"]
    ):
        raise ValueError("fixture case IDs are not unique")
    if not fixture_cases.issubset(matrix_cases):
        raise ValueError(
            f"matrix missing witness cases: {sorted(fixture_cases - matrix_cases)}"
        )


def run_validator(validator: Path, fixture: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            str(validator),
            "--fixture",
            str(fixture),
            "--self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def validate(
    design: Path,
    matrix_path: Path,
    fixture_path: Path,
    validator_path: Path,
    *,
    pinned: bool,
) -> str:
    if pinned:
        for label, path in (
            ("design", design),
            ("matrix", matrix_path),
            ("fixture", fixture_path),
            ("validator", validator_path),
        ):
            actual = sha(path)
            if actual != EXPECTED[label]:
                raise ValueError(
                    f"{label} SHA-256 mismatch: expected {EXPECTED[label]}, got {actual}"
                )
    design_text = design.read_text(encoding="utf-8")
    required_design_tokens = (
        "class TraceabilityLifecycleRootGenesisSignerProvenance(BaseModel):",
        "TraceabilityLifecycleRootSignerProvenance = (",
        "signer_coordinate: TraceabilityLifecycleRootSignerProvenance",
        "signer_coordinates: tuple[TraceabilityLifecycleRootSignerProvenance, ...]",
        "sequence-one successor coordinate, sequence-two genesis member",
    )
    missing = [token for token in required_design_tokens if token not in design_text]
    if missing:
        raise ValueError(f"design semantic declaration missing: {missing}")
    validator_source = validator_path.read_bytes()
    validate_import_boundary(validator_source)
    matrix = strict_json(matrix_path.read_bytes())
    fixture = strict_json(fixture_path.read_bytes())
    validate_matrix(matrix, fixture)
    result = run_validator(validator_path, fixture_path)
    if result.returncode != 0:
        raise ValueError(f"semantic validator failed: {result.stderr or result.stdout}")
    expected_output = '{"accepted": 6, "rejected": 41}\n'
    if result.stdout != expected_output or result.stderr:
        raise ValueError("semantic validator output mismatch")
    return result.stdout


def reject_mutated_fixture(
    design: Path,
    matrix: Path,
    fixture: Path,
    validator: Path,
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copied_fixture = root / fixture.name
        value = strict_json(fixture.read_bytes())
        value["accepted_roots"][0]["signer_coordinates"][0]["authority_id"] = "authority-2"
        copied_fixture.write_text(
            json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="ascii",
        )
        try:
            validate(design, matrix, copied_fixture, validator, pinned=False)
        except ValueError:
            return
        raise AssertionError("mutated accepted genesis fixture was accepted")


def reject_deleted_boundary_witness(
    design: Path,
    matrix: Path,
    fixture: Path,
    validator: Path,
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        copied_fixture = Path(directory) / fixture.name
        value = strict_json(fixture.read_bytes())
        value["boundary_witnesses"] = value["boundary_witnesses"][:-1]
        copied_fixture.write_text(
            json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="ascii",
        )
        try:
            validate(design, matrix, copied_fixture, validator, pinned=False)
        except ValueError:
            return
        raise AssertionError("deleted interval-boundary witness was accepted")


def reject_mutated_matrix(
    design: Path,
    matrix: Path,
    fixture: Path,
    validator: Path,
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copied_matrix = root / matrix.name
        value = strict_json(matrix.read_bytes())
        value["cases"] = value["cases"][1:]
        copied_matrix.write_text(
            json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="ascii",
        )
        fixture_value = strict_json(fixture.read_bytes())
        removed_id = value["cases"][0]["case_id"]
        if removed_id in {
            case["case_id"] for case in fixture_value["negative_cases"]
        }:
            raise AssertionError("matrix self-test did not remove intended first witness case")
        first_witness = fixture_value["negative_cases"][0]["case_id"]
        value["cases"] = [
            case for case in value["cases"] if case["case_id"] != first_witness
        ]
        copied_matrix.write_text(
            json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="ascii",
        )
        try:
            validate(design, copied_matrix, fixture, validator, pinned=False)
        except ValueError:
            return
        raise AssertionError("matrix witness-case deletion was accepted")


def replica_check(
    design: Path,
    matrix: Path,
    fixture: Path,
    validator: Path,
) -> None:
    outputs: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        parent = Path(directory)
        for name in ("a", "b"):
            root = parent / name
            root.mkdir()
            copies = {}
            for label, source in (
                ("design", design),
                ("matrix", matrix),
                ("fixture", fixture),
                ("validator", validator),
            ):
                target = root / source.name
                shutil.copyfile(source, target)
                copies[label] = target
            outputs.append(
                validate(
                    copies["design"],
                    copies["matrix"],
                    copies["fixture"],
                    copies["validator"],
                    pinned=False,
                )
            )
    if outputs != ['{"accepted": 6, "rejected": 41}\n'] * 2:
        raise AssertionError("semantic replica outputs differ")


def checker_command(
    design: Path,
    matrix: Path,
    fixture: Path,
    validator: Path,
    expected_checker_sha256: str,
    *,
    isolated: bool,
) -> list[str]:
    command = [sys.executable]
    if isolated:
        command.append("-I")
    command.extend(
        [
            str(Path(__file__).resolve()),
            "--design",
            str(design),
            "--matrix",
            str(matrix),
            "--fixture",
            str(fixture),
            "--validator",
            str(validator),
            "--expected-checker-sha256",
            expected_checker_sha256,
        ]
    )
    return command


def reject_checker_identity_drift(
    design: Path,
    matrix: Path,
    fixture: Path,
    validator: Path,
) -> None:
    result = subprocess.run(
        checker_command(
            design,
            matrix,
            fixture,
            validator,
            "0" * 64,
            isolated=True,
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 or "checker SHA-256 mismatch" not in (
        result.stderr + result.stdout
    ):
        raise AssertionError("checker identity drift was not rejected")


def reject_non_isolated_invocation(
    design: Path,
    matrix: Path,
    fixture: Path,
    validator: Path,
    expected_checker_sha256: str,
) -> None:
    result = subprocess.run(
        checker_command(
            design,
            matrix,
            fixture,
            validator,
            expected_checker_sha256,
            isolated=False,
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 or ISOLATION_DIAGNOSTIC not in (
        result.stderr + result.stdout
    ):
        raise AssertionError("non-isolated checker invocation was not rejected")


def main() -> None:
    if not sys.flags.isolated:
        raise SystemExit(ISOLATION_DIAGNOSTIC)
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--validator", required=True, type=Path)
    parser.add_argument("--expected-checker-sha256", required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    actual_checker_sha256 = sha(Path(__file__))
    if actual_checker_sha256 != args.expected_checker_sha256:
        raise ValueError(
            "checker SHA-256 mismatch: "
            f"expected {args.expected_checker_sha256}, got {actual_checker_sha256}"
        )
    validate(args.design, args.matrix, args.fixture, args.validator, pinned=True)
    replica_check(args.design, args.matrix, args.fixture, args.validator)
    if args.self_test:
        reject_mutated_fixture(args.design, args.matrix, args.fixture, args.validator)
        reject_deleted_boundary_witness(
            args.design, args.matrix, args.fixture, args.validator
        )
        reject_mutated_matrix(args.design, args.matrix, args.fixture, args.validator)
        reject_checker_identity_drift(
            args.design, args.matrix, args.fixture, args.validator
        )
        reject_non_isolated_invocation(
            args.design,
            args.matrix,
            args.fixture,
            args.validator,
            args.expected_checker_sha256,
        )
    print(
        "lifecycle-root signer provenance checked: "
        f"fixture_sha256={sha(args.fixture)} accepted=6 rejected=41 replicas=2"
    )


if __name__ == "__main__":
    main()

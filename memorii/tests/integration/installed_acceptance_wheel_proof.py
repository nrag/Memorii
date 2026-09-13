"""Prepare fixtures and prove the public acceptance command from an installed wheel.

The authoring helper is deliberately test-only.  Every evaluated subprocess is
the wheel venv's console script, runs outside the checkout with ``PYTHONPATH``
removed, and uses its interpreter's fixed platform-data configuration path.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class _Patch:
    def setattr(self, target: object, name: str, value: object) -> None:
        setattr(target, name, value)


def _helpers() -> object:
    unit = Path(__file__).resolve().parents[1] / "unit" / "acceptance"
    sys.path.insert(0, str(unit))
    import test_installed_acceptance_cli as helpers

    return helpers


def _data_path(installed_python: Path) -> Path:
    value = subprocess.check_output(
        [installed_python, "-c", "import sysconfig; print(sysconfig.get_path('data'))"],
        text=True,
        env=_clean_env(),
    ).strip()
    return Path(value) / "etc" / "memorii" / "acceptance" / "runtime-v2.json"


def _prepare(
    *, helpers: object, root: Path, config_path: Path, future: bool = False,
    release_issued_at: datetime | None = None, lifecycle_state: str = "active",
) -> tuple[list[str], Path, Path, Path]:
    args, receipts, authorizations, config = helpers._installed_fixture(  # type: ignore[attr-defined]
        root, _Patch(), checkpoint_offset=timedelta(days=1) if future else timedelta(minutes=-1),
        release_issued_at=release_issued_at, lifecycle_state=lifecycle_state,
        use_frozen_multicell=True,
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.unlink(missing_ok=True)
    shutil.copyfile(config, config_path)
    config_path.chmod(0o600)
    return args, receipts, authorizations, config_path


def _run(command: list[str], cwd: Path, success: bool) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=_clean_env(), text=True, capture_output=True)
    if (result.returncode == 0) != success:
        raise AssertionError(result.stdout + result.stderr)
    return result


def _assert_empty(receipts: Path, authorizations: Path) -> None:
    assert not receipts.exists() or not list(receipts.rglob("*"))
    assert not authorizations.exists() or not list(authorizations.rglob("*"))


def _negative(
    *, helpers: object, root: Path, config_path: Path, command: list[str], mutate: object
) -> None:
    args, receipts, authorizations, _ = _prepare(helpers=helpers, root=root, config_path=config_path)
    mutate(args, config_path)
    _run(command + args, root, False)
    _assert_empty(receipts, authorizations)


def _entry_points_path(installed_python: Path) -> Path:
    command = (
        "from importlib.metadata import distribution; "
        "print(distribution('memorii')._path / 'entry_points.txt')"
    )
    return Path(subprocess.check_output([installed_python, "-c", command], text=True, env=_clean_env()).strip())


def _clean_env() -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    return environment


def _inventory_evaluation_imports(
    *, installed_python: Path, args: list[str], cwd: Path, output: Path
) -> None:
    code = (
        "import json, sys; from pathlib import Path; from acceptance.cli import main; "
        "assert main(json.loads(sys.argv[1])) == 0; root=Path(sys.prefix).resolve(); "
        "origins={name: module.__file__ for name,module in sys.modules.items() "
        "if (name == 'acceptance' or name.startswith('acceptance.') or name == 'memorii' or name.startswith('memorii.')) "
        "and getattr(module, '__file__', None)}; "
        "assert origins and all(Path(path).resolve().is_relative_to(root) for path in origins.values()); "
        "print(json.dumps(origins, sort_keys=True))"
    )
    result = _run([installed_python, "-c", code, json.dumps(args)], cwd, True)
    output.write_text(result.stdout.splitlines()[-1] + "\n", encoding="utf-8")


def _advance_to_successor(
    *, helpers: object, root: Path, config_path: Path, args: list[str], authority_cli: Path
) -> list[str]:
    config = json.loads(config_path.read_bytes())
    authoring = json.loads((root / "fixture-authoring.json").read_bytes())
    authority_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(authoring["authority_private_key"]))
    production_key = Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(authoring["production_revocation_private_key"])
    )
    coordinate = authoring["coordinate"]
    authority_root = Path(config["authority_repository_root"])
    index = json.loads((authority_root / "current.json").read_bytes())
    first_digest = index["digest"]
    first = json.loads((authority_root / "objects" / first_digest).read_bytes())
    now = datetime.now(tz=UTC)
    values = {args[index][2:]: Path(args[index + 1]).read_bytes() for index in range(0, 10, 2)}
    numeric = helpers.build_v2_authority(  # type: ignore[attr-defined]
        policy=values["policy"],
        evidence=values["evidence"],
        key=authority_key,
        coordinate=coordinate,
        authority_snapshot_digest=first["authority_snapshot_digest"],
        now=now,
        issued_at=now - timedelta(seconds=30),
        release_epoch=2,
        release_sequence=2,
        supersedes_release_digest=first["active_release_digest"],
    )
    production_coordinate = "production-revocation-1"
    receipt_digest, revocation_receipt = helpers._artifact(  # type: ignore[attr-defined]
        "ProductionRevocationReceipt",
        production_key,
        production_coordinate,
        schema_version=1,
        purpose="production_revocation_receipt",
        prior_approval_release_digest=first["active_release_digest"],
        withdrawal_requested_at=helpers._time(now - timedelta(seconds=20)),  # type: ignore[attr-defined]
        prior_production_epoch=1,
        advanced_production_epoch=2,
        completed_at=helpers._time(now - timedelta(seconds=10)),  # type: ignore[attr-defined]
    )
    production_checkpoint_digest, production_checkpoint = helpers._artifact(  # type: ignore[attr-defined]
        "ProductionEpochCheckpoint",
        production_key,
        production_coordinate,
        schema_version=1,
        purpose="production_epoch_checkpoint",
        production_authority_snapshot_digest="b" * 64,
        checkpoint_generation=1,
        predecessor_checkpoint_digest=None,
        active_production_epoch=2,
        active_authorization_digests=["c" * 64],
        revocation_receipt_digests=[receipt_digest],
        observed_at=helpers._time(now - timedelta(seconds=5)),  # type: ignore[attr-defined]
    )
    reader_root = Path(config["production_revocation_reader"]["reader_root"])
    (reader_root / "objects").mkdir(parents=True, exist_ok=True)
    (reader_root / "current").mkdir()
    for digest, raw in (
        (receipt_digest, revocation_receipt),
        (production_checkpoint_digest, production_checkpoint),
    ):
        (reader_root / "objects" / digest).write_bytes(raw)
    (reader_root / "current" / f"{first['active_release_digest']}.json").write_bytes(
        helpers._json({  # type: ignore[attr-defined]
            "prior_approval_release_digest": first["active_release_digest"],
            "receipt_digest": receipt_digest,
            "checkpoint_digest": production_checkpoint_digest,
        })
    )
    prior_checkpoint = json.loads(
        (authority_root / "objects" / first["current_checkpoint_digest"]).read_bytes()
    )
    prior_checkpoint.pop("checkpoint_digest")
    prior_checkpoint.pop("signature")
    prior_checkpoint.update({
        "checkpoint_generation": 2,
        "predecessor_checkpoint_digest": first["current_checkpoint_digest"],
        "release_history_head_digest": numeric.release_digest,
        "release_history_head_sequence": 2,
        "active_release_digest": numeric.release_digest,
        "active_epoch": 2,
        "active_sequence": 2,
        "production_revocation_evidence": [[receipt_digest, production_checkpoint_digest]],
        "observed_at": helpers._time(now - timedelta(seconds=1)),  # type: ignore[attr-defined]
    })
    checkpoint_digest, checkpoint = helpers._artifact(  # type: ignore[attr-defined]
        "AcceptanceCurrentCheckpoint", authority_key, coordinate, **prior_checkpoint
    )
    successor_commit = dict(first)
    successor_commit.pop("commit_digest")
    successor_commit.update({
        "transaction_sequence": 2,
        "predecessor_commit_digest": first_digest,
        "release_history_head_digest": numeric.release_digest,
        "release_history_head_sequence": 2,
        "active_release_digest": numeric.release_digest,
        "active_release_epoch": 2,
        "active_release_sequence": 2,
        "current_checkpoint_digest": checkpoint_digest,
        "approval_release_digest": numeric.release_digest,
        "production_revocation_evidence": [[receipt_digest, production_checkpoint_digest]],
    })
    commit_digest, commit = helpers._artifact(  # type: ignore[attr-defined]
        "AcceptanceAuthorityCommit", None, None, **successor_commit
    )
    publication = root / "successor-publication"
    publication.mkdir()
    objects = {
        numeric.release_digest: numeric.release,
        receipt_digest: revocation_receipt,
        production_checkpoint_digest: production_checkpoint,
        checkpoint_digest: checkpoint,
    }
    command = [
        str(authority_cli),
        "--commit", str(publication / "commit.json"),
        "--expected-commit-digest", first_digest,
        "--expected-key-head", first["key_history_head_digest"],
        "--expected-status-generation", "1",
    ]
    (publication / "commit.json").write_bytes(commit)
    for digest, raw in objects.items():
        path = publication / digest
        path.write_bytes(raw)
        command.extend(("--object", f"{digest}={path}"))
    result = _run(command, root, True)
    assert result.stdout.strip() == commit_digest
    _, _, _, limits = helpers.inputs("0.00")  # type: ignore[attr-defined]
    certificate = helpers.candidate(  # type: ignore[attr-defined]
        numeric.policy, values["evidence"], numeric.binding, limits
    )
    candidates = {
        "release": numeric.release,
        "baseline": numeric.baseline,
        "policy": numeric.policy,
        "evidence": values["evidence"],
        "certificate": certificate,
    }
    successor_args = []
    for name, raw in candidates.items():
        path = root / f"successor-{name}.bin"
        path.write_bytes(raw)
        successor_args.extend((f"--{name}", str(path)))
    return successor_args + ["--deployment-manifest-digest", "7" * 64]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installed-python", type=Path, required=True)
    parser.add_argument("--installed-cli", type=Path, required=True)
    parser.add_argument("--installed-authority-cli", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parsed = parser.parse_args()
    # Resolving the venv interpreter follows its symlink to the base executable
    # and silently loses the venv's sys.prefix. Keep the invocation path intact.
    installed_python = parsed.installed_python.absolute()
    cli = parsed.installed_cli.absolute()
    authority_cli = parsed.installed_authority_cli.absolute()
    work = parsed.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    assert not Path.cwd().resolve().is_relative_to(Path(__file__).resolve().parents[3])
    config_path = _data_path(installed_python)
    helpers = _helpers()
    _run(
        [
            installed_python,
            "-c",
            "from pathlib import Path; import acceptance, memorii; "
            "root=Path(sys_prefix := __import__('sys').prefix).resolve(); "
            "assert Path(acceptance.__file__).resolve().is_relative_to(root); "
            "assert Path(memorii.__file__).resolve().is_relative_to(root)",
        ],
        work,
        True,
    )
    frozen_fixture = (
        Path(__file__).resolve().parents[3]
        / "docs/design/semantic_ingestion/acceptance_authority_vectors/multicell-v2.json"
    )
    frozen_proof = Path(__file__).with_name("installed_frozen_numeric_vector_proof.py")
    _run([installed_python, str(frozen_proof), str(frozen_fixture)], work, True)
    args, receipts, authorizations, _ = _prepare(helpers=helpers, root=work / "success", config_path=config_path)
    result = _run([cli] + args, work, True)
    receipt_digest = result.stdout.strip()
    receipt = json.loads((receipts / receipt_digest).read_bytes())
    assert receipt["receipt_digest"] == receipt_digest
    assert (receipts / "attempts").is_dir() and len(list((receipts / "attempts").iterdir())) == 1
    assert (authorizations / receipt["deployment_authorization_digest"]).is_file()
    # A fresh process reconciles a durable authorization/attempt when the
    # receipt acknowledgement is lost after production publication.
    (receipts / receipt_digest).unlink()
    retry = _run([cli] + args, work, True)
    assert retry.stdout.strip() == receipt_digest
    assert len(list(authorizations.iterdir())) == 1
    assert len(list((receipts / "attempts").iterdir())) == 1

    successor_args = _advance_to_successor(
        helpers=helpers,
        root=work / "success",
        config_path=config_path,
        args=args,
        authority_cli=authority_cli,
    )
    successor_result = _run([cli] + successor_args, work, True)
    successor_receipt = json.loads(
        (receipts / successor_result.stdout.strip()).read_bytes()
    )
    successor_release = json.loads(Path(successor_args[1]).read_bytes())
    successor_authorization = json.loads(
        (authorizations / successor_receipt["deployment_authorization_digest"]).read_bytes()
    )
    assert (
        successor_authorization["verified_capability_baseline_approval_release_digest"]
        == successor_release["release_digest"]
    )
    config = json.loads(config_path.read_bytes())
    current = json.loads((Path(config["authority_repository_root"]) / "current.json").read_bytes())
    assert successor_receipt["authority_commit_digest"] == current["digest"]
    _run([cli] + args, work, False)
    _inventory_evaluation_imports(
        installed_python=installed_python,
        args=successor_args,
        cwd=work,
        output=work / "import-origins.json",
    )
    config = json.loads(config_path.read_bytes())
    reader_root = Path(config["production_revocation_reader"]["reader_root"])
    prior_release = successor_release["supersedes_release_digest"]
    current_mapping = reader_root / "current" / f"{prior_release}.json"
    current_bytes = current_mapping.read_bytes()
    receipt_count = len(list(receipts.iterdir()))
    authorization_count = len(list(authorizations.iterdir()))
    current_mapping.write_bytes(b"{}")
    _run([cli] + successor_args, work, False)
    assert len(list(receipts.iterdir())) == receipt_count
    assert len(list(authorizations.iterdir())) == authorization_count
    current_mapping.write_bytes(current_bytes)

    conflict_args, conflict_receipts, conflict_authorizations, _ = _prepare(
        helpers=helpers,
        root=work / "publisher-conflict",
        config_path=config_path,
    )
    conflict_result = _run([cli] + conflict_args, work, True)
    conflict_receipt = json.loads(
        (conflict_receipts / conflict_result.stdout.strip()).read_bytes()
    )
    conflict_authorization = (
        conflict_authorizations / conflict_receipt["deployment_authorization_digest"]
    )
    conflict_authorization.write_bytes(b"{}")
    (conflict_receipts / conflict_result.stdout.strip()).unlink()
    _run([cli] + conflict_args, work, False)
    assert not (conflict_receipts / conflict_result.stdout.strip()).exists()
    assert conflict_authorization.read_bytes() == b"{}"

    def bad_signature(args: list[str], _: Path) -> None:
        path = Path(args[1])
        value = json.loads(path.read_bytes())
        value["signature"] = "0" * 128
        path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii"))

    def missing_object(args: list[str], _: Path) -> None:
        release = json.loads(Path(args[1]).read_bytes())["release_digest"]
        config = json.loads(config_path.read_bytes())
        (Path(config["authority_repository_root"]) / "objects" / release).unlink()

    def insecure_config(_: list[str], path: Path) -> None:
        path.chmod(0o666)

    def symlink_config(_: list[str], path: Path) -> None:
        raw = path.read_bytes()
        target = path.with_name("real-runtime-v2.json")
        target.write_bytes(raw)
        path.unlink()
        path.symlink_to(target)

    def insecure_root(_: list[str], _config: Path) -> None:
        config = json.loads(config_path.read_bytes())
        Path(config["authority_repository_root"]).chmod(0o722)

    def wrong_numeric_signer(_: list[str], path: Path) -> None:
        config = json.loads(path.read_bytes())
        config["numeric_authority"]["signing_key_id"] = "unknown-key"
        path.write_bytes(helpers._json(config))  # type: ignore[attr-defined]

    def wrong_numeric_policy(_: list[str], path: Path) -> None:
        config = json.loads(path.read_bytes())
        config["numeric_authority"]["trust_policy_digest"] = "8" * 64
        path.write_bytes(helpers._json(config))  # type: ignore[attr-defined]

    def candidate_schema(target: str, marker: str | None) -> object:
        def mutate(args: list[str], _: Path) -> None:
            values = {args[index][2:]: Path(args[index + 1]) for index in range(0, 10, 2)}
            path = values[target]
            value = json.loads(path.read_bytes())
            if marker is None:
                value.pop("schema")
            else:
                value["schema"] = marker
            path.write_bytes(helpers._json(value))  # type: ignore[attr-defined]

        return mutate

    def mixed_signed_manifest(args: list[str], path: Path) -> None:
        root = Path(args[1]).parent
        authoring = json.loads((root / "fixture-authoring.json").read_bytes())
        key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(authoring["authority_private_key"]))
        config = json.loads(path.read_bytes())
        coverage = json.loads(base64.b64decode(config["numeric_authority"]["coverage"]))
        coverage.pop("manifest_digest")
        coverage.pop("signature")
        coverage["trust_policy_digest"] = "8" * 64
        _, raw = helpers._artifact(  # type: ignore[attr-defined]
            "CapabilityCoverageManifest", key, authoring["coordinate"], **coverage
        )
        config["numeric_authority"]["coverage"] = base64.b64encode(raw).decode("ascii")
        path.write_bytes(helpers._json(config))  # type: ignore[attr-defined]

    for name, mutation in (
        ("bad-signature", bad_signature),
        ("missing-authority", missing_object),
        ("insecure-config", insecure_config),
        ("symlink-config", symlink_config),
        ("insecure-root", insecure_root),
        ("wrong-numeric-signer", wrong_numeric_signer),
        ("wrong-numeric-policy", wrong_numeric_policy),
        ("mixed-signed-manifest", mixed_signed_manifest),
        ("unmarked-policy", candidate_schema("policy", None)),
        ("v1-policy", candidate_schema("policy", "statistical_acceptance_policy.v1")),
        ("unmarked-evidence", candidate_schema("evidence", None)),
        ("v1-evidence", candidate_schema("evidence", "statistical_acceptance_evidence.v1")),
    ):
        _negative(helpers=helpers, root=work / name, config_path=config_path, command=[cli], mutate=mutation)

    args, receipts, authorizations, _ = _prepare(helpers=helpers, root=work / "future-checkpoint", config_path=config_path, future=True)
    _run([cli] + args, work, False)
    _assert_empty(receipts, authorizations)

    for state in ("retired", "revoked", "compromised"):
        args, receipts, authorizations, _ = _prepare(
            helpers=helpers, root=work / f"release-{state}", config_path=config_path,
            lifecycle_state=state,
        )
        _run([cli] + args, work, False)
        _assert_empty(receipts, authorizations)
    args, receipts, authorizations, _ = _prepare(
        helpers=helpers, root=work / "release-expired", config_path=config_path,
        release_issued_at=datetime.now(tz=UTC) - timedelta(days=3),
    )
    _run([cli] + args, work, False)
    _assert_empty(receipts, authorizations)

    entry_points = _entry_points_path(installed_python)
    original_entry_points = entry_points.read_text(encoding="utf-8")
    for group in (
        "memorii.acceptance_evaluator_runtime",
        "memorii.acceptance_deployment_publisher",
        "memorii.acceptance_production_revocation_reader",
    ):
        args, receipts, authorizations, _ = _prepare(
            helpers=helpers, root=work / f"missing-{group}", config_path=config_path
        )
        before, section = original_entry_points.split(f"[{group}]\n", 1)
        body, after = (section.split("\n[", 1) + [""])[:2]
        entry_points.write_text(before + ("[" + after if after else ""), encoding="utf-8")
        try:
            assert subprocess.check_output(
                [installed_python, "-c", f"from importlib.metadata import entry_points; print(len(tuple(entry_points(group={group!r}))))"],
                text=True,
                env=_clean_env(),
            ).strip() == "0"
            _run([cli] + args, work, False)
            _assert_empty(receipts, authorizations)
        finally:
            entry_points.write_text(original_entry_points, encoding="utf-8")
    args, receipts, authorizations, _ = _prepare(
        helpers=helpers, root=work / "duplicate-evaluator", config_path=config_path
    )
    entry_points.write_text(
        original_entry_points.replace(
            "[memorii.acceptance_evaluator_runtime]\ninstalled = acceptance.host_runtime:InstalledAcceptanceRuntime",
            "[memorii.acceptance_evaluator_runtime]\ninstalled = acceptance.host_runtime:InstalledAcceptanceRuntime\nsecond = acceptance.host_runtime:InstalledAcceptanceRuntime",
        ),
        encoding="utf-8",
    )
    try:
        _run([cli] + args, work, False)
        _assert_empty(receipts, authorizations)
    finally:
        entry_points.write_text(original_entry_points, encoding="utf-8")
    print(json.dumps({"receipt_digest": receipt_digest, "negatives": 23}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

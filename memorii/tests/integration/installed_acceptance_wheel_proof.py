"""Prepare fixtures and prove the public acceptance command from an installed wheel.

The authoring helper is deliberately test-only.  Every evaluated subprocess is
the wheel venv's console script, runs outside the checkout with ``PYTHONPATH``
removed, and uses its interpreter's fixed platform-data configuration path.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installed-python", type=Path, required=True)
    parser.add_argument("--installed-cli", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parsed = parser.parse_args()
    # Resolving the venv interpreter follows its symlink to the base executable
    # and silently loses the venv's sys.prefix. Keep the invocation path intact.
    installed_python = parsed.installed_python.absolute()
    cli = parsed.installed_cli.absolute()
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
    _inventory_evaluation_imports(
        installed_python=installed_python,
        args=args,
        cwd=work,
        output=work / "import-origins.json",
    )

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

    for name, mutation in (
        ("bad-signature", bad_signature),
        ("missing-authority", missing_object),
        ("insecure-config", insecure_config),
        ("symlink-config", symlink_config),
        ("insecure-root", insecure_root),
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
    print(json.dumps({"receipt_digest": receipt_digest, "negatives": 14}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

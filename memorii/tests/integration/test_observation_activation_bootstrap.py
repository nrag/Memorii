"""Fresh-process bootstrap mechanics; candidate-wheel certification is separate."""
from __future__ import annotations

import base64
import csv
import io
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

_BOOTSTRAP = Path(__file__).resolve().parents[3] / "tools/observation_activation_bootstrap.py"


def _launch(tmp_path: Path, mutation: str) -> subprocess.CompletedProcess[str]:
    site, scripts, cache = (tmp_path / name for name in ("site", "scripts", "cache"))
    for path in (site, scripts, cache):
        path.mkdir()
    distributions, installed = [], []
    for name, payload, roots in (
        ("dependency", {"dep.py": b"VALUE = 7\n", "ns/child.py": b"VALUE = 9\n", "../scripts/helper": b"do not execute\n"}, ("dep.py", "ns")),
        ("memorii", {"memorii/__init__.py": b"import dep\nfrom ns import child\nVALUE = dep.VALUE + child.VALUE\n", "memorii/empty.py": b""}, ("memorii",)),
    ):
        metadata = f"{name}-1.0.dist-info"
        payload[f"{metadata}/METADATA"] = f"Name: {name}\nVersion: 1.0\n".encode()
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        for path, raw in sorted(payload.items()):
            target = site / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            digest = sha256(raw).hexdigest()
            writer.writerow((path, "sha256=" + base64.urlsafe_b64encode(bytes.fromhex(digest)).decode().rstrip("="), str(len(raw))))
            installed.append((name, "scripts/helper" if path.startswith("../scripts/") else "site/" + path, digest, len(raw)))
        record_path = f"{metadata}/RECORD"
        writer.writerow((record_path, "", ""))
        raw = buffer.getvalue().encode()
        (site / record_path).write_bytes(raw)
        digest = sha256(raw).hexdigest()
        installed.append((name, "site/" + record_path, digest, len(raw)))
        distributions.append((name, "1.0", "a" * 64, digest, roots))
    extra = ""
    changed_paths = {
        "changed": site / "dep.py", "extra": site / "unrecorded.py", "script": scripts / "helper",
        "record": site / "memorii-1.0.dist-info/RECORD", "metadata": site / "memorii-1.0.dist-info/METADATA",
        "package_bytecode": site / "memorii/stale.pyc",
    }
    if mutation in changed_paths:
        changed_paths[mutation].write_bytes(b"changed")
    elif mutation == "missing":
        (site / "memorii/empty.py").unlink()
    elif mutation == "symlink":
        (site / "memorii/empty.py").unlink()
        (site / "memorii/empty.py").symlink_to(site / "dep.py")
    elif mutation == "cached_bytecode":
        (cache / "memorii").mkdir()
        (cache / "memorii/stale.pyc").write_bytes(b"stale")
    elif mutation == "preloaded":
        extra = "sys.modules['memorii'] = types.ModuleType('memorii')"
    elif mutation == "preloaded_dependency":
        extra = "sys.modules['dep'] = types.ModuleType('dep')"
    elif mutation == "shadow":
        shadow = tmp_path / "shadow"
        (shadow / "memorii").mkdir(parents=True)
        (shadow / "memorii/__init__.py").write_bytes(b"raise AssertionError('shadow executed')\n")
        extra = f"sys.path.insert(0, {str(shadow)!r})"
    elif mutation == "prefix":
        extra = "sys.pycache_prefix = None"
    runner = tmp_path / "runner.py"
    runner.write_text(f'''
import importlib.util, pathlib, platform, sys, sysconfig, types
spec = importlib.util.spec_from_file_location("trusted_bootstrap", {_BOOTSTRAP.as_posix()!r})
bootstrap = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bootstrap
spec.loader.exec_module(bootstrap)
site = pathlib.Path({str(site)!r})
sys.path.insert(0, str(site))
configuration = bootstrap.DeploymentConfiguration(
    site, pathlib.Path({str(scripts)!r}), platform.python_implementation(),
    platform.python_version(), sysconfig.get_platform(), "wheel-no-compile-v1",
    "fresh-private-prefix-v1", "selected-distribution-root-v1",
    tuple(bootstrap.DistributionRow(*row) for row in {distributions!r}),
    tuple(bootstrap.InstalledFileRow(*row) for row in {sorted(installed)!r}),
)
{extra}
try:
    facts = bootstrap.verify_deployment(configuration, private_pycache_prefix=pathlib.Path({str(cache)!r}))
    guard = bootstrap.install_selected_distribution_origin_guard(configuration)
except bootstrap.BootstrapVerificationError as exc:
    print("REJECT", str(exc))
    raise SystemExit(3)
assert facts.configuration_identity_digest == bootstrap.deployment_configuration_identity(configuration)
import memorii
assert memorii.VALUE == 16
pathlib.Path({str(tmp_path / 'imported')!r}).write_text("imported")
print("VERIFIED")
''')
    return subprocess.run(
        [sys.executable, "-I", "-X", f"pycache_prefix={cache}", str(runner)],
        capture_output=True, text=True, timeout=30, check=False,
    )


def test_fresh_bootstrap_accepts_pinned_scripts_empty_files_and_namespace_imports(tmp_path: Path) -> None:
    result = _launch(tmp_path, "valid")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "VERIFIED"
    assert (tmp_path / "imported").read_text() == "imported"


@pytest.mark.parametrize("mutation", [
    "changed", "extra", "missing", "script", "record", "metadata", "symlink",
    "package_bytecode", "cached_bytecode", "preloaded", "preloaded_dependency", "shadow", "prefix",
])
def test_fresh_bootstrap_rejects_before_import(tmp_path: Path, mutation: str) -> None:
    result = _launch(tmp_path, mutation)
    assert result.returncode == 3, result.stdout + result.stderr
    assert result.stdout.startswith("REJECT bootstrap.")
    assert not (tmp_path / "imported").exists()

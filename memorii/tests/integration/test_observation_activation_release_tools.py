"""Operator preparation failures must stop before installation or host execution."""
from __future__ import annotations

import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[3] / "tools"


@pytest.mark.parametrize("failure", ["wheel_pin", "existing_destination"])
def test_prepare_rejects_before_creating_an_environment(tmp_path: Path, failure: str) -> None:
    wheel = tmp_path / "memorii-1.0-py3-none-any.whl"
    wheel.write_bytes(b"not a wheel")
    destination = tmp_path / "prepared"
    if failure == "existing_destination":
        destination.mkdir()
        (destination / "sentinel").write_text("preserve")
    result = subprocess.run([
        sys.executable, str(_TOOLS / "observation_activation_prepare.py"),
        "--destination", str(destination), "--wheel", str(wheel), "0" * 64, "memorii",
    ], capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert not (destination / "environment").exists()
    assert not (destination / "deployment_configuration.py").exists()
    if failure == "wheel_pin":
        assert "wheel_digest_mismatch" in result.stderr
    else:
        assert (destination / "sentinel").read_text() == "preserve"


@pytest.mark.parametrize("failure", ["pin", "isolation", "symlink"])
def test_launcher_rejects_before_executing_unverified_code(tmp_path: Path, failure: str) -> None:
    sentinel = tmp_path / "executed"
    module = tmp_path / "bootstrap.py"
    module.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n")
    digest = sha256(module.read_bytes()).hexdigest()
    if failure == "symlink":
        link = tmp_path / "link.py"
        link.symlink_to(module)
        module = link
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o700)
    command = [sys.executable]
    if failure != "isolation":
        command.extend(("-I", "-S", "-X", f"pycache_prefix={cache}"))
    command.append(str(_TOOLS / "observation_activation_launch.py"))
    for name in ("bootstrap", "configuration", "host"):
        command.extend((f"--{name}", str(module), f"--{name}-sha256", "0" * 64 if failure == "pin" else digest))
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert not sentinel.exists()
    if failure == "pin":
        assert "protected_module_digest_mismatch" in result.stderr
    elif failure == "isolation":
        assert "requires -I -S" in result.stderr

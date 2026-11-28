"""Check the separate pinned host artifact and wheel digest contract."""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from pathlib import Path

import pytest
from tools.build_native_host_assets import build_assets

_ROOT = Path(__file__).resolve().parents[4]


def test_host_assets_bind_exact_members_and_are_reproducible(tmp_path: Path) -> None:
    wheel = tmp_path / "memorii-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"candidate wheel fixture")
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest = build_assets(_ROOT, wheel=wheel, output=first, revision="1" * 40)
    assert build_assets(_ROOT, wheel=wheel, output=second, revision="1" * 40) == manifest
    assert manifest.wheel.sha256 == hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert {asset.host for asset in manifest.hosts} == {"pi", "openclaw"}
    for asset in manifest.hosts:
        payload = (first / asset.archive.filename).read_bytes()
        assert payload == (second / asset.archive.filename).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == asset.archive.sha256
        with tarfile.open(first / asset.archive.filename, mode="r:gz") as bundle:
            assert set(bundle.getnames()) == {member.filename for member in asset.members}
            for expected in asset.members:
                member = bundle.getmember(expected.filename)
                assert member.isfile() and member.mtime == 0
                source = bundle.extractfile(member)
                assert source is not None
                with source:
                    assert hashlib.sha256(source.read()).hexdigest() == expected.sha256


def test_host_lock_drift_refuses_release_manifest(tmp_path: Path) -> None:
    package_path = Path("memorii/memorii/integrations/pi/extension")
    source = tmp_path / package_path
    shutil.copytree(_ROOT / package_path, source)
    lock_path = source / "package-lock.json"
    lock = json.loads(lock_path.read_bytes())
    lock["packages"]["node_modules/@earendil-works/pi-coding-agent"]["version"] = "1.0.0"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"candidate wheel fixture")
    output = tmp_path / "assets"
    with pytest.raises(ValueError, match="same exact host pin"):
        build_assets(tmp_path, wheel=wheel, output=output, revision="1" * 40)
    assert not (output / "native-host-assets.json").exists()

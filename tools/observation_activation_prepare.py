"""Prepare a fresh offline wheel deployment and protected Python configuration.

This operator tool never runs during runtime bootstrap. Wheel roots and SHA pins
are trusted release inputs, not fields read from a runtime request or environment.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from hashlib import sha256
from pathlib import Path

from observation_activation_bootstrap import (
    BootstrapVerificationError,
    DeploymentConfiguration,
    DistributionRow,
    InstalledFileRow,
    _hash_file,
    _open_anchor,
    _parse_record,
    _read_exact,
    _record_locator,
    _safe_relative,
    _walk_regular,
    _verify_anchor_closure,
    _verify_distribution_records,
    _verify_distribution_roots,
    deployment_configuration_identity,
)


@dataclass(frozen=True)
class WheelInput:
    path: Path
    sha256: str
    top_level_roots: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path) or not self.path.is_absolute() or self.path.suffix != ".whl":
            raise ValueError("wheel_path_invalid")
        if re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise ValueError("wheel_pin_invalid")
        if type(self.top_level_roots) is not tuple or not self.top_level_roots:
            raise ValueError("wheel_roots_invalid")
        for root in self.top_level_roots:
            _safe_relative(root)
        if tuple(sorted(set(self.top_level_roots))) != self.top_level_roots:
            raise ValueError("wheel_roots_order_invalid")


@dataclass(frozen=True)
class PreparedDeployment:
    configuration: DeploymentConfiguration
    configuration_module: Path
    configuration_module_sha256: str
    bootstrap_module: Path
    bootstrap_module_sha256: str


def _copy_verified_wheel(wheel: WheelInput, target: Path) -> None:
    parent = _open_anchor(wheel.path.parent)
    try:
        descriptor = os.open(wheel.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024**3:
                raise ValueError("wheel_file_invalid")
            digest = sha256()
            remaining = info.st_size
            with target.open("xb") as output:
                while remaining:
                    chunk = os.read(descriptor, min(1024**2, remaining))
                    if not chunk:
                        raise ValueError("wheel_changed_during_copy")
                    output.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                if os.read(descriptor, 1) or digest.hexdigest() != wheel.sha256:
                    raise ValueError("wheel_digest_mismatch")
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)


def _wheel_identity(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        rows = archive.infolist()
        if len(rows) > 250_000 or sum(row.file_size for row in rows) > 64 * 1024**3:
            raise ValueError("wheel_inventory_limit")
        paths: set[str] = set()
        metadata = []
        for row in rows:
            value = row.filename.rstrip("/") if row.is_dir() else row.filename
            _safe_relative(value)
            if value in paths or row.file_size > 2 * 1024**3:
                raise ValueError("wheel_member_invalid")
            paths.add(value)
            mode = stat.S_IFMT(row.external_attr >> 16)
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("wheel_special_file")
            if value.endswith(".pyc") or "__pycache__" in value.split("/"):
                raise ValueError("wheel_bytecode_not_permitted")
            if value.split("/")[0].endswith(".data") and not (row.is_dir() and "/" not in value) and value.split("/")[1:2] not in (["purelib"], ["platlib"], ["scripts"]):
                raise ValueError("wheel_destination_outside_anchors")
            if value.endswith(".dist-info/METADATA") and len(value.split("/")) == 2:
                if row.file_size > 4 * 1024**2:
                    raise ValueError("wheel_metadata_limit")
                metadata.append(archive.read(row))
        if len(metadata) != 1:
            raise ValueError("wheel_metadata_ambiguous")
        parsed = BytesParser().parsebytes(metadata[0], headersonly=True)
        names, versions = parsed.get_all("Name"), parsed.get_all("Version")
        if names is None or versions is None or len(names) != 1 or len(versions) != 1:
            raise ValueError("wheel_metadata_invalid")
        name = re.sub(r"[-_.]+", "-", names[0].lower())
        DistributionRow(name, versions[0], "0" * 64, "0" * 64, ("validation",))
        return name, versions[0]


def _configuration_source(configuration: DeploymentConfiguration) -> bytes:
    lines = [
        '"""Protected deployment inputs: review and pin this file before use."""',
        "from pathlib import Path",
        "from observation_activation_bootstrap import DeploymentConfiguration, DistributionRow, InstalledFileRow",
        "configuration = DeploymentConfiguration(",
        f"    installation_root=Path({str(configuration.installation_root)!r}),",
        f"    scripts_root=Path({str(configuration.scripts_root)!r}),",
    ]
    for field in ("python_implementation", "python_version", "platform_tag", "install_policy", "cache_policy", "origin_policy"):
        lines.append(f"    {field}={getattr(configuration, field)!r},")
    lines.append("    distributions=(")
    for row in configuration.distributions:
        lines.append(f"        DistributionRow({row.normalized_name!r}, {row.version!r}, {row.wheel_sha256!r}, {row.record_sha256!r}, {row.top_level_roots!r}),")
    lines.append("    ),\n    installed_files=(")
    for row in configuration.installed_files:
        lines.append(f"        InstalledFileRow({row.normalized_distribution!r}, {row.installed_relative_path!r}, {row.sha256!r}, {row.size!r}),")
    lines.append("    ),\n)\n")
    return "\n".join(lines).encode("utf-8")


def prepare_deployment(wheels: tuple[WheelInput, ...], *, destination: Path) -> PreparedDeployment:
    """Verify all wheel bytes before installing into a new, isolated prefix."""
    if type(wheels) is not tuple or not wheels or len(wheels) > 512 or any(type(row) is not WheelInput for row in wheels):
        raise ValueError("wheel_inputs_invalid")
    if not destination.is_absolute() or ".." in destination.parts:
        raise ValueError("deployment_destination_invalid")
    parent = _open_anchor(destination.parent)
    os.close(parent)
    destination.mkdir(mode=0o700)
    wheel_dir = destination / "wheels"
    wheel_dir.mkdir()
    copied = []
    identities = {}
    for wheel in wheels:
        target = wheel_dir / wheel.path.name
        _copy_verified_wheel(wheel, target)
        identity = _wheel_identity(target)
        if identity[0] in identities:
            raise ValueError("wheel_distribution_duplicate")
        identities[identity[0]] = (identity[1], wheel)
        copied.append(target)
    if "memorii" not in identities:
        raise ValueError("memorii_wheel_required")
    prefix = destination / "environment"
    subprocess.run([
        sys.executable, "-I", "-m", "pip", "install", "--no-deps", "--no-compile", "--no-index",
        "--ignore-installed", "--no-warn-script-location", "--prefix", str(prefix), *map(str, copied),
    ], check=True, timeout=300)
    paths = sysconfig.get_paths(scheme="posix_prefix", vars={"base": str(prefix), "platbase": str(prefix)})
    site, scripts = Path(paths["purelib"]), Path(paths["scripts"])
    scripts.mkdir(parents=True, exist_ok=True)
    site_fd = _open_anchor(site)
    try:
        script_fd = _open_anchor(scripts)
    except (OSError, ValueError, BootstrapVerificationError):
        os.close(site_fd)
        raise
    try:
        site_files = dict(_walk_regular(site_fd))
        distributions = []
        for name, (version, wheel) in sorted(identities.items()):
            matches = []
            for path in site_files:
                if path.endswith(".dist-info/METADATA") and len(path.split("/")) == 2:
                    parsed = BytesParser().parsebytes(_read_exact(site_fd, path, 4 * 1024**2), headersonly=True)
                    actual = re.sub(r"[-_.]+", "-", str(parsed.get("Name", "")).lower())
                    if actual == name:
                        matches.append(path.rsplit("/", 1)[0] + "/RECORD")
            if len(matches) != 1:
                raise ValueError("installed_distribution_ambiguous")
            record = _read_exact(site_fd, matches[0], 64 * 1024**2)
            distributions.append((DistributionRow(name, version, wheel.sha256, sha256(record).hexdigest(), wheel.top_level_roots), matches[0], record))
        import platform
        provisional = DeploymentConfiguration(site, scripts, platform.python_implementation(), platform.python_version(),
            sysconfig.get_platform(), "wheel-no-compile-v1", "fresh-private-prefix-v1", "selected-distribution-root-v1",
            tuple(row for row, _, _ in distributions), ())
        installed = []
        claimed = set()
        for distribution, path, raw in distributions:
            for record_path, expected_digest, expected_size in _parse_record(raw, path):
                locator = _record_locator(provisional, path, record_path)
                if locator in claimed:
                    raise ValueError("installed_file_duplicate_owner")
                claimed.add(locator)
                root_fd = site_fd if locator.startswith("site/") else script_fd
                relative = locator.split("/", 1)[1]
                if expected_digest is None:
                    if locator != "site/" + path:
                        raise ValueError("unhashed_installed_file")
                    size, digest = len(raw), sha256(raw).hexdigest()
                else:
                    assert expected_size is not None
                    size, digest = expected_size, _hash_file(root_fd, relative, expected_size)
                    if digest != expected_digest:
                        raise ValueError("installed_record_digest_mismatch")
                installed.append(InstalledFileRow(distribution.normalized_name, locator, digest, size))
        if {"site/" + path for path in site_files} != {path for path in claimed if path.startswith("site/")}:
            raise ValueError("installed_site_closure_mismatch")
        configuration = DeploymentConfiguration(site, scripts, provisional.python_implementation, provisional.python_version,
            provisional.platform_tag, provisional.install_policy, provisional.cache_policy, provisional.origin_policy,
            provisional.distributions, tuple(sorted(installed, key=lambda row: (row.normalized_distribution, row.installed_relative_path))))
        claims = _verify_distribution_records(configuration, site_fd, script_fd)
        _verify_anchor_closure(configuration, site_fd, script_fd, claims)
        _verify_distribution_roots(configuration, site_fd)
    finally:
        os.close(script_fd)
        os.close(site_fd)
    module = destination / "deployment_configuration.py"
    with module.open("xb") as output:
        output.write(_configuration_source(configuration))
    bootstrap = destination / "observation_activation_bootstrap.py"
    shutil.copyfile(Path(__file__).with_name(bootstrap.name), bootstrap)
    return PreparedDeployment(configuration, module, sha256(module.read_bytes()).hexdigest(), bootstrap, sha256(bootstrap.read_bytes()).hexdigest())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--wheel", nargs=3, action="append", required=True, metavar=("PATH", "SHA256", "ROOTS"), help="repeat for every pinned wheel; comma-separated explicit import roots")
    args = parser.parse_args()
    wheels = tuple(WheelInput(Path(path), digest, tuple(roots.split(","))) for path, digest, roots in args.wheel)
    prepared = prepare_deployment(wheels, destination=args.destination)
    print(f"configuration_sha256={prepared.configuration_module_sha256}")
    print(f"bootstrap_sha256={prepared.bootstrap_module_sha256}")
    print(f"deployment_identity={deployment_configuration_identity(prepared.configuration)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

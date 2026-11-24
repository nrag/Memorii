"""Check and record the named local runner envelope."""

from __future__ import annotations

import os
import platform
import plistlib
import shutil
import sqlite3
import subprocess
from importlib.metadata import version
from pathlib import Path

from tests.support.reference_capacity_fixture import ReferenceFixtureError

_MINIMUM_MEMORY_BYTES = 16 * 1024**3


def _output(*command: str) -> str:
    try:
        return subprocess.check_output(command, stderr=subprocess.DEVNULL, text=True, timeout=10).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReferenceFixtureError(f"cannot attest runner hardware with {command[0]}") from exc


def _linux_volume(path: Path) -> tuple[str, bool]:
    source, filesystem = _output("findmnt", "-n", "-o", "SOURCE,FSTYPE", "--target", str(path)).split()
    # Device-mapper installations require checking both the mapped device
    # and every underlying physical device.
    device = source.split("[", 1)[0]
    flags = _output("lsblk", "--noheadings", "--inverse", "--output", "ROTA", device).split()
    return filesystem, bool(flags) and set(flags) == {"0"}


def _mac_volume(path: Path) -> tuple[str, bool]:
    device = _output("df", "-P", str(path)).splitlines()[-1].split()[0]
    volume = plistlib.loads(_output("diskutil", "info", "-plist", device).encode())
    solid_state = volume.get("SolidState")
    parent = volume.get("ParentWholeDisk")
    if solid_state is None and isinstance(parent, str):
        disk = plistlib.loads(_output("diskutil", "info", "-plist", parent).encode())
        solid_state = disk.get("SolidState")
    return str(volume.get("FilesystemType") or ""), solid_state is True


def verify_profile(profile: str, path: Path, *, dedicated_idle: bool) -> dict[str, object]:
    required_system = {"linux": "Linux", "macos": "Darwin"}[profile]
    actual_system = platform.system()
    if actual_system != required_system:
        raise ReferenceFixtureError(f"runner profile {profile} requires {required_system}, found {actual_system}")
    if not dedicated_idle:
        raise ReferenceFixtureError("capacity profile requires an otherwise idle dedicated runner")
    cpu_count = os.cpu_count()
    if cpu_count is None or cpu_count < 4:
        raise ReferenceFixtureError("capacity profile requires at least 4 logical cores")
    if profile == "linux":
        meminfo = Path("/proc/meminfo").read_text()
        total = next((line for line in meminfo.splitlines() if line.startswith("MemTotal:")), "")
        memory_bytes = int(total.split()[1]) * 1024 if total else 0
        cpuinfo = Path("/proc/cpuinfo").read_text()
        cpu_model = next((line.partition(":")[2].strip() for line in cpuinfo.splitlines()
                          if line.startswith(("model name", "Hardware"))), platform.machine())
        filesystem, ssd = _linux_volume(path)
    else:
        memory_bytes = int(_output("sysctl", "-n", "hw.memsize"))
        cpu_model = _output("sysctl", "-n", "machdep.cpu.brand_string")
        filesystem, ssd = _mac_volume(path)
    if memory_bytes < _MINIMUM_MEMORY_BYTES:
        raise ReferenceFixtureError("capacity profile requires at least 16 GiB of RAM")
    if not filesystem or not ssd:
        raise ReferenceFixtureError("capacity profile requires an attested local SSD")
    import icu

    return {
        "profile": profile, "cpu_model": cpu_model, "logical_cores": cpu_count, "memory_bytes": memory_bytes,
        "os": platform.platform(), "architecture": platform.machine(), "filesystem": filesystem,
        "ssd": ssd, "work_free_bytes": shutil.disk_usage(path).free, "sqlite": sqlite3.sqlite_version,
        "python": platform.python_version(),
        "icu": str(vars(icu)["ICU_VERSION"]), "pyicu": version("PyICU"),
    }

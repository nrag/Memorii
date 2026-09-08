"""Nonproduction package-size and stale-bytecode feasibility probe."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import zipfile


def probe(wheel: Path) -> dict[str, object]:
    with zipfile.ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        records = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            raise ValueError("expected exactly one RECORD")
        rows = list(csv.reader(io.StringIO(archive.read(records[0]).decode())))
        result: dict[str, object] = {
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "historical_wheel_only": True,
            "file_count": len(names),
            "payload_bytes": sum(archive.getinfo(name).file_size for name in names),
            "maximum_file_bytes": max(archive.getinfo(name).file_size for name in names),
            "record_rows": len(rows),
            "unsigned_record_rows": [row for row in rows if not row[1]],
            "registry_json_files": len([
                name for name in names
                if "/observation_registry_sources/" in name and name.endswith(".json")
            ]),
        }
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "sample.py"
        source.write_text("VALUE = 1\n")
        stamp = source.stat().st_mtime
        py_compile.compile(str(source), doraise=True)
        source.write_text("VALUE = 2\n")
        os.utime(source, (stamp, stamp))
        command = [sys.executable, "-c", "import sample; print(sample.VALUE)"]
        observed = subprocess.check_output(command, cwd=directory, text=True).strip()
        isolated = subprocess.check_output(
            [sys.executable, "-X", f"pycache_prefix={directory}/fresh-cache", *command[1:]],
            cwd=directory, text=True,
        ).strip()
        if observed != "1" or isolated != "2":
            raise AssertionError("stale-cache discrimination failed")
        result["stale_pyc"] = {
            "verified_disk_value": 2,
            "executed_value": int(observed),
            "fresh_cache_executed_value": int(isolated),
            "same_size_and_timestamp": True,
            "conclusion": "Disk/RECORD verification alone cannot establish loaded source identity.",
        }
    return result


if __name__ == "__main__":
    print(json.dumps(probe(Path(sys.argv[1])), indent=2))

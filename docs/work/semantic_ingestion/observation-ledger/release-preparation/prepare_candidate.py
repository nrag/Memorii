"""Proof-only acquisition/inventory driver; runtime installation stays offline.

Arguments: WHEEL_DIRECTORY NEW_DEPLOYMENT_DIRECTORY [--acquire]. With acquisition,
pin the installed base dependency closure, then build/download its wheels. Input
wheel bytes and explicit import-root choices are retained before installation.

Acquired third-party wheels that ship bytecode members are rebuilt without those
members (and without their RECORD rows) before certification: the deployment
prepare contract admits source-only wheels, and every published numpy 1.26.x
CPython Linux wheel carries a stray legacy numpy/distutils __pycache__ entry that
would otherwise make the required dependency closure uncertifiable. The memorii
wheel itself is never rebuilt, and each rebuilt wheel records both its upstream
and prepared digests plus the removed members in wheel-inputs.json.
"""
import csv
import io
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import zipfile


def _is_bytecode_member(name: str) -> bool:
    return name.endswith(".pyc") or "__pycache__" in name.split("/")


def _strip_bytecode_members(wheel: Path) -> tuple[str, list[str]]:
    """Rebuild one wheel without bytecode members; return upstream digest."""
    upstream = sha256(wheel.read_bytes()).hexdigest()
    with zipfile.ZipFile(wheel) as archive:
        members = archive.infolist()
        removed = {row.filename for row in members if _is_bytecode_member(row.filename)}
        if not removed:
            return upstream, []
        if any(row.filename.split("/")[0].removesuffix(".dist-info") == "memorii"
               for row in members if row.filename.endswith(".dist-info/METADATA")):
            raise ValueError(f"memorii_wheel_bytecode_not_permitted:{wheel.name}")
        record_name = next(
            (row.filename for row in members
             if re.fullmatch(r"[^/]+\.dist-info/RECORD", row.filename)),
            None,
        )
        record_bytes = None if record_name is None else archive.read(record_name)
        rebuilt = wheel.with_name(wheel.name + ".rebuilt")
        with zipfile.ZipFile(rebuilt, "w", zipfile.ZIP_DEFLATED) as output:
            for row in members:
                if row.filename in removed:
                    continue
                data = archive.read(row.filename)
                if row.filename == record_name:
                    kept = []
                    for line in record_bytes.decode("utf-8").splitlines(keepends=True):
                        parsed = next(csv.reader(io.StringIO(line)), None)
                        if parsed is not None and parsed[0] not in removed:
                            kept.append(line)
                    data = "".join(kept).encode("utf-8")
                info = zipfile.ZipInfo(row.filename, date_time=row.date_time)
                info.external_attr = row.external_attr
                info.compress_type = row.compress_type
                output.writestr(info, data)
    rebuilt.replace(wheel)
    return upstream, sorted(removed)


def main():
    wheels, destination = (Path(value).resolve() for value in sys.argv[1:3])
    repository = Path(__file__).resolve().parents[5]
    wheels.mkdir(parents=True, exist_ok=True)
    provenance: dict[str, dict[str, object]] = {}
    if "--acquire" in sys.argv[3:]:
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
        pending = [Requirement(value) for value in tomllib.loads((repository / "memorii/pyproject.toml").read_text())["project"]["dependencies"]]
        selected = {}
        while pending:
            requirement = pending.pop()
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            name = canonicalize_name(requirement.name)
            if name in selected:
                continue
            installed = importlib.metadata.distribution(name)
            if installed.version not in requirement.specifier:
                raise ValueError(f"installed_dependency_version_mismatch:{name}")
            selected[name] = installed.version
            pending.extend(Requirement(value) for value in installed.requires or ())
        requirements = wheels / "requirements.txt"
        requirements.write_text("".join(f"{name}=={version}\n" for name, version in sorted(selected.items())))
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheels), "-r", str(requirements)], check=True, timeout=300)
        for wheel in sorted(wheels.glob("*.whl")):
            upstream, removed = _strip_bytecode_members(wheel)
            if removed:
                provenance[wheel.name] = dict(
                    upstream_sha256=upstream, removed_bytecode_members=removed,
                )
    rows = []
    for path in sorted(wheels.glob("*.whl")):
        with zipfile.ZipFile(path) as archive:
            roots = sorted({name.split("/")[0] for name in archive.namelist()
                if "/" not in name or not name.split("/")[0].endswith((".dist-info", ".data", ".libs"))})
        row = dict(path=str(path), sha256=sha256(path.read_bytes()).hexdigest(), roots=roots)
        if path.name in provenance:
            row.update(provenance[path.name])
        rows.append(row)
    (wheels / "wheel-inputs.json").write_text(json.dumps(rows, indent=2) + "\n")
    if not rows:
        raise ValueError("no_candidate_wheels")
    # A real valid candidate wheel must still fail before pip after substitution.
    original = next(row for row in rows if Path(row["path"]).name.startswith("memorii-"))
    negative = wheels / "tamper-proof"
    negative.mkdir()
    modified = negative / Path(original["path"]).name
    modified.write_bytes(Path(original["path"]).read_bytes() + b"tamper")
    failed = negative / "deployment"
    result = subprocess.run([sys.executable, str(repository / "tools/observation_activation_prepare.py"),
        "--destination", str(failed), "--wheel", str(modified), original["sha256"], ",".join(original["roots"])],
        capture_output=True, text=True, timeout=30)
    if result.returncode == 0 or "wheel_digest_mismatch" not in result.stderr or (failed / "environment").exists():
        raise AssertionError("candidate_wheel_tamper_not_rejected_before_install")
    (negative / "rejection.log").write_text(result.stderr)
    command = [sys.executable, str(repository / "tools/observation_activation_prepare.py"), "--destination", str(destination)]
    for row in rows:
        command.extend(("--wheel", row["path"], row["sha256"], ",".join(row["roots"])))
    subprocess.run(command, check=True, timeout=300)


if __name__ == "__main__":
    main()

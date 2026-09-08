"""Proof-only acquisition/inventory driver; runtime installation stays offline.

Arguments: WHEEL_DIRECTORY NEW_DEPLOYMENT_DIRECTORY [--acquire]. With acquisition,
pin the installed base dependency closure, then build/download its wheels. Input
wheel bytes and explicit import-root choices are retained before installation.
"""
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import zipfile


def main():
    wheels, destination = (Path(value).resolve() for value in sys.argv[1:3])
    repository = Path(__file__).resolve().parents[5]
    wheels.mkdir(parents=True, exist_ok=True)
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
    rows = []
    for path in sorted(wheels.glob("*.whl")):
        with zipfile.ZipFile(path) as archive:
            roots = sorted({name.split("/")[0] for name in archive.namelist()
                if "/" not in name or not name.split("/")[0].endswith((".dist-info", ".data", ".libs"))})
        rows.append(dict(path=str(path), sha256=sha256(path.read_bytes()).hexdigest(), roots=roots))
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

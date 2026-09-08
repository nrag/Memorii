"""Run the isolated proof against an already prepared deployment.

Arguments: PREPARED_DIRECTORY NEW_PROOF_DIRECTORY. Release input snapshots are
frozen into the protected host before it starts; runtime never chooses pins.
"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


def main():
    prepared, work = (Path(value).resolve() for value in sys.argv[1:])
    work.mkdir(mode=0o700)
    repository = Path(__file__).resolve().parents[5]
    candidate_path = Path(__file__).with_name("candidate.json")
    candidate_raw = candidate_path.read_bytes()
    candidate_digest = sha256(candidate_raw).hexdigest()
    if candidate_digest != candidate_path.with_suffix(".sha256").read_text().strip():
        raise ValueError("proof_candidate_manifest_pin_mismatch")
    for path, digest in json.loads(candidate_raw)["files"].items():
        if sha256((repository / path).read_bytes()).hexdigest() != digest:
            raise ValueError(f"proof_candidate_member_changed:{path}")
    source = repository / "memorii/memorii/core/memory_evolution/observation_registry_sources"
    publication = json.loads((source / "publication-manifest.json").read_bytes())
    vectors = (repository / "docs/work/semantic_ingestion/registry-publication/registry-vector-manifest.json").read_bytes()
    parity = json.loads((repository / "docs/work/semantic_ingestion/registry-publication/independent-positive-parity.json").read_bytes())
    constants = dict(VECTOR_BYTES=vectors, VECTOR_DIGEST=sha256(vectors).hexdigest(),
        PUBLICATION_DIGEST=parity["publication_digest"], REGISTRY_DIGEST=parity["registry_digest"],
        SNAPSHOTS=tuple((row["decoder_id"], row["source_snapshot_digest"]) for row in publication["decoder_source_snapshots"]),
        OUTPUT=str(work / "target"), HOST_SENTINEL=str(work / "host-executed"))
    host = work / "host.py"
    host.write_text("".join(f"{key} = {value!r}\n" for key, value in constants.items()) + Path(__file__).with_name("installed_host.py").read_text())
    cache = work / "cache"
    cache.mkdir(mode=0o700)
    command = [sys.executable, "-I", "-S", "-X", f"pycache_prefix={cache}",
        str(repository / "tools/observation_activation_launch.py")]
    pins = {}
    for name, path in (("bootstrap", prepared / "observation_activation_bootstrap.py"),
                       ("configuration", prepared / "deployment_configuration.py"), ("host", host)):
        digest = sha256(path.read_bytes()).hexdigest()
        pins[name] = dict(path=str(path), sha256=digest)
        command.extend((f"--{name}", str(path), f"--{name}-sha256", digest))
    (work / "invocation.json").write_text(json.dumps(dict(pins=pins, command=command), indent=2) + "\n")
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    (work / "process.log").write_text(result.stdout + result.stderr)
    if result.returncode == 0:
        proof = work / "target/proof.json"
        report = json.loads(proof.read_text())
        report.update(candidate_sha256=candidate_digest, command=command, protected_module_pins=pins,
            process_log_sha256=sha256((work / "process.log").read_bytes()).hexdigest(),
            wheel_inputs={path.name:sha256(path.read_bytes()).hexdigest() for path in sorted((prepared / "wheels").glob("*.whl"))})
        proof.write_text(json.dumps(report, indent=2) + "\n")
    print(result.stdout + result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

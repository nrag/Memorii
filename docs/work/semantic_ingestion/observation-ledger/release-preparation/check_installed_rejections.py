"""Exercise tampering on a disposable proof deployment; restore exact bytes.

Arguments: PREPARED_DIRECTORY SUCCESSFUL_PROOF_DIRECTORY. Never use on a live
deployment: this fixture deliberately changes a dependency temporarily.
"""
import json
from pathlib import Path
import subprocess
import sys


def main():
    prepared, work = (Path(value).resolve() for value in sys.argv[1:])
    command = json.loads((work / "invocation.json").read_text())["command"]
    site = next((prepared / "environment/lib").glob("python*/site-packages"))
    results = []
    sentinel = work / "host-executed"
    sentinel.unlink()
    for kind in ("configuration_pin", "host_pin", "extra_payload", "changed_payload", "changed_dependency"):
        cache = work / ("rejection-cache-" + kind)
        cache.mkdir(mode=0o700)
        candidate = command.copy()
        candidate[candidate.index("-X") + 1] = "pycache_prefix=" + str(cache)
        target, old = None, None
        if kind.endswith("_pin"):
            name = kind.removesuffix("_pin")
            candidate[candidate.index("--" + name + "-sha256") + 1] = "0" * 64
        elif kind == "extra_payload":
            target = site / "memorii/unrecorded_probe.py"
            with target.open("xb") as stream:
                stream.write(b'raise RuntimeError("must not execute")\n')
        else:
            target = site / ("memorii/__init__.py" if kind == "changed_payload" else "typing_extensions.py")
            old = target.read_bytes()
            target.write_bytes(old + b"\n")
        try:
            result = subprocess.run(candidate, capture_output=True, text=True, timeout=120)
            expected = "protected_module_digest_mismatch" if kind.endswith("_pin") else "bootstrap."
            if result.returncode == 0 or expected not in result.stderr:
                raise AssertionError((kind, result.stdout, result.stderr))
            if sentinel.exists():
                raise AssertionError("unverified host executed")
            results.append(dict(mutation=kind, rejected=True, error=result.stderr.strip().splitlines()[-1]))
        finally:
            if target is not None:
                if old is None:
                    target.unlink()
                else:
                    target.write_bytes(old)
    (work / "rejections.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results))


if __name__ == "__main__":
    main()

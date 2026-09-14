"""Compare independent recipe implementations and fixed byte preimages."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def implementations(path: Path) -> dict:
    python = json.loads(subprocess.check_output(
        [sys.executable, str(ROOT / "identity_oracle.py"), str(path)], text=True,
    ))
    javascript = json.loads(subprocess.check_output(
        ["node", str(ROOT / "identity_reference.mjs"), str(path)], text=True,
    ))
    if python != javascript:
        raise AssertionError("independent recipe preimages disagree")
    return python


def leaves(value, prefix=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, (*prefix, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, (*prefix, index))
    else:
        yield prefix, value


def main() -> None:
    original = json.loads((ROOT / "identity-input.json").read_text())
    baseline = implementations(ROOT / "identity-input.json")
    assert baseline == json.loads((ROOT / "identity-expected.json").read_text())
    changes = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "input.json"
        for coordinates, value in leaves(original):
            candidate = copy.deepcopy(original)
            owner = candidate
            for coordinate in coordinates[:-1]:
                owner = owner[coordinate]
            owner[coordinates[-1]] = (
                str(int(value) + 1) if coordinates[-1] in {"size", "schema_version"}
                else ("0" if value[0] != "0" else "1") + value[1:]
            )
            path.write_text(json.dumps(candidate))
            actual = implementations(path)
            changed = {name for name in baseline if baseline[name] != actual[name]}
            family = coordinates[0]
            if family == "package_files":
                expected = {"P", "schema", "codec", "writer"}
            elif family == "environment":
                expected = {"E", "schema", "codec", "writer"}
            elif family == "memorii_wheel_sha256":
                expected = {"writer"}
            elif family == "entries" and coordinates[-1] in {"decoder_id", "implementation_source_digest"}:
                expected = {"codec"}
            else:
                expected = {"schema", "codec"}
            assert changed == expected, (coordinates, changed, expected)
            changes.append({"field": list(coordinates), "changed": sorted(changed)})
    result = {
        "status": "INDEPENDENT_RECIPE_FEASIBILITY_PASSED",
        "positive_preimages": len(baseline),
        "isolated_field_mutations": len(changes),
        "mutations": changes,
        "limitation": "Synthetic recipe inputs, not manifest parsing or coherent publication/deployment acceptance.",
        "files": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("identity-input.json", "identity-expected.json", "identity_oracle.py", "identity_reference.mjs")
        },
    }
    (ROOT / "identity-feasibility.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Five exact preimages agree; {len(changes)} field mutations agree.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
REPOSITORY_ROOT = PROJECT_ROOT.parent
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "semantic_ingestion" / "provider_compatibility"
CAPTURE_TOOL = PROJECT_ROOT / "tools" / "extract_provider_compatibility_fixture.py"


def _capture(output: Path) -> None:
    captured = subprocess.run(
        [
            sys.executable,
            str(CAPTURE_TOOL),
            "--repository",
            str(REPOSITORY_ROOT),
            "--python",
            sys.executable,
            "--legacy-reader",
            str(FIXTURE_ROOT / "legacy_reader.py"),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert captured.returncode == 0, (
        "provider compatibility recapture failed\n"
        f"stdout:\n{captured.stdout}\n"
        f"stderr:\n{captured.stderr}"
    )


def test_historical_provider_recapture_is_byte_identical(tmp_path: Path) -> None:
    assert shutil.which("git") is not None, "git is required for the provider compatibility capture gate"
    first, second = tmp_path / "first", tmp_path / "second"
    _capture(first)
    _capture(second)

    first_files = {path.name: path.read_bytes() for path in first.iterdir()}
    second_files = {
        path.name: path.read_bytes() for path in second.iterdir()
    }
    assert first_files == second_files

    manifest = json.loads(first_files["capture_manifest.json"])
    expected_names = {*manifest["generated_files"], "capture_manifest.json"}
    assert set(first_files) == expected_names
    for name in expected_names:
        assert first_files[name] == (FIXTURE_ROOT / name).read_bytes()

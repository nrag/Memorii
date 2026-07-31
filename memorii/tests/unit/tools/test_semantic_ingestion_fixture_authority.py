"""Acceptance-only checks for the non-operational C1 fixture authority."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[4]
FIXTURES = ROOT / "memorii" / "tests" / "fixtures" / "semantic_ingestion" / "traceability_golden_vectors"
DESIGN = ROOT / "docs" / "design" / "semantic_ingestion_architecture.md"
SIGNERS = ["fixture-bootstrap-1", "fixture-bootstrap-2", "fixture-recovery-1", "fixture-recovery-2"]


def _load(name: str):
    path = FIXTURES / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _outputs(design: bytes | None = None) -> tuple[bytes, bytes]:
    raw = DESIGN.read_bytes() if design is None else design
    return (_load("elaborate_stdlib.py").elaborate(raw), _load("elaborate_independent.py").elaborate(raw))


def _assert_both_reject(design: bytes) -> None:
    outcomes: list[bool] = []
    for name in ("elaborate_stdlib.py", "elaborate_independent.py"):
        try:
            _load(name).elaborate(design)
        except ValueError:
            outcomes.append(True)
        else:
            outcomes.append(False)
    assert outcomes == [True, True], f"elaborator rejection disagreement: {outcomes}"


def _extract_design_signer_rows(design: bytes) -> list[dict[str, str]]:
    """Test-owned parser, independent of both fixture elaborators."""
    rows: list[dict[str, str]] = []
    for line in design.splitlines():
        if not line.startswith((b"| `fixture-bootstrap-", b"| `fixture-recovery-")):
            continue
        parts = line.decode("ascii").removeprefix("| ").removesuffix(" |").split(" | ")
        if len(parts) != 5:
            raise ValueError("invalid fixed signer table row")
        signer, seed, public, message, signature = parts
        rows.append(
            {
                "signer": signer.removeprefix("`").removesuffix("`"),
                "seed_hex": seed.removeprefix("`").removesuffix("`"),
                "public_key_hex": public.removeprefix("`").removesuffix("`"),
                "message_hex": "" if message == "empty" else message.removeprefix("`").removesuffix("`"),
                "signature_hex": signature.removeprefix("`").removesuffix("`"),
            }
        )
    if [row["signer"] for row in rows] != SIGNERS:
        raise ValueError("fixed signer table does not contain the exact signer sequence")
    return rows


def test_sia_m0a_c1_independent_elaborators_pin_the_frozen_profile_registry() -> None:
    stdlib, independent = _outputs()
    assert stdlib == independent
    expected = json.loads((FIXTURES / "c1-v1.expected.json").read_bytes())
    output = json.loads(stdlib)
    assert hashlib.sha256(stdlib).hexdigest() == expected["output_sha256"]
    assert output["design_document_digest"] == expected["design_document_digest"]
    assert output["grammar_digest"] == expected["grammar_digest"]
    assert output["schema_inventory_digest"] == expected["inventory_digest"]
    assert output["profile_digest"] == expected["profile_digest"]
    assert output["registry_digest"] == expected["registry_digest"]
    assert len(output["entries"]) == expected["schema_count"]
    assert hashlib.sha256(DESIGN.read_bytes()).hexdigest() == "158277cd433c85714253359e134c94ece0f3ad59d2b3f1b9a403c295417a397e"
    assert [entry["schema_id"] for entry in output["entries"]] == (FIXTURES / "c1-v1.inventory.txt").read_text().splitlines()
    pinned_vectors = json.loads((FIXTURES / "c1-v1.vectors.json").read_bytes())
    assert [{key: vector[key] for key in pinned_vectors[0]} for vector in output["ed25519_vectors"]] == pinned_vectors


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.replace(b"tuple=tagged_declared_order", b"tuple=changed_declared_order"),
        lambda value: value.replace(b"CanonicalEncodedArtifact.v1\n", b"OtherArtifact.v1\n"),
        lambda value: value.replace(b"TraceabilityTrustLifecycleRootBody.v1\n", b""),
        lambda value: value.replace(b"profile_version=1", b"profile_version=2"),
    ],
)
def test_sia_m0a_c1_design_mutations_do_not_reproduce_pinned_output(mutation) -> None:
    altered = mutation(DESIGN.read_bytes())
    stdlib_outcome: bytes | None = None
    independent_outcome: bytes | None = None
    with suppress(ValueError):
        stdlib_outcome = _load("elaborate_stdlib.py").elaborate(altered)
    with suppress(ValueError):
        independent_outcome = _load("elaborate_independent.py").elaborate(altered)
    assert (stdlib_outcome is None) == (independent_outcome is None)
    if stdlib_outcome is not None:
        assert stdlib_outcome == independent_outcome
        assert hashlib.sha256(stdlib_outcome).hexdigest() != json.loads((FIXTURES / "c1-v1.expected.json").read_bytes())["output_sha256"]


def test_sia_m0a_c1_signature_profile_contains_all_fixed_keys_and_successor() -> None:
    output = json.loads(_outputs()[0])
    vectors = output["ed25519_vectors"]
    design_rows = _extract_design_signer_rows(DESIGN.read_bytes())
    assert [vector["signer"] for vector in vectors] == SIGNERS
    assert [{key: vector[key] for key in design_rows[0]} for vector in vectors] == design_rows
    assert all(len(bytes.fromhex(vector["public_key_hex"])) == 32 for vector in vectors)
    assert all(len(bytes.fromhex(vector["signature_hex"])) == 64 for vector in vectors)
    assert hashlib.sha256(b"memorii:sia-test-ed25519-seed:fixture-bootstrap-2:v1").hexdigest() == vectors[1]["seed_hex"]


def test_sia_m0a_c1_rejects_the_reviewed_one_extra_five_signature_mutation() -> None:
    valid = b"e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    malformed = valid.replace(b"901555fb", b"9015555fb")
    assert len(malformed) == 129
    mutated = DESIGN.read_bytes().replace(valid, malformed)
    malformed_hex = _extract_design_signer_rows(mutated)[0]["signature_hex"]
    assert len(malformed_hex) == 129
    with pytest.raises(ValueError):
        bytes.fromhex(malformed_hex)
    _assert_both_reject(mutated)


def _replace_signer_row(design: bytes, signer: str, mutate: Callable[[list[str]], None]) -> bytes:
    prefix = f"| `{signer}` |".encode()
    line = next(line for line in design.splitlines() if line.startswith(prefix))
    cells = line.decode().removeprefix("| ").removesuffix(" |").split(" | ")
    mutate(cells)
    replacement = ("| " + " | ".join(cells) + " |").encode()
    return design.replace(line, replacement)


def _flip_nibble(value: str) -> str:
    return ("1" if value[0] != "1" else "2") + value[1:]


def test_sia_m0a_c1_each_elaborator_rejects_every_fixed_vector_field_mutation() -> None:
    design = DESIGN.read_bytes()
    for signer in SIGNERS:
        for index in (1, 2, 4):
            _assert_both_reject(
                _replace_signer_row(design, signer, lambda cells, index=index: cells.__setitem__(index, f"`{_flip_nibble(cells[index][1:-1])}`"))
            )
        # The empty RFC vector has no nibble to flip; replacing it with one
        # valid hex byte is the smallest message mutation.
        _assert_both_reject(
            _replace_signer_row(
                design,
                signer,
                lambda cells: cells.__setitem__(
                    3,
                    "`00`" if cells[3] == "empty" else f"`{_flip_nibble(cells[3][1:-1])}`",
                ),
            )
        )
    first, second = SIGNERS[:2]
    first_row = next(line for line in design.splitlines() if line.startswith(f"| `{first}` |".encode()))
    second_row = next(line for line in design.splitlines() if line.startswith(f"| `{second}` |".encode()))
    _assert_both_reject(
        design.replace(first_row, b"@@FIRST-SIGNER-ROW@@", 1)
        .replace(second_row, first_row, 1)
        .replace(b"@@FIRST-SIGNER-ROW@@", second_row, 1)
    )
    _assert_both_reject(design.replace(second_row, second_row.replace(second.encode(), first.encode())))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw + b"\n",
        lambda raw: raw[:-1],
        lambda raw: b"\xef\xbb\xbf" + raw,
        lambda raw: raw.replace(b"\n", b"\r\n"),
        lambda raw: raw.replace(b"Source-Grounded", b"Source\x00-Grounded", 1),
        lambda raw: raw.replace(b"Source-Grounded", b"Source\r-Grounded", 1),
        lambda raw: raw.replace(b"# Source-Grounded", b"`[SIA-CTV-GRAMMAR-V1-BEGIN]`\n# Source-Grounded", 1),
        lambda raw: raw.replace(b"\n`[SIA-CTV-GRAMMAR-V1-BEGIN]`\n```text", b"\nx`[SIA-CTV-GRAMMAR-V1-BEGIN]`\n```text", 1),
        lambda raw: raw.replace(b"\n`[SIA-CTV-GRAMMAR-V1-BEGIN]`\n```text", b"\n`[SIA-CTV-GRAMMAR-V1-BEGIN]`x\n```text", 1),
        lambda raw: raw.replace(b"\n`[SIA-CTV-GRAMMAR-V1-BEGIN]`\n```text", b"\n` [SIA-CTV-GRAMMAR-V1-BEGIN]`\n```text", 1),
        lambda raw: raw.replace(b"\n`[SIA-CTV-GRAMMAR-V1-BEGIN]`\n```text", b"\n`[SIA-CTV-GRAMMAR-V1-BEGIN]`\n[SIA-CTV-GRAMMAR-V1-BEGIN]\n```text", 1),
        lambda raw: raw.replace(b"```text\nprofile_id=", b"``` text\nprofile_id=", 1),
        lambda raw: raw.replace(b"profile_id=semantic", "profile_id=sémantic".encode(), 1),
    ],
)
def test_sia_m0a_c1_raw_design_preflight_rejects_mutations_in_both_paths(mutation) -> None:
    _assert_both_reject(mutation(DESIGN.read_bytes()))


def test_sia_m0a_c1_elaborators_are_production_isolated() -> None:
    forbidden = ("import memorii", "from memorii", "pydantic", "semantic_ingestion_traceability", "elaborate_independent", "elaborate_stdlib")
    for path in (FIXTURES / "elaborate_stdlib.py", FIXTURES / "elaborate_independent.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(token in source for token in forbidden if token not in path.stem)


def test_sia_m0a_c1_production_ast_and_bytes_exclude_fixture_authority() -> None:
    forbidden = (
        "traceability_golden_vectors",
        "fixture-bootstrap-1",
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
    )
    production = ROOT / "memorii" / "memorii"
    for path in production.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        assert not any(token in source for token in forbidden), path


def test_sia_m0a_c1_built_wheel_excludes_fixture_authority(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "wheel"
    site_dir = tmp_path / "site"
    wheel_dir.mkdir()
    environment = {**os.environ, "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
        ],
        cwd=ROOT / "memorii",
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(wheel_dir.glob("memorii-*.whl"))
    assert len(wheels) == 1
    forbidden = (
        b"traceability_golden_vectors",
        b"fixture-bootstrap-1",
        b"9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        b"tests/unit/tools/test_semantic_ingestion_fixture_authority.py",
    )
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        assert not any(name.startswith(("tests/", "memorii/tests/")) for name in names)
        for name in names:
            if name.endswith((".py", ".json", ".txt")):
                contents = archive.read(name)
                assert not any(token in contents for token in forbidden), name
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(site_dir),
            str(wheels[0]),
        ],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    probe = (
        "import importlib, memorii\n"
        "assert 'site' in memorii.__file__\n"
        "try:\n"
        " importlib.import_module('memorii.tests.fixtures.semantic_ingestion.traceability_golden_vectors.elaborate_stdlib')\n"
        "except ModuleNotFoundError:\n"
        " pass\n"
        "else:\n"
        " raise AssertionError('fixture elaborator is importable from wheel')\n"
    )
    subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env={**environment, "PYTHONPATH": str(site_dir)},
        check=True,
        capture_output=True,
        text=True,
    )

"""Black-box tests for the clean-room CTV v2 reference compiler."""

from __future__ import annotations

import ast
import base64
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[4]
PROJECT = ROOT / "memorii"
DESIGN = ROOT / "docs" / "design" / "semantic_ingestion_architecture.md"
REGISTRY = ROOT / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json"
FROZEN_AUTHORITY = (
    ROOT
    / "docs"
    / "design"
    / "semantic_ingestion"
    / "traceability_golden_vectors"
    / "ctv-binding-authority-v2.json"
)
COMPILER = PROJECT / "memorii" / "tools" / "semantic_ingestion_ctv_reference_compiler.py"
VALIDATOR = (
    ROOT
    / "docs"
    / "design"
    / "semantic_ingestion"
    / "traceability_golden_vectors"
    / "validate_ctv_binding_authority_v2.py"
)
CHECKER = (
    ROOT
    / "docs"
    / "design"
    / "semantic_ingestion"
    / "traceability_golden_vectors"
    / "check_ctv_binding_authority_v2.py"
)
EXPECTED_DESIGN_SHA256 = "786c9f22c33db76bb16518cfa6da57ae95084b126e36d6462d6cd122d75fa17e"
EXPECTED_AUTHORITY_SHA256 = "fe5778f0518f198ebe44e239460a8fac2a747cac58c7c94c0b3dfb148fae1ab2"
EXPECTED_VALIDATOR_SHA256 = "317133f2e92ad8032968314b3f16ff1b08b031c93c0ebcd3bbd789a876de5d6d"
EXPECTED_CHECKER_SHA256 = "e2c35870a99e587f34cbffc701f42587520ee015009cd51647367da56716c732"
EXPECTED_PROFILE_DIGEST = "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f"
PYTHON312_ISOLATED = ("python3.12", "-I")
AUDIT_BOOTSTRAP = r"""
from __future__ import annotations
import os
import runpy
import sys
from pathlib import Path

compiler, design, registry, output = sys.argv[1:]
declared = {
    Path(compiler).resolve(),
    Path(design).resolve(),
    Path(registry).resolve(),
    Path(output).resolve(),
}
output_parent = Path(output).resolve().parent
runtime_roots = {
    Path(sys.base_prefix).resolve(),
    Path(sys.prefix).resolve(),
}

def audit(event, arguments):
    if event.startswith(("socket.", "subprocess.", "ctypes.", "urllib.", "http.")):
        raise PermissionError(f"forbidden runtime event: {event}")
    if event != "open" or not arguments or not isinstance(arguments[0], (str, bytes)):
        return
    raw = os.fsdecode(arguments[0])
    if raw in {"/dev/null", os.devnull}:
        return
    path = Path(raw).resolve(strict=False)
    temporary_output = path.parent == output_parent and path.name.startswith(
        f".{Path(output).name}."
    ) and path.name.endswith(".tmp")
    if path in declared or temporary_output or any(path.is_relative_to(root) for root in runtime_roots):
        return
    raise PermissionError(f"undeclared file access: {path}")

sys.addaudithook(audit)
sys.argv = [compiler, "--design", design, "--registry", registry, "--output", output]
runpy.run_path(compiler, run_name="__main__")
"""
COLLISION_BOOTSTRAP = r"""
from __future__ import annotations
import os
import runpy
import sys
from pathlib import Path

compiler, design, registry, output = sys.argv[1:]
foreign = Path(output).with_name(f".{Path(output).name}.{os.getpid()}.tmp")
foreign.write_bytes(b"foreign-temp-owner\n")
sys.argv = [compiler, "--design", design, "--registry", registry, "--output", output]
runpy.run_path(compiler, run_name="__main__")
"""
Mutation = Callable[[bytes], bytes]
CANONICAL_ARTIFACT_DECLARATION = (
    b"class CanonicalEncodedArtifact(BaseModel):\n"
    b"    binding: CanonicalTypedValueProfileBinding\n"
    b"    canonical_value_bytes: bytes\n"
)


def _command(design: Path, registry: Path, output: Path, compiler: Path = COMPILER) -> list[str]:
    return [
        *PYTHON312_ISOLATED,
        str(compiler),
        "--design",
        str(design),
        "--registry",
        str(registry),
        "--output",
        str(output),
    ]


def _run(
    design: Path,
    registry: Path,
    output: Path,
    compiler: Path = COMPILER,
    *,
    environment: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    run_environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "73",
        "PYTHONNOUSERSITE": "1",
        "TZ": "UTC",
    }
    if environment is not None:
        run_environment.update(environment)
    return subprocess.run(
        _command(design, registry, output, compiler),
        cwd=output.parent if cwd is None else cwd,
        env=run_environment,
        capture_output=True,
        text=True,
    )


def _validator_run(design: Path, registry: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            *PYTHON312_ISOLATED,
            str(VALIDATOR),
            "--design",
            str(design),
            "--registry",
            str(registry),
            "--authority",
            str(output),
            "--write",
        ],
        cwd=output.parent,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        },
        capture_output=True,
        text=True,
    )


def _checker_run(
    registry: Path,
    authority: Path,
    *,
    expected_registry_sha256: str,
    expected_authority_sha256: str = EXPECTED_AUTHORITY_SHA256,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            *PYTHON312_ISOLATED,
            str(CHECKER),
            "--design",
            str(DESIGN),
            "--registry",
            str(registry),
            "--authority",
            str(authority),
            "--validator",
            str(VALIDATOR),
            "--expected-design-sha256",
            EXPECTED_DESIGN_SHA256,
            "--expected-registry-sha256",
            expected_registry_sha256,
            "--expected-authority-sha256",
            expected_authority_sha256,
            "--expected-validator-sha256",
            EXPECTED_VALIDATOR_SHA256,
            "--expected-checker-sha256",
            EXPECTED_CHECKER_SHA256,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _replace_once(value: bytes, old: bytes, new: bytes) -> bytes:
    assert value.count(old) == 1, old
    return value.replace(old, new, 1)


def _marked_payload(document: bytes, marker: str, language: str) -> bytes:
    begin = f"`[{marker}-BEGIN]`\n```{language}\n".encode()
    end = f"```\n`[{marker}-END]`".encode()
    assert document.count(begin) == 1
    start = document.index(begin) + len(begin)
    finish = document.index(end, start)
    return document[start:finish]


def _replace_marked(document: bytes, marker: str, language: str, payload: bytes) -> bytes:
    original = _marked_payload(document, marker, language)
    begin = f"`[{marker}-BEGIN]`\n```{language}\n".encode()
    start = document.index(begin) + len(begin)
    finish = start + len(original)
    return document[:start] + payload + document[finish:]


def _expected_v2_source_design_sha256(document: bytes) -> str:
    pattern = (
        rb"(^`\[SIA-CTV-ENUM-REGISTRY-V1-BEGIN\]`\n```json\n)"
        rb"(.*?)"
        rb"(```\n`\[SIA-CTV-ENUM-REGISTRY-V1-END\]`$)"
    )
    matches = list(re.finditer(pattern, document, re.DOTALL | re.MULTILINE))
    assert len(matches) == 1
    match = matches[0]
    redacted = (
        document[: match.start(2)]
        + b"<v1-baseline-excluded-from-v2-authority>\n"
        + document[match.end(2) :]
    )
    return hashlib.sha256(redacted).hexdigest()


def _enum_document_mutation(update: Callable[[dict[str, Any]], None]) -> Mutation:
    def mutate(document: bytes) -> bytes:
        rows = json.loads(_marked_payload(document, "SIA-CTV-ENUM-REGISTRY-V2", "json"))
        assert isinstance(rows, dict)
        update(rows)
        payload = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        return _replace_marked(document, "SIA-CTV-ENUM-REGISTRY-V2", "json", payload)

    return mutate


def _remove_first_enum(rows: dict[str, Any]) -> None:
    rows.pop(next(iter(rows)))


def _add_enum(rows: dict[str, Any]) -> None:
    rows["Round3UnknownEnum"] = ["unknown"]


def _duplicate_enum_member(rows: dict[str, Any]) -> None:
    members = rows["NormativeExecutionEvidenceRecordBody.execution_result"]
    assert isinstance(members, list)
    members.append(members[0])


def _confuse_enum_member_type(rows: dict[str, Any]) -> None:
    rows["TraceabilityApprovalGoldenVectorManifestBody.manifest_version"] = [True]


def _reverse_enum_member_order(rows: dict[str, Any]) -> None:
    members = rows["NormativeExecutionEvidenceRecordBody.execution_result"]
    assert isinstance(members, list)
    members.reverse()


def _valid_enum_mutation(document: bytes) -> bytes:
    old = (
        b'    execution_status: Literal["not_executed", "executed", "cancelled", "error"]\n'
        b'    execution_result: Literal["pass", "fail", "indeterminate"]\n'
    )
    new = (
        b'    execution_status: Literal["not_executed", "executed", "cancelled", "error"]\n'
        b'    execution_result: Literal["pass", "fail", "round3_indeterminate"]\n'
    )
    changed = _replace_once(document, old, new)

    def update(rows: dict[str, Any]) -> None:
        members = rows["NormativeExecutionEvidenceRecordBody.execution_result"]
        assert isinstance(members, list)
        assert members == ["pass", "fail", "indeterminate"]
        members[-1] = "round3_indeterminate"

    return _enum_document_mutation(update)(changed)


def _duplicate_class(document: bytes) -> bytes:
    declaration = (
        b"class CanonicalEncodedArtifact(BaseModel):\n"
        b"    binding: CanonicalTypedValueProfileBinding\n"
        b"    canonical_value_bytes: bytes\n"
        b"    canonical_value_digest: str\n"
        b"    artifact_digest: str\n"
    )
    assert document.count(declaration) == 1
    return document.replace(declaration, declaration + b"\n" + declaration, 1)


def _inheritance_cycle(document: bytes) -> bytes:
    needle = b"class CanonicalEncodedArtifact(BaseModel):"
    replacement = (
        b"class Round3CycleA(Round3CycleB):\n"
        b"    cycle_a: str\n\n"
        b"class Round3CycleB(Round3CycleA):\n"
        b"    cycle_b: str\n\n"
        b"class CanonicalEncodedArtifact(Round3CycleA):"
    )
    return _replace_once(document, needle, replacement)


def _recursive_alias(document: bytes) -> bytes:
    needle = (
        b"class CanonicalEncodedArtifact(BaseModel):\n"
        b"    binding: CanonicalTypedValueProfileBinding\n"
    )
    replacement = (
        b"Round3RecursiveAlias = Round3RecursiveAlias\n\n"
        b"class CanonicalEncodedArtifact(BaseModel):\n"
        b"    binding: Round3RecursiveAlias\n"
    )
    return _replace_once(document, needle, replacement)


def _duplicate_generation_tag(document: bytes) -> bytes:
    block = (
        b"class TraceabilityRawRegistryGenerationMember(\n"
        b"    TraceabilityGenerationMemberBase\n"
        b"):\n"
        b'    artifact_kind: Literal["registry_source"]\n'
    )
    return _replace_once(
        document,
        block,
        block.replace(b'"registry_source"', b'"design_document"'),
    )


def _remove_generation_member(document: bytes) -> bytes:
    return _replace_once(document, b"    | TraceabilityReleaseGenerationMember\n", b"")


def _reorder_generation_members(document: bytes) -> bytes:
    ordered = (
        b"    TraceabilityRawDesignGenerationMember\n"
        b"    | TraceabilityRawRegistryGenerationMember\n"
    )
    reversed_order = (
        b"    TraceabilityRawRegistryGenerationMember\n"
        b"    | TraceabilityRawDesignGenerationMember\n"
    )
    return _replace_once(document, ordered, reversed_order)


INVALID_DESIGN_CORPUS: tuple[tuple[str, Mutation], ...] = (
    (
        "syntax_marker",
        lambda value: _replace_once(
            value,
            b"`[SIA-CTV-GRAMMAR-V2-BEGIN]`",
            b"`[SIA-CTV-GRAMMAR-V2-MISSING]`",
        ),
    ),
    ("grammar_omission", lambda value: _replace_once(value, b"unknown_tag=reject\n", b"")),
    (
        "grammar_duplicate",
        lambda value: _replace_once(
            value,
            b"unknown_tag=reject\n",
            b"unknown_tag=reject\nunknown_tag=reject\n",
        ),
    ),
    ("namespace_class_class", _duplicate_class),
    (
        "namespace_alias_class",
        lambda value: _replace_once(
            value,
            b"class CanonicalEncodedArtifact(BaseModel):",
            b"CanonicalEncodedArtifact = str\n\nclass CanonicalEncodedArtifact(BaseModel):",
        ),
    ),
    (
        "qualified_base",
        lambda value: _replace_once(
            value,
            b"class CanonicalEncodedArtifact(BaseModel):",
            b"class CanonicalEncodedArtifact(models.BaseModel):",
        ),
    ),
    (
        "dynamic_body",
        lambda value: _replace_once(
            value,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: CanonicalTypedValueProfileBinding\n",
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: CanonicalTypedValueProfileBinding\n"
            b"    def forbidden(self): ...\n",
        ),
    ),
    (
        "class_type_parameters",
        lambda value: _replace_once(
            value,
            b"class CanonicalEncodedArtifact(BaseModel):",
            b"class CanonicalEncodedArtifact[T](BaseModel):",
        ),
    ),
    (
        "protocol_method_type_parameters",
        lambda value: _replace_once(
            value,
            b"    def load_current(self) -> DeploymentAuthorizationTrustSnapshot: ...",
            b"    def load_current[T](self) -> DeploymentAuthorizationTrustSnapshot: ...",
        ),
    ),
    (
        "nonsimple_annotated_assignment",
        lambda value: _replace_once(
            value,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: CanonicalTypedValueProfileBinding\n",
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    (binding): CanonicalTypedValueProfileBinding\n",
        ),
    ),
    (
        "default_factory",
        lambda value: _replace_once(
            value,
            b'class CanonicalTypedValueProfileBinding(BaseModel):\n'
            b'    profile_id: Literal["semantic_ingestion_typed_value"]\n'
            b"    profile_version: int = Field(ge=1)\n",
            b'class CanonicalTypedValueProfileBinding(BaseModel):\n'
            b'    profile_id: Literal["semantic_ingestion_typed_value"]\n'
            b"    profile_version: int = Field(default_factory=int)\n",
        ),
    ),
    (
        "unresolved_forward_reference",
        lambda value: _replace_once(
            value,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: CanonicalTypedValueProfileBinding\n",
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b'    binding: "Round3MissingType"\n',
        ),
    ),
    ("enum_missing", _enum_document_mutation(_remove_first_enum)),
    ("enum_extra", _enum_document_mutation(_add_enum)),
    ("enum_duplicate", _enum_document_mutation(_duplicate_enum_member)),
    ("enum_type_confusion", _enum_document_mutation(_confuse_enum_member_type)),
    ("enum_order", _enum_document_mutation(_reverse_enum_member_order)),
    (
        "open_graph",
        lambda value: _replace_once(
            value,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: CanonicalTypedValueProfileBinding\n",
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: Any\n",
        ),
    ),
    ("recursive_alias", _recursive_alias),
    ("inheritance_cycle", _inheritance_cycle),
    (
        "unsupported_generic",
        lambda value: _replace_once(
            value,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: CanonicalTypedValueProfileBinding\n",
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: Sequence[str]\n",
        ),
    ),
    (
        "collection_missing_arity",
        lambda value: _replace_once(
            value,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: CanonicalTypedValueProfileBinding\n",
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: list\n",
        ),
    ),
    (
        "discriminator_metadata",
        lambda value: _replace_once(
            value,
            b"    | TraceabilityGoldenVectorManifestGenerationMember,\n"
            b'    Field(discriminator="artifact_kind"),\n',
            b"    | TraceabilityGoldenVectorManifestGenerationMember,\n"
            b'    Field(alias="artifact_kind"),\n',
        ),
    ),
    ("tagged_union_removed_member", _remove_generation_member),
    ("tagged_union_reordered", _reorder_generation_members),
    (
        "tagged_union_substitution",
        lambda value: _replace_once(
            value,
            b"    | TraceabilityReleaseGenerationMember\n",
            b"    | CanonicalEncodedArtifact\n",
        ),
    ),
    ("tagged_union_duplicate_tag", _duplicate_generation_tag),
)
REFERENCE_ONLY_INVALID_CORPUS: tuple[tuple[str, Mutation], ...] = (
    (
        "collection_extra_arity",
        lambda value: _replace_once(
            value,
            b"    canonical_value_bytes: bytes\n",
            b"    canonical_value_bytes: list[str, int]\n",
        ),
    ),
    (
        "tuple_invalid_ellipsis",
        lambda value: _replace_once(
            value,
            b"    canonical_value_bytes: bytes\n",
            b"    canonical_value_bytes: tuple[..., str]\n",
        ),
    ),
)


def _replace_binding(annotation: bytes) -> Mutation:
    return lambda value: _replace_once(
        value,
        CANONICAL_ARTIFACT_DECLARATION,
        b"class CanonicalEncodedArtifact(BaseModel):\n"
        b"    binding: " + annotation + b"\n"
        b"    canonical_value_bytes: bytes\n",
    )


def _replace_with_inherited_binding(annotation: bytes) -> Mutation:
    return lambda value: _replace_once(
        value,
        CANONICAL_ARTIFACT_DECLARATION,
        b"class Layer1CollectionParent(BaseModel):\n"
        b"    binding: " + annotation + b"\n\n"
        b"class CanonicalEncodedArtifact(Layer1CollectionParent):\n"
        b"    canonical_value_bytes: bytes\n",
    )


COLLECTION_TYPE_INVALID_CORPUS: tuple[tuple[str, Mutation], ...] = (
    *REFERENCE_ONLY_INVALID_CORPUS,
    ("direct_collection_extra_arity", _replace_binding(b"list[str, int]")),
    ("whole_quoted_collection_extra_arity", _replace_binding(b'"list[str, int]"')),
    ("quoted_collection_child", _replace_binding(b'list["str", int]')),
    ("nested_collection_extra_arity", _replace_binding(b"tuple[list[str, int], ...]")),
    (
        "aliased_collection_extra_arity",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1InvalidCollectionAlias = list[str, int]\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ).replace(
            CANONICAL_ARTIFACT_DECLARATION,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: Layer1InvalidCollectionAlias\n"
            b"    canonical_value_bytes: bytes\n",
            1,
        ),
    ),
    ("inherited_collection_extra_arity", _replace_with_inherited_binding(b"list[str, int]")),
    (
        "reachable_unprojected_collection_extra_arity",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1UnprojectedInvalidCollection = list[str, int]\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    ("tuple_quoted_ellipsis_child", _replace_binding(b'tuple[str, "..."]')),
    ("direct_map_missing_value", _replace_binding(b"dict[str]")),
    ("direct_map_extra_arity", _replace_binding(b"dict[str, int, bool]")),
    ("whole_quoted_map_missing_value", _replace_binding(b'"dict[str]"')),
    ("nested_map_extra_arity", _replace_binding(b"tuple[dict[str, int, bool], ...]")),
    (
        "aliased_map_missing_value",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1InvalidMapAlias = dict[str]\n\n" + CANONICAL_ARTIFACT_DECLARATION,
        ).replace(
            CANONICAL_ARTIFACT_DECLARATION,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: Layer1InvalidMapAlias\n"
            b"    canonical_value_bytes: bytes\n",
            1,
        ),
    ),
    ("inherited_map_extra_arity", _replace_with_inherited_binding(b"dict[str, int, bool]")),
    (
        "unprojected_map_missing_value",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1UnprojectedInvalidMap = dict[str]\n\n" + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
)

COLLECTION_TYPE_VALID_CONTROLS: tuple[tuple[str, Mutation], ...] = (
    ("direct_unary_collection", _replace_binding(b"list[str]")),
    ("whole_quoted_unary_collection", _replace_binding(b'"list[str]"')),
    ("quoted_unary_collection_child", _replace_binding(b'list["str"]')),
    ("nested_exact_variadic_tuple", _replace_binding(b"tuple[list[str], ...]")),
    (
        "aliased_unary_collection",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1ValidCollectionAlias = list[str]\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ).replace(
            CANONICAL_ARTIFACT_DECLARATION,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: Layer1ValidCollectionAlias\n"
            b"    canonical_value_bytes: bytes\n",
            1,
        ),
    ),
    ("inherited_unary_collection", _replace_with_inherited_binding(b"list[str]")),
    (
        "unprojected_valid_unary_collection",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1UnprojectedValidCollection = list[str]\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    ("tuple_quoted_scalar_child", _replace_binding(b'tuple["str", ...]')),
    ("finite_zero_item_tuple", _replace_binding(b"tuple[()]")),
    ("direct_map", _replace_binding(b"dict[str, int]")),
    ("whole_quoted_map", _replace_binding(b'"dict[str, int]"')),
    ("nested_map", _replace_binding(b"tuple[dict[str, int], ...]")),
    (
        "aliased_map",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1ValidMapAlias = dict[str, int]\n\n" + CANONICAL_ARTIFACT_DECLARATION,
        ).replace(
            CANONICAL_ARTIFACT_DECLARATION,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: Layer1ValidMapAlias\n"
            b"    canonical_value_bytes: bytes\n",
            1,
        ),
    ),
    ("inherited_map", _replace_with_inherited_binding(b"dict[str, int]")),
    (
        "unprojected_map",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1UnprojectedValidMap = dict[str, int]\n\n" + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
)

FIELD_TYPE_INVALID_CORPUS: tuple[tuple[str, Mutation], ...] = (
    ("direct_field_type", _replace_binding(b"Field()")),
    ("whole_quoted_field_type", _replace_binding(b'"Field(default=1)"')),
    ("nested_field_type", _replace_binding(b"list[Field(ge=1)]")),
    (
        "aliased_field_type",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1BadFieldType = Field(default=1)\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ).replace(
            CANONICAL_ARTIFACT_DECLARATION,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: Layer1BadFieldType\n"
            b"    canonical_value_bytes: bytes\n",
            1,
        ),
    ),
    ("inherited_field_type", _replace_with_inherited_binding(b"Field(ge=1)")),
    (
        "unprojected_field_alias",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1UnprojectedBadField = Field(default=1)\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    (
        "unprojected_model_field_type",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"class Layer1UnprojectedBadModel(BaseModel):\n"
            b"    field: Field(default=1)\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
)

DECLARATION_GRAMMAR_INVALID_CORPUS: tuple[tuple[str, Mutation], ...] = (
    ("bare_ellipsis_type", _replace_binding(b"...")),
    ("quoted_ellipsis_type", _replace_binding(b'"..."')),
    ("set_literal_type", _replace_binding(b"{str}")),
    ("dict_literal_type", _replace_binding(b"{str: int}")),
    ("generic_ellipsis_type", _replace_binding(b"dict[..., str]")),
    ("list_generic_ellipsis_type", _replace_binding(b"list[...]")),
    (
        "unprojected_literal_call",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1BadLiteral = Literal[evil()]\n\n" + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    (
        "unprojected_literal_set",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1BadLiteral = Literal[{str}]\n\n" + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    (
        "unprojected_annotated_non_field",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1BadAnnotated = Annotated[str, NotField(default=1)]\n\n" + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    (
        "unprojected_annotated_call_default",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1BadAnnotated = Annotated[str, Field(default=evil())]\n\n" + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    (
        "unprojected_annotated_kwargs",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1BadAnnotated = Annotated[str, Field(**{})]\n\n" + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
)

TYPE_POSITION_INVALID_CORPUS = (
    *COLLECTION_TYPE_INVALID_CORPUS,
    *FIELD_TYPE_INVALID_CORPUS,
    *DECLARATION_GRAMMAR_INVALID_CORPUS,
)

DECLARATION_GRAMMAR_VALID_CONTROLS: tuple[tuple[str, Mutation], ...] = (
    (
        "unprojected_literal_name",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1UnprojectedLiteral = Literal[SomeName]\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    (
        "unprojected_annotated_default",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1UnprojectedAnnotated = Annotated[str, Field(default=None)]\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    (
        "unprojected_discriminator_metadata",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1UnprojectedDiscriminator = Annotated[str, Field(discriminator=\"kind\")]\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    (
        "unprojected_literal_signed_tuple_list_data",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1UnprojectedLiteralData = Literal[-1, (+2,), [3]]\n\n" + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
    (
        "unprojected_annotated_signed_tuple_list_data",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1UnprojectedAnnotatedData = Annotated[str, Field(default=[-1, (+2,)])]\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ),
    ),
)


def _replace_protocol_annotation(annotation: bytes) -> Mutation:
    needle = b"    def load_current(self) -> DeploymentAuthorizationTrustSnapshot: ...\n"
    return lambda value: _replace_once(
        value,
        needle,
        b"    def load_current(self, probe: " + annotation + b") -> DeploymentAuthorizationTrustSnapshot: ...\n",
    )


def _replace_protocol_return(annotation: bytes) -> Mutation:
    needle = b"    def load_current(self) -> DeploymentAuthorizationTrustSnapshot: ...\n"
    return lambda value: _replace_once(
        value,
        needle,
        b"    def load_current(self) -> " + annotation + b": ...\n",
    )


PROTOCOL_TYPE_INVALID_CORPUS: tuple[tuple[str, Mutation], ...] = (
    ("protocol_bare_ellipsis_argument", _replace_protocol_annotation(b"...")),
    ("protocol_quoted_ellipsis_argument", _replace_protocol_annotation(b'"..."')),
    ("protocol_collection_extra_arity_argument", _replace_protocol_annotation(b"list[str, int]")),
    ("protocol_field_as_type_argument", _replace_protocol_annotation(b"Field(default=1)")),
    ("protocol_map_missing_value_argument", _replace_protocol_annotation(b"dict[str]")),
    ("protocol_tuple_invalid_ellipsis_argument", _replace_protocol_annotation(b"tuple[..., str]")),
    ("protocol_literal_call_argument", _replace_protocol_annotation(b"Literal[evil()]")),
    ("protocol_literal_set_argument", _replace_protocol_annotation(b"Literal[{str}]")),
    ("protocol_annotated_non_field_argument", _replace_protocol_annotation(b"Annotated[str, NotField(default=1)]")),
    ("protocol_annotated_call_default_argument", _replace_protocol_annotation(b"Annotated[str, Field(default=evil())]")),
    ("protocol_annotated_kwargs_argument", _replace_protocol_annotation(b"Annotated[str, Field(**{})]")),
    ("protocol_bare_ellipsis_return", _replace_protocol_return(b"...")),
    ("protocol_quoted_ellipsis_return", _replace_protocol_return(b'"..."')),
    ("protocol_collection_extra_arity_return", _replace_protocol_return(b"list[str, int]")),
    ("protocol_field_as_type_return", _replace_protocol_return(b"Field(default=1)")),
    ("protocol_map_missing_value_return", _replace_protocol_return(b"dict[str]")),
    ("protocol_tuple_invalid_ellipsis_return", _replace_protocol_return(b"tuple[..., str]")),
    ("protocol_literal_call_return", _replace_protocol_return(b"Literal[evil()]")),
    ("protocol_literal_set_return", _replace_protocol_return(b"Literal[{str}]")),
    ("protocol_annotated_non_field_return", _replace_protocol_return(b"Annotated[str, NotField(default=1)]")),
    ("protocol_annotated_call_default_return", _replace_protocol_return(b"Annotated[str, Field(default=evil())]")),
    ("protocol_annotated_kwargs_return", _replace_protocol_return(b"Annotated[str, Field(**{})]")),
)

PROTOCOL_TYPE_VALID_CONTROLS: tuple[tuple[str, Mutation], ...] = (
    ("protocol_valid_map_argument", _replace_protocol_annotation(b"dict[str, int]")),
    ("protocol_valid_map_return", _replace_protocol_return(b"dict[str, int]")),
    ("protocol_valid_zero_tuple_argument", _replace_protocol_annotation(b"tuple[()]")),
    ("protocol_valid_zero_tuple_return", _replace_protocol_return(b"tuple[()]")),
    ("protocol_valid_literal_argument", _replace_protocol_annotation(b"Literal[SomeName]")),
    ("protocol_valid_literal_return", _replace_protocol_return(b"Literal[SomeName]")),
    ("protocol_valid_annotated_argument", _replace_protocol_annotation(b"Annotated[str, Field(default=None)]")),
    ("protocol_valid_annotated_return", _replace_protocol_return(b"Annotated[str, Field(default=None)]")),
)


def _add_valid_field_default(value: bytes) -> bytes:
    return _replace_once(
        value,
        CANONICAL_ARTIFACT_DECLARATION,
        CANONICAL_ARTIFACT_DECLARATION + b"    layer1_valid_default: int = Field(ge=1)\n",
    )


def test_two_fresh_processes_reproduce_the_complete_frozen_authority(tmp_path: Path) -> None:
    assert _command(DESIGN, REGISTRY, tmp_path / "authority.json")[:2] == list(
        PYTHON312_ISOLATED
    )
    outputs = [tmp_path / "first.json", tmp_path / "second.json"]
    for output in outputs:
        completed = _run(DESIGN, REGISTRY, output)
        assert completed.returncode == 0, completed.stderr

    first = outputs[0].read_bytes()
    assert first == outputs[1].read_bytes()
    assert first == FROZEN_AUTHORITY.read_bytes()
    assert hashlib.sha256(first).hexdigest() == EXPECTED_AUTHORITY_SHA256
    authority = json.loads(first)
    assert len(authority["schemas"]) == 56
    assert len(authority["enum_registry"]["rows"]) == 249
    assert authority["profile"]["digest"] == EXPECTED_PROFILE_DIGEST


def test_v2_profile_scope_uses_behavioral_identity() -> None:
    design = DESIGN.read_text(encoding="utf-8")
    start = design.index("#### 3.23.4.2.1 scenario-first closure-only canonical typed-value profile v2")
    end = design.index("`[SIA-CTV-GRAMMAR-V2-BEGIN]`", start)
    scope = design[start:end]
    assert "Scenario-first closure artifacts" in scope
    assert "scenario-first closure\nauthority" in scope
    assert "C2 artifacts" not in scope
    assert "C2 authority" not in scope


def test_valid_reachable_field_mutation_matches_both_compilers_and_formula_validation(
    tmp_path: Path,
) -> None:
    original = DESIGN.read_bytes()
    needle = (
        b"class CanonicalEncodedArtifact(BaseModel):\n"
        b"    binding: CanonicalTypedValueProfileBinding\n"
    )
    replacement = needle + b"    anti_replay_probe: str\n"
    assert original.count(needle) == 1
    mutated_design = tmp_path / "design.md"
    mutated_design.write_bytes(original.replace(needle, replacement))
    reference_output = tmp_path / "mutated-reference.json"
    design_output = tmp_path / "mutated-design.json"

    reference = _run(mutated_design, REGISTRY, reference_output)
    design = _validator_run(mutated_design, REGISTRY, design_output)
    assert reference.returncode == 0, reference.stderr
    assert design.returncode == 0, design.stderr
    assert reference_output.read_bytes() == design_output.read_bytes()
    baseline = json.loads(FROZEN_AUTHORITY.read_bytes())
    changed = json.loads(reference_output.read_bytes())
    baseline_schema = baseline["schemas"][0]
    changed_schema = changed["schemas"][0]

    assert reference_output.read_bytes() != FROZEN_AUTHORITY.read_bytes()
    assert _authority_formula_errors(changed) == []
    assert changed["profile"] == baseline["profile"]
    assert changed["enum_registry"] == baseline["enum_registry"]
    assert changed_schema["coordinate"] == "CanonicalEncodedArtifact.v1"
    assert len(changed_schema["normalized_graph"]["fields"]) == len(
        baseline_schema["normalized_graph"]["fields"]
    ) + 1
    assert changed_schema["normalized_graph"]["fields"][1]["field_name"] == "anti_replay_probe"
    assert changed_schema["schema_fingerprint"] != baseline_schema["schema_fingerprint"]
    assert changed_schema["binding_digest"] != baseline_schema["binding_digest"]
    assert changed["source_design_sha256"] != baseline["source_design_sha256"]


def test_benign_registry_whitespace_matches_both_compilers_and_changes_only_source_identity(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.json"
    registry.write_bytes(REGISTRY.read_bytes() + b"\n")
    reference_output = tmp_path / "reference.json"
    design_output = tmp_path / "design.json"

    reference = _run(DESIGN, registry, reference_output)
    design = _validator_run(DESIGN, registry, design_output)
    assert reference.returncode == 0, reference.stderr
    assert design.returncode == 0, design.stderr
    assert reference_output.read_bytes() == design_output.read_bytes()

    baseline = json.loads(FROZEN_AUTHORITY.read_bytes())
    changed = json.loads(reference_output.read_bytes())
    expected_registry_sha256 = hashlib.sha256(registry.read_bytes()).hexdigest()
    assert changed["source_registry_sha256"] == expected_registry_sha256
    assert changed["source_registry_sha256"] != baseline["source_registry_sha256"]
    changed_without_identity = copy.deepcopy(changed)
    baseline_without_identity = copy.deepcopy(baseline)
    changed_without_identity.pop("source_registry_sha256")
    baseline_without_identity.pop("source_registry_sha256")
    assert changed_without_identity == baseline_without_identity

    # The independently compiled bytes prove the non-identity fields remain
    # stable; checker execution is covered once by the public PR-gate suite.


@pytest.mark.parametrize("condition", ["empty", "missing", "unreadable"])
def test_invalid_registry_preserves_preexisting_output(
    tmp_path: Path,
    condition: str,
) -> None:
    registry = tmp_path / "registry.json"
    if condition == "empty":
        registry.write_bytes(b"")
    elif condition == "unreadable":
        registry.mkdir()
    output = tmp_path / "authority.json"
    sentinel = b"preexisting-output-must-survive\n"
    output.write_bytes(sentinel)

    completed = _run(DESIGN, registry, output)
    assert completed.returncode != 0
    assert output.read_bytes() == sentinel
    assert not list(tmp_path.glob(".authority.json.*.tmp"))


def test_invalid_input_preserves_preexisting_output_atomically(tmp_path: Path) -> None:
    invalid_design = tmp_path / "design.md"
    design = DESIGN.read_bytes()
    needle = b"profile_version=2\n"
    assert design.count(needle) == 1
    invalid_design.write_bytes(design.replace(needle, b"profile_version=3\n"))
    output = tmp_path / "authority.json"
    sentinel = b"preexisting-output-must-survive\n"
    output.write_bytes(sentinel)

    completed = _run(invalid_design, REGISTRY, output)
    assert completed.returncode != 0
    assert output.read_bytes() == sentinel
    assert not list(tmp_path.glob(".authority.json.*.tmp"))


def test_compiler_has_only_stdlib_imports_and_no_forbidden_dependency() -> None:
    source = COMPILER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            imports.add((node.module or "").split(".", 1)[0])
    assert imports <= {
        "__future__",
        "argparse",
        "ast",
        "base64",
        "dataclasses",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "typing",
    }
    forbidden = (
        "validate_ctv_binding_authority_v2",
        "check_ctv_binding_authority_v2",
        "ctv-binding-authority-v2.json",
        "traceability_golden_vectors",
        "memorii.core",
    )
    assert not any(token in source for token in forbidden)


def test_isolated_runtime_succeeds_without_validator_or_checked_authority(tmp_path: Path) -> None:
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    compiler = isolated / "compiler.py"
    design = isolated / "design.md"
    registry = isolated / "registry.json"
    output = isolated / "output.json"
    bootstrap = tmp_path / "audit_bootstrap.py"
    bootstrap.write_text(AUDIT_BOOTSTRAP, encoding="ascii")
    shutil.copyfile(COMPILER, compiler)
    shutil.copyfile(DESIGN, design)
    shutil.copyfile(REGISTRY, registry)

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(bootstrap),
            str(compiler),
            str(design),
            str(registry),
            str(output),
        ],
        cwd=isolated,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "101",
            "PYTHONNOUSERSITE": "1",
        },
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert set(path.name for path in isolated.iterdir()) == {
        "compiler.py",
        "design.md",
        "registry.json",
        "output.json",
    }
    assert hashlib.sha256(output.read_bytes()).hexdigest() == EXPECTED_AUTHORITY_SHA256


@pytest.mark.parametrize(("label", "mutation"), INVALID_DESIGN_CORPUS, ids=[item[0] for item in INVALID_DESIGN_CORPUS])
def test_hand_authored_invalid_corpus_has_equivalent_fail_closed_verdicts(
    tmp_path: Path,
    label: str,
    mutation: Mutation,
) -> None:
    invalid = tmp_path / f"{label}.md"
    invalid.write_bytes(mutation(DESIGN.read_bytes()))
    reference_output = tmp_path / f"{label}.reference.json"
    design_output = tmp_path / f"{label}.design.json"

    reference = _run(invalid, REGISTRY, reference_output)
    design = _validator_run(invalid, REGISTRY, design_output)

    assert reference.returncode != 0, f"reference accepted {label}: {reference.stdout}"
    assert design.returncode != 0, f"design validator accepted {label}: {design.stdout}"
    assert not reference_output.exists()
    assert not design_output.exists()


@pytest.mark.parametrize(
    ("label", "mutation"),
    TYPE_POSITION_INVALID_CORPUS,
    ids=[item[0] for item in TYPE_POSITION_INVALID_CORPUS],
)
def test_collection_type_corpus_has_equivalent_fail_closed_verdicts(
    tmp_path: Path,
    label: str,
    mutation: Mutation,
) -> None:
    invalid = tmp_path / f"{label}.md"
    invalid.write_bytes(mutation(DESIGN.read_bytes()))
    reference_output = tmp_path / f"{label}.reference.json"
    design_output = tmp_path / f"{label}.design.json"
    reference = _run(invalid, REGISTRY, reference_output)
    design = _validator_run(invalid, REGISTRY, design_output)
    assert reference.returncode != 0, f"reference accepted {label}: {reference.stdout}"
    assert design.returncode != 0, f"design validator accepted {label}: {design.stdout}"
    assert not reference_output.exists()
    assert not design_output.exists()


@pytest.mark.parametrize(
    ("label", "mutation"),
    TYPE_POSITION_INVALID_CORPUS,
    ids=[item[0] for item in TYPE_POSITION_INVALID_CORPUS],
)
@pytest.mark.parametrize("preseeded", [False, True], ids=["absent", "preseeded"])
def test_public_validator_write_preserves_targets_for_invalid_collection_type_inputs(
    tmp_path: Path,
    label: str,
    mutation: Mutation,
    preseeded: bool,
) -> None:
    invalid = tmp_path / f"{label}.md"
    invalid.write_bytes(mutation(DESIGN.read_bytes()))
    output = tmp_path / "authority.json"
    sentinel = b"preseeded-authority-must-survive\n"
    expected_mode = 0o640
    if preseeded:
        output.write_bytes(sentinel)
        output.chmod(expected_mode)

    completed = _validator_run(invalid, REGISTRY, output)

    assert completed.returncode != 0, f"validator accepted {label}: {completed.stdout}"
    if preseeded:
        assert output.read_bytes() == sentinel
        assert output.stat().st_mode & 0o7777 == expected_mode
    else:
        assert not output.exists()
    assert not list(tmp_path.glob(".authority.json.*.tmp"))


@pytest.mark.parametrize(
    ("label", "mutation"),
    (*COLLECTION_TYPE_VALID_CONTROLS, *DECLARATION_GRAMMAR_VALID_CONTROLS),
    ids=[
        item[0]
        for item in (*COLLECTION_TYPE_VALID_CONTROLS, *DECLARATION_GRAMMAR_VALID_CONTROLS)
    ],
)
def test_public_validator_write_publishes_exact_checked_authority_for_valid_declaration_controls(
    tmp_path: Path,
    label: str,
    mutation: Mutation,
) -> None:
    design = tmp_path / f"{label}.md"
    design.write_bytes(mutation(DESIGN.read_bytes()))
    reference_output = tmp_path / f"{label}.reference.json"
    checked_output = tmp_path / f"{label}.checked.json"

    reference = _run(design, REGISTRY, reference_output)
    validator = _validator_run(design, REGISTRY, checked_output)

    assert reference.returncode == 0, reference.stderr
    assert validator.returncode == 0, validator.stderr
    assert checked_output.read_bytes() == reference_output.read_bytes()
    assert not list(tmp_path.glob(f".{checked_output.name}.*.tmp"))


PROJECTED_NON_STRING_MAPS: tuple[tuple[str, Mutation], ...] = (
    ("direct_int_key", _replace_binding(b"dict[int, str]")),
    ("whole_quoted_bool_key", _replace_binding(b'"dict[bool, str]"')),
    ("nested_int_key", _replace_binding(b"tuple[dict[int, str], ...]")),
    (
        "reachable_alias_int_key",
        lambda value: _replace_once(
            value,
            CANONICAL_ARTIFACT_DECLARATION,
            b"Layer1ProjectedBadMap = dict[int, str]\n\n"
            + CANONICAL_ARTIFACT_DECLARATION,
        ).replace(
            CANONICAL_ARTIFACT_DECLARATION,
            b"class CanonicalEncodedArtifact(BaseModel):\n"
            b"    binding: Layer1ProjectedBadMap\n"
            b"    canonical_value_bytes: bytes\n",
            1,
        ),
    ),
    ("inherited_bool_key", _replace_with_inherited_binding(b"dict[bool, str]")),
)


@pytest.mark.parametrize(
    ("label", "mutation"),
    PROJECTED_NON_STRING_MAPS,
    ids=[item[0] for item in PROJECTED_NON_STRING_MAPS],
)
@pytest.mark.parametrize("preseeded", [False, True], ids=["absent", "preseeded"])
def test_projected_non_string_map_keys_fail_closed_in_both_public_compilers(
    tmp_path: Path, label: str, mutation: Mutation, preseeded: bool
) -> None:
    design = tmp_path / f"{label}.md"
    design.write_bytes(mutation(DESIGN.read_bytes()))
    reference_output = tmp_path / "reference.json"
    checked_output = tmp_path / "checked.json"
    sentinel = b"preserve-projected-map-output\n"
    if preseeded:
        checked_output.write_bytes(sentinel)
        checked_output.chmod(0o640)
    assert _run(design, REGISTRY, reference_output).returncode != 0
    assert _validator_run(design, REGISTRY, checked_output).returncode != 0
    assert not reference_output.exists()
    if preseeded:
        assert checked_output.read_bytes() == sentinel
        assert checked_output.stat().st_mode & 0o7777 == 0o640
    else:
        assert not checked_output.exists()
    assert not list(tmp_path.glob(".checked.json.*.tmp"))


@pytest.mark.parametrize(
    ("label", "mutation"),
    (
        ("unprojected_non_string_map", lambda value: _replace_once(value, CANONICAL_ARTIFACT_DECLARATION, b"Layer1UnprojectedNonStringMap = dict[int, str]\n\n" + CANONICAL_ARTIFACT_DECLARATION)),
        ("protocol_non_string_map", _replace_protocol_annotation(b"dict[int, str]")),
    ),
)
def test_non_string_maps_outside_ctv_projection_remain_accepted(
    tmp_path: Path, label: str, mutation: Mutation
) -> None:
    design = tmp_path / f"{label}.md"
    design.write_bytes(mutation(DESIGN.read_bytes()))
    reference_output = tmp_path / "reference.json"
    checked_output = tmp_path / "checked.json"
    assert _run(design, REGISTRY, reference_output).returncode == 0
    assert _validator_run(design, REGISTRY, checked_output).returncode == 0
    assert checked_output.read_bytes() == reference_output.read_bytes()
    authority = json.loads(reference_output.read_bytes())
    baseline = json.loads(FROZEN_AUTHORITY.read_bytes())
    assert authority["source_design_sha256"] != baseline["source_design_sha256"]
    authority.pop("source_design_sha256")
    baseline.pop("source_design_sha256")
    assert authority == baseline


ZERO_TUPLE_CONTROLS: tuple[tuple[str, Mutation, bool], ...] = (
    ("direct", _replace_binding(b"tuple[()]"), True),
    ("whole_quoted", _replace_binding(b'"tuple[()]"'), True),
    ("nested", _replace_binding(b"tuple[tuple[()], ...]"), True),
    ("reachable_alias", lambda value: _replace_once(value, CANONICAL_ARTIFACT_DECLARATION, b"Layer1ZeroTuple = tuple[()]\n\n" + CANONICAL_ARTIFACT_DECLARATION).replace(CANONICAL_ARTIFACT_DECLARATION, b"class CanonicalEncodedArtifact(BaseModel):\n    binding: Layer1ZeroTuple\n    canonical_value_bytes: bytes\n", 1), True),
    ("inherited", _replace_with_inherited_binding(b"tuple[()]"), True),
    ("unprojected", lambda value: _replace_once(value, CANONICAL_ARTIFACT_DECLARATION, b"Layer1UnprojectedZeroTuple = tuple[()]\n\n" + CANONICAL_ARTIFACT_DECLARATION), False),
)


@pytest.mark.parametrize(
    ("label", "mutation", "projected"), ZERO_TUPLE_CONTROLS, ids=[item[0] for item in ZERO_TUPLE_CONTROLS]
)
def test_zero_item_tuple_forms_have_paired_public_equivalence(
    tmp_path: Path, label: str, mutation: Mutation, projected: bool
) -> None:
    design = tmp_path / f"{label}.md"
    design.write_bytes(mutation(DESIGN.read_bytes()))
    reference_output = tmp_path / "reference.json"
    checked_output = tmp_path / "checked.json"
    assert _run(design, REGISTRY, reference_output).returncode == 0
    assert _validator_run(design, REGISTRY, checked_output).returncode == 0
    assert checked_output.read_bytes() == reference_output.read_bytes()
    if not projected:
        authority = json.loads(reference_output.read_bytes())
        baseline = json.loads(FROZEN_AUTHORITY.read_bytes())
        assert authority["source_design_sha256"] != baseline["source_design_sha256"]
        authority.pop("source_design_sha256")
        baseline.pop("source_design_sha256")
        assert authority == baseline
        return
    graph = json.loads(reference_output.read_bytes())["schemas"][0]["normalized_graph"]
    annotation = next(field["annotation"] for field in graph["fields"] if field["field_name"] == "binding")
    if label == "nested":
        annotation = annotation["items"][0]
    assert annotation == {"items": [], "kind": "collection", "name": "tuple", "variadic": False}


@pytest.mark.parametrize(
    ("label", "mutation"),
    PROTOCOL_TYPE_INVALID_CORPUS,
    ids=[item[0] for item in PROTOCOL_TYPE_INVALID_CORPUS],
)
@pytest.mark.parametrize("preseeded", [False, True], ids=["absent", "preseeded"])
def test_public_protocol_type_failures_are_paired_and_atomic(
    tmp_path: Path,
    label: str,
    mutation: Mutation,
    preseeded: bool,
) -> None:
    invalid = tmp_path / f"{label}.md"
    invalid.write_bytes(mutation(DESIGN.read_bytes()))
    reference_output = tmp_path / "reference.json"
    checked_output = tmp_path / "checked.json"
    sentinel = b"preseeded-authority-must-survive\n"
    if preseeded:
        checked_output.write_bytes(sentinel)
        checked_output.chmod(0o640)

    reference = _run(invalid, REGISTRY, reference_output)
    validator = _validator_run(invalid, REGISTRY, checked_output)

    assert reference.returncode != 0, f"reference accepted {label}: {reference.stdout}"
    assert validator.returncode != 0, f"validator accepted {label}: {validator.stdout}"
    assert not reference_output.exists()
    if preseeded:
        assert checked_output.read_bytes() == sentinel
        assert checked_output.stat().st_mode & 0o7777 == 0o640
    else:
        assert not checked_output.exists()
    assert not list(tmp_path.glob(".checked.json.*.tmp"))


@pytest.mark.parametrize(
    ("label", "mutation"),
    PROTOCOL_TYPE_VALID_CONTROLS,
    ids=[item[0] for item in PROTOCOL_TYPE_VALID_CONTROLS],
)
def test_public_protocol_valid_type_controls_publish_exact_matching_bytes(
    tmp_path: Path,
    label: str,
    mutation: Mutation,
) -> None:
    design = tmp_path / f"{label}.md"
    design.write_bytes(mutation(DESIGN.read_bytes()))
    reference_output = tmp_path / "reference.json"
    checked_output = tmp_path / "checked.json"
    reference = _run(design, REGISTRY, reference_output)
    validator = _validator_run(design, REGISTRY, checked_output)
    assert reference.returncode == 0, reference.stderr
    assert validator.returncode == 0, validator.stderr
    assert checked_output.read_bytes() == reference_output.read_bytes()


@pytest.mark.parametrize(
    ("label", "mutation"),
    (("valid_model_field_default", _add_valid_field_default),),
)
def test_valid_model_field_default_and_generation_metadata_remain_accepted(
    tmp_path: Path,
    label: str,
    mutation: Mutation,
) -> None:
    design = tmp_path / f"{label}.md"
    design.write_bytes(mutation(DESIGN.read_bytes()))
    reference_output = tmp_path / "reference.json"
    checked_output = tmp_path / "checked.json"

    reference = _run(design, REGISTRY, reference_output)
    validator = _validator_run(design, REGISTRY, checked_output)

    assert reference.returncode == 0, reference.stderr
    assert validator.returncode == 0, validator.stderr
    assert checked_output.read_bytes() == reference_output.read_bytes()


@pytest.mark.parametrize(
    ("initial", "mode"),
    ((None, 0o644), (b"old-authority\n", 0o640), (b"old-authority\n", 0o600)),
    ids=("absent", "preseeded-0640", "preseeded-0600"),
)
def test_public_validator_write_success_preserves_mode_contract(
    tmp_path: Path,
    initial: bytes | None,
    mode: int,
) -> None:
    output = tmp_path / "authority.json"
    if initial is not None:
        output.write_bytes(initial)
        output.chmod(mode)
    expected = tmp_path / "expected.json"
    reference = _run(DESIGN, REGISTRY, expected)
    completed = _validator_run(DESIGN, REGISTRY, output)

    assert reference.returncode == 0, reference.stderr
    assert completed.returncode == 0, completed.stderr
    assert output.read_bytes() == expected.read_bytes()
    assert output.stat().st_mode & 0o7777 == mode
    assert not list(tmp_path.glob(".authority.json.*.tmp"))


def test_valid_enum_mutation_recomputes_profile_fingerprints_and_bindings_in_both_compilers() -> None:
    with tempfile.TemporaryDirectory(prefix="ctv-round5-") as temporary:
        root = Path(temporary)
        design = root / "design.md"
        design.write_bytes(_valid_enum_mutation(DESIGN.read_bytes()))
        reference_output = root / "reference.json"
        design_output = root / "design.json"
        reference = _run(design, REGISTRY, reference_output)
        design_result = _validator_run(design, REGISTRY, design_output)
        assert reference.returncode == 0, reference.stderr
        assert design_result.returncode == 0, design_result.stderr
        assert reference_output.read_bytes() == design_output.read_bytes()

        baseline = json.loads(FROZEN_AUTHORITY.read_bytes())
        changed = json.loads(reference_output.read_bytes())
        assert changed["enum_registry"]["digest"] != baseline["enum_registry"]["digest"]
        assert changed["profile"]["digest"] != baseline["profile"]["digest"]
        pairs = list(zip(changed["schemas"], baseline["schemas"], strict=True))
        fingerprint_equalities = [
            changed_schema["schema_fingerprint"] == baseline_schema["schema_fingerprint"]
            for changed_schema, baseline_schema in pairs
        ]
        assert any(fingerprint_equalities)
        assert not all(fingerprint_equalities)
        assert all(
            changed_schema["binding_digest"] != baseline_schema["binding_digest"]
            for changed_schema, baseline_schema in pairs
        )


def test_v1_only_change_is_compatible_but_v1_v2_substitution_rejects(tmp_path: Path) -> None:
    baseline_output = tmp_path / "baseline.json"
    baseline_checked = tmp_path / "baseline.checked.json"
    assert _run(DESIGN, REGISTRY, baseline_output).returncode == 0
    assert _validator_run(DESIGN, REGISTRY, baseline_checked).returncode == 0
    assert baseline_checked.read_bytes() == baseline_output.read_bytes()

    v1_document = DESIGN.read_bytes()
    v1_payload = _marked_payload(v1_document, "SIA-CTV-ENUM-REGISTRY-V1", "json")
    v1_changed = tmp_path / "v1-only.md"
    v1_changed.write_bytes(
        _replace_marked(
            v1_document,
            "SIA-CTV-ENUM-REGISTRY-V1",
            "json",
            v1_payload.replace(b"\n", b"\n ", 1),
        )
    )
    v1_output = tmp_path / "v1-only.json"
    v1_checked = tmp_path / "v1-only.checked.json"
    assert _run(v1_changed, REGISTRY, v1_output).returncode == 0
    assert _validator_run(v1_changed, REGISTRY, v1_checked).returncode == 0
    assert v1_output.read_bytes() == baseline_output.read_bytes()
    assert v1_checked.read_bytes() == v1_output.read_bytes()
    assert _expected_v2_source_design_sha256(v1_changed.read_bytes()) == _expected_v2_source_design_sha256(v1_document)
    assert json.loads(v1_output.read_bytes())["source_design_sha256"] == _expected_v2_source_design_sha256(v1_changed.read_bytes())

    substituted = tmp_path / "substituted.md"
    substituted.write_bytes(
        _replace_once(
            DESIGN.read_bytes(),
            b"`[SIA-CTV-GRAMMAR-V2-BEGIN]`",
            b"`[SIA-CTV-GRAMMAR-V1-BEGIN]`",
        )
    )
    output = tmp_path / "substituted.json"
    checked_output = tmp_path / "substituted.checked.json"
    sentinel = b"substituted-output-must-survive\n"
    for target in (output, checked_output):
        target.write_bytes(sentinel)
        target.chmod(0o640)
    assert _run(substituted, REGISTRY, output).returncode != 0
    assert _validator_run(substituted, REGISTRY, checked_output).returncode != 0
    for target in (output, checked_output):
        assert target.read_bytes() == sentinel
        assert target.stat().st_mode & 0o7777 == 0o640
        assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


@pytest.mark.parametrize(
    ("label", "mutation"),
    (
        (
            "inline_begin_before_authority",
            lambda document: document.replace(
                b"`[SIA-CTV-ENUM-REGISTRY-V1-BEGIN]`\n```json\n",
                b"non-authority prose `[SIA-CTV-ENUM-REGISTRY-V1-BEGIN]`\n```json\n"
                b"still non-authority prose\n"
                b"`[SIA-CTV-ENUM-REGISTRY-V1-BEGIN]`\n```json\n",
                1,
            ),
        ),
        (
            "inline_close_after_authority",
            lambda document: document.replace(
                b"```\n`[SIA-CTV-ENUM-REGISTRY-V1-END]`",
                b"```\n`[SIA-CTV-ENUM-REGISTRY-V1-END]`\n"
                b"non-authority prose ```\n`[SIA-CTV-ENUM-REGISTRY-V1-END]`",
                1,
            ),
        ),
    ),
)
def test_marker_shaped_non_authority_prose_preserves_public_compiler_parity(
    tmp_path: Path,
    label: str,
    mutation: Mutation,
) -> None:
    mutated_bytes = mutation(DESIGN.read_bytes())
    design = tmp_path / f"{label}.md"
    design.write_bytes(mutated_bytes)
    reference_output = tmp_path / f"{label}.reference.json"
    checked_output = tmp_path / f"{label}.checked.json"

    reference = _run(design, REGISTRY, reference_output)
    validator = _validator_run(design, REGISTRY, checked_output)

    assert reference.returncode == 0, reference.stderr
    assert validator.returncode == 0, validator.stderr
    assert reference_output.read_bytes() == checked_output.read_bytes()

    authority = json.loads(reference_output.read_bytes())
    assert authority["source_design_sha256"] == _expected_v2_source_design_sha256(
        mutated_bytes
    )


@pytest.mark.parametrize(
    ("label", "mutation"),
    (
        (
            "orphan_close_after_block",
            lambda document: document.replace(
                b"```\n`[SIA-CTV-ENUM-REGISTRY-V1-END]`",
                b"```\n`[SIA-CTV-ENUM-REGISTRY-V1-END]`\n"
                b"```\n`[SIA-CTV-ENUM-REGISTRY-V1-END]`",
                1,
            ),
        ),
        (
            "orphan_begin_after_block",
            lambda document: document.replace(
                b"```\n`[SIA-CTV-ENUM-REGISTRY-V1-END]`",
                b"```\n`[SIA-CTV-ENUM-REGISTRY-V1-END]`\n"
                b"`[SIA-CTV-ENUM-REGISTRY-V1-BEGIN]`\n```json\n"
                b"orphan authority candidate without a close\n",
                1,
            ),
        ),
        (
            "invalid_suffix_close_before_valid_close",
            lambda document: document.replace(
                b"`[SIA-CTV-ENUM-REGISTRY-V1-BEGIN]`\n```json\n",
                b"`[SIA-CTV-ENUM-REGISTRY-V1-BEGIN]`\n```json\n"
                b"```\n`[SIA-CTV-ENUM-REGISTRY-V1-END]`not-an-end\n",
                1,
            ),
        ),
    ),
)
def test_incomplete_v1_marker_candidates_do_not_change_complete_block_selection(
    tmp_path: Path,
    label: str,
    mutation: Mutation,
) -> None:
    mutated_bytes = mutation(DESIGN.read_bytes())
    design = tmp_path / f"{label}.md"
    design.write_bytes(mutated_bytes)
    reference_output = tmp_path / f"{label}.reference.json"
    checked_output = tmp_path / f"{label}.checked.json"

    reference = _run(design, REGISTRY, reference_output)
    validator = _validator_run(design, REGISTRY, checked_output)

    assert reference.returncode == 0, reference.stderr
    assert validator.returncode == 0, validator.stderr
    assert reference_output.read_bytes() == checked_output.read_bytes()
    authority = json.loads(reference_output.read_bytes())
    assert authority["source_design_sha256"] == _expected_v2_source_design_sha256(
        mutated_bytes
    )


def test_two_complete_v1_blocks_fail_closed_in_both_public_compilers(
    tmp_path: Path,
) -> None:
    document = DESIGN.read_bytes()
    complete_block = (
        b"`[SIA-CTV-ENUM-REGISTRY-V1-BEGIN]`\n```json\n"
        + _marked_payload(document, "SIA-CTV-ENUM-REGISTRY-V1", "json")
        + b"```\n`[SIA-CTV-ENUM-REGISTRY-V1-END]`"
    )
    duplicated = tmp_path / "two-complete-v1-blocks.md"
    duplicated.write_bytes(document + b"\n" + complete_block + b"\n")
    reference_output = tmp_path / "two-complete-v1-blocks.reference.json"
    checked_output = tmp_path / "two-complete-v1-blocks.checked.json"

    reference = _run(duplicated, REGISTRY, reference_output)
    validator = _validator_run(duplicated, REGISTRY, checked_output)

    assert reference.returncode != 0, reference.stdout
    assert validator.returncode != 0, validator.stdout
    assert not reference_output.exists()
    assert not checked_output.exists()


@pytest.mark.parametrize(
    ("marker", "language"),
    (
        ("SIA-CTV-GRAMMAR-V2", "text"),
        ("SIA-TRACEABILITY-SCHEMA-INVENTORY-V1", "text"),
        ("SIA-CTV-ENUM-REGISTRY-V2", "json"),
        ("SIA-CTV-ENUM-REGISTRY-V1", "json"),
    ),
)
@pytest.mark.parametrize("preseeded", [False, True], ids=("absent", "preseeded"))
def test_public_marked_block_family_parity_and_atomicity(
    tmp_path: Path, marker: str, language: str, preseeded: bool
) -> None:
    """Every public authority marker is paired with the independent oracle.

    A valid document must produce byte-identical authority, while a malformed
    or duplicated closed block must reject without replacing a pre-existing
    validator target.
    """
    valid = tmp_path / f"{marker}.valid.md"
    valid.write_bytes(DESIGN.read_bytes())
    reference = tmp_path / "reference.json"
    checked = tmp_path / "checked.json"
    assert _run(valid, REGISTRY, reference).returncode == 0
    assert _validator_run(valid, REGISTRY, checked).returncode == 0
    assert checked.read_bytes() == reference.read_bytes()
    authority = json.loads(reference.read_bytes())
    assert _authority_formula_errors(authority) == []
    payload = _marked_payload(DESIGN.read_bytes(), marker, language)
    if marker == "SIA-CTV-GRAMMAR-V2":
        grammar = authority["grammar"]
        preimage = b"memorii:sia-ctv-grammar:v2\0" + payload
        assert grammar["payload"].encode() == payload
        assert base64.b64decode(grammar["payload_base64"], validate=True) == payload
        assert base64.b64decode(grammar["digest_preimage_base64"], validate=True) == preimage
        assert hashlib.sha256(preimage).hexdigest() == grammar["digest"]
        enum_registry = authority["enum_registry"]
        enum_bytes = base64.b64decode(enum_registry["canonical_bytes_base64"], validate=True)
        profile_preimage = b"".join((b"memorii:sia-ctv-profile:v2\0", _lp("semantic_ingestion_typed_value"), _lp("2"), _lp(grammar["revision"]), _lp(grammar["digest"]), _lp(payload), _lp("sia-ctv-enum-registry-v2"), _lp(enum_registry["digest"]), _lp(enum_bytes)))
        assert base64.b64decode(authority["profile"]["preimage_base64"], validate=True) == profile_preimage
        assert hashlib.sha256(profile_preimage).hexdigest() == authority["profile"]["digest"]
    elif marker == "SIA-TRACEABILITY-SCHEMA-INVENTORY-V1":
        coordinates = tuple(line.strip() for line in payload.decode("ascii", "strict").splitlines() if line.strip())
        assert len(coordinates) == 56
        assert len(set(coordinates)) == 56
        assert coordinates == tuple(sorted(coordinates))
        assert all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]+", coordinate) for coordinate in coordinates)
        assert tuple(authority["inventory"]) == coordinates
        assert tuple(item["coordinate"] for item in authority["schemas"]) == coordinates
    elif marker == "SIA-CTV-ENUM-REGISTRY-V2":
        rows = json.loads(payload)
        enum_registry = authority["enum_registry"]
        canonical = _canonical(rows)
        preimage = b"memorii:sia-ctv-enum-registry:v2\0" + canonical
        assert enum_registry["rows"] == rows
        assert base64.b64decode(enum_registry["canonical_bytes_base64"], validate=True) == canonical
        assert base64.b64decode(enum_registry["digest_preimage_base64"], validate=True) == preimage
        assert hashlib.sha256(preimage).hexdigest() == enum_registry["digest"]
        assert _authority_formula_errors(authority) == []
    else:
        # V1 is retained as redacted source material; it is not parsed as V2.
        assert json.loads(payload)
        assert authority["source_design_sha256"] == _expected_v2_source_design_sha256(DESIGN.read_bytes())

    complete = f"`[{marker}-BEGIN]`\n```{language}\n".encode() + payload + f"```\n`[{marker}-END]`\n".encode()
    invalid_cases: list[tuple[str, bytes]] = [
        ("malformed", DESIGN.read_bytes().replace(f"`[{marker}-BEGIN]`".encode(), f"`[{marker}-MISSING]`".encode(), 1)),
        ("duplicate", DESIGN.read_bytes() + b"\n" + complete),
    ]
    if marker != "SIA-CTV-ENUM-REGISTRY-V1":
        invalid_payload = b"{}\n" if language == "json" else b"not-an-authority-payload\n"
        invalid_cases.append(("invalid_payload", _replace_marked(DESIGN.read_bytes(), marker, language, invalid_payload)))
    for label, invalid_bytes in invalid_cases:
        invalid = tmp_path / f"{marker}.{label}.md"
        invalid.write_bytes(invalid_bytes)
        reference_output = tmp_path / f"{label}.reference.json"
        checked_output = tmp_path / f"{label}.checked.json"
        sentinel = b"authority-target-must-survive\n"
        if preseeded:
            checked_output.write_bytes(sentinel)
            checked_output.chmod(0o640)
        assert _run(invalid, REGISTRY, reference_output).returncode != 0
        assert _validator_run(invalid, REGISTRY, checked_output).returncode != 0
        assert not reference_output.exists()
        if preseeded:
            assert checked_output.read_bytes() == sentinel
            assert checked_output.stat().st_mode & 0o7777 == 0o640
        else:
            assert not checked_output.exists()
        assert not list(tmp_path.glob(f".{checked_output.name}.*.tmp"))


def test_determinism_is_independent_of_cwd_hash_seed_timezone_locale_and_umask(tmp_path: Path) -> None:
    outputs: list[bytes] = []
    settings = (
        ("1", "UTC", "C", 0o022),
        ("987654", "America/Chicago", "C", 0o077),
    )
    for index, (seed, timezone, locale, mask) in enumerate(settings):
        directory = tmp_path / f"run-{index}"
        directory.mkdir()
        output = directory / "authority.json"
        wrapper = directory / "runner.py"
        wrapper.write_text(
            "import os, runpy, sys\n"
            f"os.umask({mask})\n"
            f"sys.argv = [{str(COMPILER)!r}, '--design', {str(DESIGN)!r}, "
            f"'--registry', {str(REGISTRY)!r}, '--output', {str(output)!r}]\n"
            f"runpy.run_path({str(COMPILER)!r}, run_name='__main__')\n",
            encoding="ascii",
        )
        completed = subprocess.run(
            [sys.executable, "-I", str(wrapper)],
            cwd=directory,
            env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONHASHSEED": seed,
                "PYTHONNOUSERSITE": "1",
                "TZ": timezone,
                "LC_ALL": locale,
            },
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        outputs.append(output.read_bytes())
    assert outputs[0] == outputs[1] == FROZEN_AUTHORITY.read_bytes()


def _lp(value: str | bytes) -> bytes:
    encoded = value if isinstance(value, bytes) else value.encode("ascii")
    return len(encoded).to_bytes(8, "big") + encoded


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"


def _authority_formula_errors(authority: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    profile = authority["profile"]
    profile_preimage = base64.b64decode(profile["preimage_base64"], validate=True)
    grammar = authority["grammar"]
    grammar_payload = grammar["payload"].encode("ascii")
    grammar_preimage = b"memorii:sia-ctv-grammar:v2\0" + grammar_payload
    enum_registry = authority["enum_registry"]
    enum_bytes = base64.b64decode(enum_registry["canonical_bytes_base64"], validate=True)
    enum_preimage = b"memorii:sia-ctv-enum-registry:v2\0" + enum_bytes
    expected_profile_preimage = b"".join((b"memorii:sia-ctv-profile:v2\0", _lp(profile["id"]), _lp(str(profile["version"])), _lp(grammar["revision"]), _lp(grammar["digest"]), _lp(grammar_payload), _lp("sia-ctv-enum-registry-v2"), _lp(enum_registry["digest"]), _lp(enum_bytes)))
    if (base64.b64decode(grammar["digest_preimage_base64"], validate=True) != grammar_preimage or hashlib.sha256(grammar_preimage).hexdigest() != grammar["digest"]):
        errors.append("grammar")
    if (base64.b64decode(enum_registry["digest_preimage_base64"], validate=True) != enum_preimage or hashlib.sha256(enum_preimage).hexdigest() != enum_registry["digest"]):
        errors.append("enum")
    if profile_preimage != expected_profile_preimage or hashlib.sha256(profile_preimage).hexdigest() != profile["digest"]:
        errors.append("profile")
    for schema in authority["schemas"]:
        graph_bytes = _canonical(schema["normalized_graph"])
        if base64.b64decode(schema["normalized_graph_bytes_base64"], validate=True) != graph_bytes:
            errors.append(f"{schema['coordinate']}:graph")
        fingerprint_preimage = (
            b"memorii:sia-ctv-schema-fingerprint:v2\0"
            + _lp(schema["coordinate"])
            + _lp(graph_bytes)
        )
        if (
            base64.b64decode(schema["schema_fingerprint_preimage_base64"], validate=True)
            != fingerprint_preimage
            or hashlib.sha256(fingerprint_preimage).hexdigest() != schema["schema_fingerprint"]
        ):
            errors.append(f"{schema['coordinate']}:fingerprint")
        binding_preimage = (
            b"memorii:sia-ctv-binding:v2\0"
            + _lp(profile["id"])
            + _lp(str(profile["version"]))
            + _lp(profile["digest"])
            + _lp(schema["coordinate"])
            + _lp("1")
            + _lp(schema["schema_fingerprint"])
        )
        if (
            base64.b64decode(schema["binding_preimage_base64"], validate=True)
            != binding_preimage
            or hashlib.sha256(binding_preimage).hexdigest() != schema["binding_digest"]
        ):
            errors.append(f"{schema['coordinate']}:binding")
    return errors


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("profile", "profile"),
        ("graph", ":graph"),
        ("fingerprint", ":fingerprint"),
        ("binding", ":binding"),
    ],
)
def test_public_authority_formula_matrix_detects_profile_graph_fingerprint_and_binding_tamper(
    field: str,
    expected: str,
) -> None:
    authority = json.loads(FROZEN_AUTHORITY.read_bytes())
    assert _authority_formula_errors(authority) == []
    tampered = copy.deepcopy(authority)
    if field == "profile":
        tampered["profile"]["digest"] = "0" * 64
    elif field == "graph":
        tampered["schemas"][0]["normalized_graph"]["fields"][0]["field_name"] = "tampered"
    elif field == "fingerprint":
        tampered["schemas"][0]["schema_fingerprint"] = "0" * 64
    else:
        tampered["schemas"][0]["binding_digest"] = "0" * 64
    assert any(expected in error for error in _authority_formula_errors(tampered))


def test_unicode_scalar_json_is_utf8_and_surrogate_enum_rejects_atomically(tmp_path: Path) -> None:
    def unicode_design(value: str) -> bytes:
        changed = _replace_once(
            DESIGN.read_bytes(),
            b'    execution_status: Literal["not_executed", "executed", "cancelled", "error"]\n'
            b'    execution_result: Literal["pass", "fail", "indeterminate"]\n',
            b'    execution_status: Literal["not_executed", "executed", "cancelled", "error"]\n'
            + b'    execution_result: Literal["pass", "fail", "'
            + value.encode("utf-8")
            + b'"]\n',
        )
        rows = json.loads(_marked_payload(changed, "SIA-CTV-ENUM-REGISTRY-V2", "json"))
        rows["NormativeExecutionEvidenceRecordBody.execution_result"] = ["pass", "fail", value]
        return _replace_marked(
            changed,
            "SIA-CTV-ENUM-REGISTRY-V2",
            "json",
            json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
        )

    outputs: dict[str, bytes] = {}
    for label, value in (("composed", "caf\u00e9"), ("decomposed", "cafe\u0301")):
        design = tmp_path / f"{label}.md"
        design.write_bytes(unicode_design(value))
        output = tmp_path / f"{label}.reference.json"
        checked_output = tmp_path / f"{label}.checked.json"
        completed = _run(design, REGISTRY, output)
        validator = _validator_run(design, REGISTRY, checked_output)
        assert completed.returncode == 0, completed.stderr
        assert validator.returncode == 0, validator.stderr
        assert checked_output.read_bytes() == output.read_bytes()
        assert value.encode("utf-8") in output.read_bytes()
        outputs[label] = output.read_bytes()
    assert outputs["composed"] != outputs["decomposed"]

    composed = unicode_design("caf\u00e9")
    invalid_declaration = _replace_once(
        composed,
        '    execution_result: Literal["pass", "fail", "caf\u00e9"]\n'.encode("utf-8"),
        b'    execution_result: Literal["pass", "fail", "\\ud800"]\n',
    )
    invalid_payload = _marked_payload(invalid_declaration, "SIA-CTV-ENUM-REGISTRY-V2", "json")
    invalid_payload = invalid_payload.replace('"caf\u00e9"'.encode("utf-8"), b'"\\ud800"')
    invalid = tmp_path / "surrogate.md"
    invalid.write_bytes(
        _replace_marked(
            invalid_declaration,
            "SIA-CTV-ENUM-REGISTRY-V2",
            "json",
            invalid_payload,
        )
    )
    output = tmp_path / "surrogate.reference.json"
    checked_output = tmp_path / "surrogate.checked.json"
    sentinel = b"preserve\n"
    for target in (output, checked_output):
        target.write_bytes(sentinel)
        target.chmod(0o640)
    assert _run(invalid, REGISTRY, output).returncode != 0
    assert _validator_run(invalid, REGISTRY, checked_output).returncode != 0
    for target in (output, checked_output):
        assert target.read_bytes() == sentinel
        assert target.stat().st_mode & 0o7777 == 0o640
        assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


def test_foreign_pid_temporary_file_survives_atomic_publication_collision(tmp_path: Path) -> None:
    bootstrap = tmp_path / "collision.py"
    bootstrap.write_text(COLLISION_BOOTSTRAP, encoding="ascii")
    output = tmp_path / "authority.json"
    sentinel = b"preexisting-output\n"
    output.write_bytes(sentinel)
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(bootstrap),
            str(COMPILER),
            str(DESIGN),
            str(REGISTRY),
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    actual_foreign = list(tmp_path.glob(".authority.json.*.tmp"))
    assert len(actual_foreign) == 1
    assert actual_foreign[0].read_bytes() == b"foreign-temp-owner\n"
    assert output.read_bytes() == sentinel

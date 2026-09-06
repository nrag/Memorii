"""Clean-room compiler for the semantic-ingestion CTV v2 binding authority."""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROFILE_ID = "semantic_ingestion_typed_value"
PROFILE_VERSION = "2"
SCHEMA_VERSION = "1"
AUTHORITY_FORMAT = "memorii-sia-ctv-binding-authority-v2"
GRAMMAR_REVISION = "sia-ctv-grammar-v2"
ENUM_REVISION = "sia-ctv-enum-registry-v2"
EXPECTED_GRAMMAR = {
    "profile_id": PROFILE_ID,
    "profile_version": PROFILE_VERSION,
    "null": "json-null",
    "boolean": "json-boolean",
    "integer": "tagged-canonical-base10-unbounded",
    "string": "unicode-scalar-string",
    "bytes": "tagged-canonical-padded-rfc4648-base64",
    "datetime": "tagged-utc-microseconds-z",
    "duration": "tagged-signed-int64-microseconds",
    "list": "tagged-ordered-list",
    "tuple": "tagged-ordered-tuple",
    "set": "tagged-canonical-encoded-byte-order-unique-set",
    "frozenset": "tagged-canonical-encoded-byte-order-unique-frozenset",
    "map": "tagged-unicode-scalar-key-order-unique-map",
    "enum": "tagged-schema-and-canonical-literal-scalar-member",
    "enum_member": "string|boolean|tagged-canonical-integer|null",
    "unknown_tag": "reject",
    "unknown_schema": "reject",
    "unknown_enum_schema_or_member": "reject",
}
PROTOCOL_NAMES = {
    "AuthenticatedIngressContextResolver",
    "BootstrapGraphControlEpochRepositoryV3",
    "BootstrapGraphDependentAuthorityProviderV3",
    "BootstrapGraphDependentCoordinatorV3",
    "BootstrapGraphGroupCommitRepositoryV3",
    "BootstrapGraphGroupExecutorPortV3",
    "BootstrapGraphPlanCompilerPortV3",
    "BootstrapGraphPlanRepositoryV3",
    "BootstrapGraphPlanningAuthorizerPortV3",
    "BootstrapGraphTargetMaterializationPlannerV3",
    "BootstrapGraphTerminalPersistencePortV3",
    "BootstrapGraphTerminalPreparationPortV3",
    "BootstrapGraphTransactionAuthorityProjectionBuilderV3",
    "BootstrapGraphTransactionAuthorityRepositoryV3",
    "BootstrapNativeIdentityAdmissionPortV3",
    "BootstrapRecoveryClaimRenewalPort",
    "BootstrapRecoveryClaimRepositoryV3",
    "CapabilityBaselineApprovalVerifier",
    "CurrentBootstrapReleaseVerifier",
    "DeploymentAuthorizationTrustStore",
    "DeploymentAuthorizationVerifier",
    "GraphFreeSourceNormalizationRuntime",
    "GraphObservationAuthorizer",
    "IdentityOperationPlanner",
    "SealedSemanticProposalRunProducer",
    "SealedSourceNormalizationEvidenceProducer",
    "SemanticIngestionAtomicStore",
    "SemanticIngestionOutcomeAuthorizer",
    "SourceNormalizationAuthorityProvider",
    "SourceNormalizationResourceReservationProvider",
    "SourceNormalizationTrustedTime",
    "TerminalBeforePlanningProofRepository",
}
GENERATION_MEMBER_TAGS = (
    ("TraceabilityRawDesignGenerationMember", "design_document"),
    ("TraceabilityRawRegistryGenerationMember", "registry_source"),
    ("TraceabilityReportSchemaGenerationMember", "report_schema"),
    ("TraceabilityRunnerEnvironmentProfileGenerationMember", "runner_environment_profile"),
    ("TraceabilityTestArtifactGenerationMember", "test_artifact"),
    ("TraceabilityResultArtifactGenerationMember", "result_artifact"),
    ("TraceabilityStdoutGenerationMember", "stdout_artifact"),
    ("TraceabilityStderrGenerationMember", "stderr_artifact"),
    ("TraceabilityGoldenTypedInputFixtureGenerationMember", "golden_typed_input_fixture"),
    ("TraceabilityBootstrapAnchorGenerationMember", "bootstrap_anchor"),
    ("TraceabilityBootstrapAnchorHistoryGenerationMember", "bootstrap_anchor_history"),
    ("TraceabilityRecoveryRootGenerationMember", "recovery_root"),
    ("TraceabilityRecoveryRootHistoryGenerationMember", "recovery_root_history"),
    ("TraceabilityRecoveryPolicyGenerationMember", "recovery_policy"),
    ("TraceabilityRecoveryPolicyHistoryGenerationMember", "recovery_policy_history"),
    ("TraceabilityLifecycleRootGenerationMember", "trust_lifecycle_root"),
    ("TraceabilityTrustSnapshotGenerationMember", "trust_snapshot"),
    ("TraceabilityStructuralManifestGenerationMember", "structural_manifest"),
    ("TraceabilityCoverageApprovalGenerationMember", "coverage_approval"),
    ("TraceabilityCoverageRootGenerationMember", "coverage_root"),
    ("TraceabilityRunnerObservationGenerationMember", "runner_environment_observation"),
    ("TraceabilityRunnerReportGenerationMember", "runner_report"),
    ("TraceabilityExecutionEvidenceGenerationMember", "execution_evidence"),
    ("TraceabilityExecutionRootGenerationMember", "execution_root"),
    ("TraceabilityReleaseGenerationMember", "release"),
    ("TraceabilityReleaseHistoryGenerationMember", "release_history"),
    ("TraceabilityPointerHistoryGenerationMember", "pointer_history"),
    ("TraceabilityGoldenVectorManifestGenerationMember", "golden_vector_manifest"),
)
ROOT_DECLARATIONS = {
    "TraceabilityRegistryRoot.anchor_bindings": "TraceabilityRegistryRootAnchorBindings",
    "TraceabilityRegistryRoot.artifact_dag": "TraceabilityRegistryRootArtifactDag",
    "TraceabilityRegistryRoot.assertion_templates": "TraceabilityRegistryRootAssertionTemplates",
    "TraceabilityRegistryRoot.heading_defaults": "TraceabilityRegistryRootHeadingDefaults",
    "TraceabilityRegistryRoot.overrides": "TraceabilityRegistryRootOverrides",
    "TraceabilityRegistryRoot.requirement_bindings": "TraceabilityRegistryRootRequirementBindings",
    "TraceabilityRegistryRoot.structural_rules": "TraceabilityRegistryRootStructuralRules",
    "TraceabilityRegistryRoot.test_evidence_groups": "TraceabilityRegistryRootTestEvidenceGroups",
}
SCALARS = {"str", "bool", "int", "bytes", "datetime", "timedelta"}


class CtvCompilationError(ValueError):
    """Raised when design authority is incomplete or outside the CTV language."""


def _canonical(value: Any) -> bytes:
    _validate_json_value(value)
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        .encode("utf-8")
        + b"\n"
    )


def _validate_json_value(value: Any) -> None:
    if isinstance(value, float):
        raise CtvCompilationError("floating-point JSON values are forbidden")
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise CtvCompilationError("JSON strings must contain only Unicode scalars")
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CtvCompilationError("JSON object names must be strings")
            _validate_json_value(key)
            _validate_json_value(item)
        return
    raise CtvCompilationError(f"unsupported canonical JSON value: {type(value).__name__}")


def _closed_json(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise CtvCompilationError(f"duplicate JSON name: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(data, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CtvCompilationError("invalid JSON authority block") from error
    _validate_json_value(value)
    return value


def _lp(value: str | bytes) -> bytes:
    encoded = value if isinstance(value, bytes) else value.encode("ascii")
    return len(encoded).to_bytes(8, "big") + encoded


def _marked_span(document: bytes, marker: str, language: str) -> tuple[int, int]:
    begin = f"`[{marker}-BEGIN]`\n```{language}\n".encode("ascii")
    end = f"```\n`[{marker}-END]`".encode("ascii")
    spans: list[tuple[int, int]] = []
    cursor = 0
    while True:
        block_start = document.find(begin, cursor)
        while block_start >= 0 and block_start > 0 and document[block_start - 1] != 0x0A:
            block_start = document.find(begin, block_start + 1)
        if block_start < 0:
            break
        payload_start = block_start + len(begin)
        payload_end = document.find(end, payload_start)
        while payload_end >= 0 and (
            payload_end + len(end) < len(document)
            and document[payload_end + len(end)] != 0x0A
        ):
            payload_end = document.find(end, payload_end + 1)
        if payload_end < 0:
            break
        spans.append((payload_start, payload_end))
        cursor = payload_end + len(end)
    if len(spans) != 1:
        raise CtvCompilationError(f"{marker}: expected one marked block")
    return spans[0]


def _marked(document: bytes, marker: str, language: str) -> bytes:
    start, end = _marked_span(document, marker, language)
    return document[start:end]


def _replace_marked_payload(document: bytes, marker: str, language: str, replacement: bytes) -> bytes:
    start, end = _marked_span(document, marker, language)
    return document[:start] + replacement + document[end:]


def _python_fences(document: str) -> list[str]:
    opening = "```python\n"
    fences: list[str] = []
    cursor = 0
    while True:
        start = document.find(opening, cursor)
        if start < 0:
            return fences
        content_start = start + len(opening)
        content_end = document.find("```", content_start)
        if content_end < 0:
            raise CtvCompilationError("unterminated Python fence")
        fences.append(document[content_start:content_end])
        cursor = content_end + 3


def _validate_data_expression(node: ast.expr) -> None:
    """Validate closed metadata and Literal data without parsing strings as types."""
    if isinstance(node, (ast.Name, ast.Constant)):
        return
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            _validate_data_expression(item)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        _validate_data_expression(node.operand)
        return
    raise CtvCompilationError("unsupported declaration data expression")


def _validate_field_data_expression(node: ast.expr) -> None:
    if (
        not isinstance(node, ast.Call)
        or not isinstance(node.func, ast.Name)
        or node.func.id != "Field"
    ):
        raise CtvCompilationError("Annotated metadata must be Field(...)")
    for argument in node.args:
        _validate_data_expression(argument)
    for keyword in node.keywords:
        if keyword.arg is None:
            raise CtvCompilationError("Field **kwargs are forbidden")
        _validate_data_expression(keyword.value)


def _validate_type_expression(node: ast.expr) -> None:
    """Validate every declaration type position before projection can skip it."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            forwarded = ast.parse(node.value, mode="eval").body
        except SyntaxError as error:
            raise CtvCompilationError("invalid quoted type expression") from error
        if isinstance(forwarded, ast.Constant) and forwarded.value is Ellipsis:
            raise CtvCompilationError("quoted ellipsis is not a type expression")
        _validate_type_expression(forwarded)
        return
    if isinstance(node, ast.Constant) and node.value is Ellipsis:
        raise CtvCompilationError("ellipsis is permitted only in exact tuple[T, ...]")
    if isinstance(node, (ast.Name, ast.Constant)):
        return
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            _validate_type_expression(item)
        return
    if isinstance(node, ast.Subscript):
        if not isinstance(node.value, ast.Name):
            raise CtvCompilationError("qualified generic owner is forbidden")
        arguments = (
            list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
        )
        if node.value.id in {"list", "set", "frozenset"} and (
            len(arguments) != 1
            or any(
                isinstance(argument, ast.Constant) and argument.value is Ellipsis
                for argument in arguments
            )
        ):
            raise CtvCompilationError(
                f"{node.value.id} annotation requires one non-ellipsis item"
            )
        if node.value.id == "dict" and len(arguments) != 2:
            raise CtvCompilationError("dict requires key and value annotations")
        if node.value.id == "tuple":
            ellipsis_positions = [
                index
                for index, argument in enumerate(arguments)
                if isinstance(argument, ast.Constant) and argument.value is Ellipsis
            ]
            if ellipsis_positions and (
                len(arguments) != 2 or ellipsis_positions != [1]
            ):
                raise CtvCompilationError("variadic tuple must be tuple[T, ...]")
        if node.value.id == "Literal":
            for argument in arguments:
                _validate_data_expression(argument)
            return
        if node.value.id == "Annotated":
            if not arguments:
                raise CtvCompilationError("Annotated requires a projected type")
            _validate_type_expression(arguments[0])
            for metadata in arguments[1:]:
                _validate_field_data_expression(metadata)
            return
        for argument in arguments:
            if (
                node.value.id == "tuple"
                and len(arguments) == 2
                and arguments.index(argument) == 1
                and isinstance(argument, ast.Constant)
                and argument.value is Ellipsis
            ):
                continue
            _validate_type_expression(argument)
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        _validate_type_expression(node.left)
        _validate_type_expression(node.right)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        _validate_type_expression(node.operand)
        return
    raise CtvCompilationError(f"unsupported declaration expression: {ast.dump(node, include_attributes=False)}")


def _protocol_method(node: ast.FunctionDef) -> None:
    if (
        getattr(node, "type_params", ())
        or node.decorator_list
        or node.args.posonlyargs
        or node.args.vararg is not None
        or node.args.kwarg is not None
        or node.args.defaults
        or any(default is not None for default in node.args.kw_defaults)
        or node.returns is None
        or len(node.body) != 1
        or not isinstance(node.body[0], ast.Expr)
        or not isinstance(node.body[0].value, ast.Constant)
        or node.body[0].value.value is not Ellipsis
    ):
        raise CtvCompilationError(f"{node.name}: invalid Protocol method")
    for argument in (*node.args.args, *node.args.kwonlyargs):
        if argument.arg != "self" or argument.annotation is not None:
            if argument.annotation is None:
                raise CtvCompilationError(f"{node.name}: unannotated Protocol argument")
            _validate_type_expression(argument.annotation)
    _validate_type_expression(node.returns)


def _class_kind(node: ast.ClassDef) -> str:
    if (
        getattr(node, "type_params", ())
        or node.decorator_list
        or node.keywords
        or len(node.bases) > 1
        or any(not isinstance(base, ast.Name) for base in node.bases)
    ):
        raise CtvCompilationError(f"{node.name}: unsupported class header")
    base = node.bases[0].id if node.bases and isinstance(node.bases[0], ast.Name) else None
    if base == "Protocol":
        if node.name not in PROTOCOL_NAMES or any(not isinstance(item, ast.FunctionDef) for item in node.body):
            raise CtvCompilationError(f"{node.name}: invalid Protocol exception")
        for item in node.body:
            assert isinstance(item, ast.FunctionDef)
            _protocol_method(item)
        return "protocol"
    if base == "StrEnum":
        if node.name != "SourceKind":
            raise CtvCompilationError(f"{node.name}: invalid StrEnum exception")
        for item in node.body:
            if (
                not isinstance(item, ast.Assign)
                or len(item.targets) != 1
                or not isinstance(item.targets[0], ast.Name)
                or not isinstance(item.value, ast.Constant)
                or not isinstance(item.value.value, str)
            ):
                raise CtvCompilationError("SourceKind must contain string assignments")
        return "strenum"
    for item in node.body:
        if (
            not isinstance(item, ast.AnnAssign)
            or item.simple != 1
            or not isinstance(item.target, ast.Name)
            or item.value is not None
            and not isinstance(item.value, ast.Call)
        ):
            raise CtvCompilationError(f"{node.name}: model body is not declarative")
        _validate_type_expression(item.annotation)
        if item.value is not None:
            _field_policy(item)
    return "model"


@dataclass(frozen=True)
class _Declarations:
    classes: dict[str, ast.ClassDef]
    aliases: dict[str, ast.expr]
    kinds: dict[str, str]


def _declarations(document: str) -> _Declarations:
    classes: dict[str, ast.ClassDef] = {}
    aliases: dict[str, ast.expr] = {}
    kinds: dict[str, str] = {}
    protocol_seen: set[str] = set()
    strenum_seen: set[str] = set()
    for source in _python_fences(document):
        try:
            module = ast.parse(source)
        except SyntaxError:
            continue
        if not any(isinstance(item, ast.ClassDef) for item in module.body):
            continue
        for item in module.body:
            if isinstance(item, ast.ClassDef):
                kind = _class_kind(item)
                name = item.name
                protocol_seen.update({name} if kind == "protocol" else ())
                strenum_seen.update({name} if kind == "strenum" else ())
                value: ast.expr | None = None
            elif (
                isinstance(item, ast.Assign)
                and len(item.targets) == 1
                and isinstance(item.targets[0], ast.Name)
            ):
                name = item.targets[0].id
                kind = "alias"
                value = item.value
                _validate_type_expression(value)
            else:
                raise CtvCompilationError("schema fence contains an executable module statement")
            if name in kinds:
                raise CtvCompilationError(f"duplicate declaration: {name}")
            if name == "BaseModel":
                raise CtvCompilationError("BaseModel must remain external")
            kinds[name] = kind
            if isinstance(item, ast.ClassDef):
                classes[name] = item
            else:
                assert value is not None
                aliases[name] = value
    if protocol_seen != PROTOCOL_NAMES or strenum_seen != {"SourceKind"}:
        raise CtvCompilationError("interface exception inventory differs from the v2 contract")
    return _Declarations(classes, aliases, kinds)


def _field_policy(node: ast.AnnAssign) -> dict[str, Any]:
    if node.value is None:
        return {"constraints": {}, "default": {"kind": "required"}}
    call = node.value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "Field" or call.args:
        raise CtvCompilationError("field default must be a keyword-only Field call")
    constraints: dict[str, int] = {}
    default: dict[str, Any] = {"kind": "required"}
    seen: set[str] = set()
    for keyword in call.keywords:
        if keyword.arg is None or keyword.arg in seen or keyword.arg not in {"default", "ge", "gt", "le"}:
            raise CtvCompilationError("unsupported or duplicate Field keyword")
        seen.add(keyword.arg)
        try:
            value = ast.literal_eval(keyword.value)
        except (ValueError, TypeError) as error:
            raise CtvCompilationError("Field metadata must be literal") from error
        if keyword.arg == "default":
            if value is not None and not isinstance(value, (str, bool, int)):
                raise CtvCompilationError("unsupported Field default")
            default = {"kind": "literal", "value": value}
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                raise CtvCompilationError("Field constraint must be an integer")
            constraints[keyword.arg] = value
    return {"constraints": constraints, "default": default}


def _literal_member(node: ast.expr) -> Any:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError) as error:
        raise CtvCompilationError("enum member must be literal") from error
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return {"$type": "integer", "value": str(value)}
    raise CtvCompilationError("unsupported enum member")


class _Projector:
    def __init__(self, declarations: _Declarations) -> None:
        self.declarations = declarations
        self.enum_rows: dict[str, list[Any]] = {}

    def _literal_nodes(
        self,
        node: ast.expr,
        stack: tuple[str, ...] = (),
        alias_owner: str | None = None,
    ) -> list[ast.expr] | None:
        if isinstance(node, ast.Name) and node.id in self.declarations.aliases:
            if node.id in stack:
                raise CtvCompilationError(f"recursive alias: {node.id}")
            return self._literal_nodes(
                self.declarations.aliases[node.id],
                stack + (node.id,),
                node.id,
            )
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Literal":
            return list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = self._literal_nodes(node.left, stack, alias_owner)
            right = self._literal_nodes(node.right, stack, alias_owner)
            return None if left is None or right is None else left + right
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Annotated":
            return self._literal_nodes(self._annotated(node, alias_owner), stack, alias_owner)
        return None

    def _enum(self, schema: str, nodes: list[ast.expr]) -> dict[str, Any]:
        members = [_literal_member(node) for node in nodes]
        identities = [_canonical(member) for member in members]
        if not members or len(set(identities)) != len(identities):
            raise CtvCompilationError(f"{schema}: empty or duplicate enum")
        previous = self.enum_rows.setdefault(schema, members)
        if _canonical(previous) != _canonical(members):
            raise CtvCompilationError(f"{schema}: conflicting enum declarations")
        return {"kind": "enum", "members": members, "schema": schema}

    def _fields(self, name: str, stack: tuple[str, ...] = ()) -> list[tuple[str, str, ast.AnnAssign]]:
        if name in stack:
            raise CtvCompilationError(f"cyclic inheritance through {name}")
        declaration = self.declarations.classes[name]
        output: list[tuple[str, str, ast.AnnAssign]] = []
        positions: dict[str, int] = {}
        if declaration.bases:
            base = declaration.bases[0]
            assert isinstance(base, ast.Name)
            if base.id != "BaseModel":
                if base.id not in self.declarations.classes:
                    raise CtvCompilationError(f"{name}: unresolved base {base.id}")
                if self.declarations.kinds[base.id] != "model":
                    raise CtvCompilationError(f"{name}: interface class entered CTV projection")
                for owner, field, node in self._fields(base.id, stack + (name,)):
                    positions[field] = len(output)
                    output.append((owner, field, node))
        for item in declaration.body:
            assert isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            field = item.target.id
            row = (name, field, item)
            if field in positions:
                output[positions[field]] = row
            else:
                positions[field] = len(output)
                output.append(row)
        return output

    def _annotated(self, node: ast.Subscript, alias_owner: str | None) -> ast.expr:
        arguments = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
        if len(arguments) != 2 or alias_owner != "TraceabilityGenerationMember":
            raise CtvCompilationError("unsupported Annotated metadata")
        metadata = arguments[1]
        if (
            not isinstance(metadata, ast.Call)
            or not isinstance(metadata.func, ast.Name)
            or metadata.func.id != "Field"
            or metadata.args
            or len(metadata.keywords) != 1
            or metadata.keywords[0].arg != "discriminator"
            or not isinstance(metadata.keywords[0].value, ast.Constant)
            or metadata.keywords[0].value.value != "artifact_kind"
        ):
            raise CtvCompilationError("invalid generation-member discriminator metadata")
        projected = arguments[0]
        self._validate_generation_members(projected)
        return projected

    @staticmethod
    def _union_members(node: ast.expr) -> list[ast.expr]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return _Projector._union_members(node.left) + _Projector._union_members(node.right)
        return [node]

    def _validate_generation_members(self, projected: ast.expr) -> None:
        members = self._union_members(projected)
        if len(members) != len(GENERATION_MEMBER_TAGS) or any(
            not isinstance(member, ast.Name) for member in members
        ):
            raise CtvCompilationError("TraceabilityGenerationMember must wrap the exact model union")
        names = tuple(member.id for member in members if isinstance(member, ast.Name))
        if names != tuple(name for name, _tag in GENERATION_MEMBER_TAGS):
            raise CtvCompilationError("TraceabilityGenerationMember model order differs from the contract")
        observed: list[tuple[str, str]] = []
        tags: set[str] = set()
        for name in names:
            if name not in self.declarations.classes or self.declarations.kinds[name] != "model":
                raise CtvCompilationError(f"{name}: generation member is not a model")
            tag_fields = [
                declaration
                for _owner, field_name, declaration in self._fields(name)
                if field_name == "artifact_kind"
            ]
            if len(tag_fields) != 1:
                raise CtvCompilationError(f"{name}: generation member requires one artifact_kind")
            annotation = tag_fields[0].annotation
            if not (
                isinstance(annotation, ast.Subscript)
                and isinstance(annotation.value, ast.Name)
                and annotation.value.id == "Literal"
            ):
                raise CtvCompilationError(f"{name}.artifact_kind must be a direct Literal")
            values = list(annotation.slice.elts) if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
            if (
                len(values) != 1
                or not isinstance(values[0], ast.Constant)
                or not isinstance(values[0].value, str)
            ):
                raise CtvCompilationError(f"{name}.artifact_kind must contain one string")
            tag = values[0].value
            if tag in tags:
                raise CtvCompilationError(f"duplicate generation-member discriminator: {tag}")
            tags.add(tag)
            observed.append((name, tag))
        if tuple(observed) != GENERATION_MEMBER_TAGS:
            raise CtvCompilationError("generation-member discriminator mapping differs from the contract")

    def normalize(
        self,
        node: ast.expr,
        *,
        owner: str | None = None,
        field: str | None = None,
        model_stack: tuple[str, ...] = (),
        alias_stack: tuple[str, ...] = (),
        alias_owner: str | None = None,
    ) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                forwarded = ast.parse(node.value, mode="eval").body
            except SyntaxError as error:
                raise CtvCompilationError(f"invalid forward reference: {node.value}") from error
            return self.normalize(
                forwarded,
                owner=owner,
                field=field,
                model_stack=model_stack,
                alias_stack=alias_stack,
                alias_owner=alias_owner,
            )
        if isinstance(node, ast.Constant) and node.value is None:
            return {"kind": "null"}
        if isinstance(node, ast.Name):
            name = node.id
            if name in SCALARS:
                return {"kind": "scalar", "name": name}
            if name in {"Any", "object"}:
                raise CtvCompilationError(f"open annotation is forbidden: {name}")
            if name in self.declarations.aliases:
                if name in alias_stack:
                    raise CtvCompilationError(f"recursive alias: {name}")
                target = self.declarations.aliases[name]
                literals = self._literal_nodes(target, (name,), name)
                if literals is not None:
                    return self._enum(name, literals)
                return self.normalize(
                    target,
                    owner=owner,
                    field=field,
                    model_stack=model_stack,
                    alias_stack=alias_stack + (name,),
                    alias_owner=name,
                )
            if name in self.declarations.classes:
                if self.declarations.kinds[name] != "model":
                    raise CtvCompilationError(f"{name}: interface class entered CTV projection")
                if name in model_stack:
                    return {"kind": "model_ref", "name": name}
                fields = []
                for declaring_owner, field_name, declaration in self._fields(name):
                    fields.append(
                        {
                            "annotation": self.normalize(
                                declaration.annotation,
                                owner=declaring_owner,
                                field=field_name,
                                model_stack=model_stack + (name,),
                                alias_stack=alias_stack,
                            ),
                            "declaring_owner": declaring_owner,
                            "field_name": field_name,
                            **_field_policy(declaration),
                        }
                    )
                return {"fields": fields, "kind": "model", "name": name}
            raise CtvCompilationError(f"unresolved annotation: {name}")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            alternatives = [
                self.normalize(
                    child,
                    owner=owner,
                    field=field,
                    model_stack=model_stack,
                    alias_stack=alias_stack,
                    alias_owner=alias_owner,
                )
                for child in (node.left, node.right)
            ]
            alternatives.sort(key=_canonical)
            if _canonical(alternatives[0]) == _canonical(alternatives[1]):
                raise CtvCompilationError("duplicate union alternative")
            return {"alternatives": alternatives, "kind": "union"}
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            container = node.value.id
            arguments = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
            if container == "Literal":
                if owner is None or field is None:
                    raise CtvCompilationError("inline Literal lacks a declaring field")
                return self._enum(f"{owner}.{field}", arguments)
            if container == "Annotated":
                return self.normalize(
                    self._annotated(node, alias_owner),
                    owner=owner,
                    field=field,
                    model_stack=model_stack,
                    alias_stack=alias_stack,
                    alias_owner=alias_owner,
                )
            if container in {"list", "tuple", "set", "frozenset"}:
                if container == "tuple":
                    ellipsis_positions = [
                        index
                        for index, argument in enumerate(arguments)
                        if isinstance(argument, ast.Constant) and argument.value is Ellipsis
                    ]
                    if ellipsis_positions and (len(arguments) != 2 or ellipsis_positions != [1]):
                        raise CtvCompilationError("variadic tuple must be tuple[T, ...]")
                    # `tuple[()]` is the closed finite zero-item tuple.  The
                    # empty argument list is distinct from a bare `tuple`.
                    if not arguments and not isinstance(node.slice, ast.Tuple):
                        raise CtvCompilationError("tuple annotation requires an item")
                elif (
                    len(arguments) != 1
                    or isinstance(arguments[0], ast.Constant)
                    and arguments[0].value is Ellipsis
                ):
                    raise CtvCompilationError(f"{container} annotation requires one non-ellipsis item")
                values: list[Any] = []
                ellipsis = False
                for argument in arguments:
                    if isinstance(argument, ast.Constant) and argument.value is Ellipsis:
                        ellipsis = True
                    else:
                        values.append(
                            self.normalize(
                                argument,
                                owner=owner,
                                field=field,
                                model_stack=model_stack,
                                alias_stack=alias_stack,
                            )
                        )
                return {
                    "items": values,
                    "kind": "collection",
                    "name": container,
                    "variadic": ellipsis or container != "tuple",
                }
            if container == "dict":
                if len(arguments) != 2:
                    raise CtvCompilationError("dict requires key and value annotations")
                key = self.normalize(arguments[0], model_stack=model_stack)
                if key != {"kind": "scalar", "name": "str"}:
                    raise CtvCompilationError("CTV maps require string keys")
                return {
                    "key": key,
                    "kind": "map",
                    "value": self.normalize(
                        arguments[1],
                        owner=owner,
                        field=field,
                        model_stack=model_stack,
                        alias_stack=alias_stack,
                    ),
                }
            raise CtvCompilationError(f"unsupported generic annotation: {container}")
        raise CtvCompilationError(f"unsupported annotation: {ast.dump(node, include_attributes=False)}")


def compile_authority(design_bytes: bytes, registry_bytes: bytes) -> bytes:
    """Compile canonical authority bytes from the frozen design and registry."""
    if not design_bytes or not registry_bytes:
        raise CtvCompilationError("design and registry must be nonempty")
    try:
        design = design_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CtvCompilationError("design must be UTF-8") from error
    grammar_bytes = _marked(design_bytes, "SIA-CTV-GRAMMAR-V2", "text")
    grammar: dict[str, str] = {}
    for row in grammar_bytes.decode("ascii").splitlines():
        if row.count("=") != 1:
            raise CtvCompilationError("grammar row must contain one equals sign")
        key, value = row.split("=")
        if not key or not value or key in grammar:
            raise CtvCompilationError("empty or duplicate grammar row")
        grammar[key] = value
    if grammar != EXPECTED_GRAMMAR:
        raise CtvCompilationError("grammar differs from the closed v2 profile")

    inventory_bytes = _marked(design_bytes, "SIA-TRACEABILITY-SCHEMA-INVENTORY-V1", "text")
    inventory = inventory_bytes.decode("ascii").splitlines()
    if len(inventory) != 56 or inventory != sorted(set(inventory)):
        raise CtvCompilationError("inventory must contain 56 sorted unique coordinates")

    declarations = _declarations(design)
    projector = _Projector(declarations)
    schemas: list[dict[str, Any]] = []
    for coordinate in inventory:
        declaration_name = ROOT_DECLARATIONS.get(
            coordinate.removesuffix(".v1"), coordinate.removesuffix(".v1")
        )
        if declaration_name not in declarations.kinds:
            raise CtvCompilationError(f"{coordinate}: missing declared root")
        graph = projector.normalize(ast.Name(id=declaration_name))
        graph_bytes = _canonical(graph)
        fingerprint_preimage = (
            b"memorii:sia-ctv-schema-fingerprint:v2\0"
            + _lp(coordinate)
            + _lp(graph_bytes)
        )
        schemas.append(
            {
                "binding_digest": "",
                "binding_preimage_base64": "",
                "coordinate": coordinate,
                "declared_root": declaration_name,
                "normalized_graph": graph,
                "normalized_graph_bytes_base64": base64.b64encode(graph_bytes).decode("ascii"),
                "schema_fingerprint": hashlib.sha256(fingerprint_preimage).hexdigest(),
                "schema_fingerprint_preimage_base64": base64.b64encode(fingerprint_preimage).decode("ascii"),
            }
        )

    declared_enum_rows = _closed_json(_marked(design_bytes, "SIA-CTV-ENUM-REGISTRY-V2", "json"))
    compiled_enum_rows = dict(sorted(projector.enum_rows.items()))
    if not isinstance(declared_enum_rows, dict) or _canonical(declared_enum_rows) != _canonical(compiled_enum_rows):
        raise CtvCompilationError("marked enum registry differs from projected declarations")
    # The frozen authority is an inventory, not an implementation guess.  A
    # row-count drift must stop compilation before a consumer can elaborate a
    # different profile under the same coordinates.
    if len(compiled_enum_rows) != 249:
        raise CtvCompilationError("enum registry must contain 249 rows")

    enum_bytes = _canonical(compiled_enum_rows)
    grammar_preimage = b"memorii:sia-ctv-grammar:v2\0" + grammar_bytes
    enum_preimage = b"memorii:sia-ctv-enum-registry:v2\0" + enum_bytes
    grammar_digest = hashlib.sha256(grammar_preimage).hexdigest()
    enum_digest = hashlib.sha256(enum_preimage).hexdigest()
    profile_preimage = b"".join(
        (
            b"memorii:sia-ctv-profile:v2\0",
            _lp(PROFILE_ID),
            _lp(PROFILE_VERSION),
            _lp(GRAMMAR_REVISION),
            _lp(grammar_digest),
            _lp(grammar_bytes),
            _lp(ENUM_REVISION),
            _lp(enum_digest),
            _lp(enum_bytes),
        )
    )
    profile_digest = hashlib.sha256(profile_preimage).hexdigest()
    for schema in schemas:
        binding_preimage = b"".join(
            (
                b"memorii:sia-ctv-binding:v2\0",
                _lp(PROFILE_ID),
                _lp(PROFILE_VERSION),
                _lp(profile_digest),
                _lp(schema["coordinate"]),
                _lp(SCHEMA_VERSION),
                _lp(schema["schema_fingerprint"]),
            )
        )
        schema["binding_preimage_base64"] = base64.b64encode(binding_preimage).decode("ascii")
        schema["binding_digest"] = hashlib.sha256(binding_preimage).hexdigest()

    source_design = _replace_marked_payload(
        design_bytes,
        "SIA-CTV-ENUM-REGISTRY-V1",
        "json",
        b"<v1-baseline-excluded-from-v2-authority>\n",
    )
    authority = {
        "enum_registry": {
            "canonical_bytes_base64": base64.b64encode(enum_bytes).decode("ascii"),
            "digest": enum_digest,
            "digest_preimage_base64": base64.b64encode(enum_preimage).decode("ascii"),
            "rows": compiled_enum_rows,
        },
        "format": AUTHORITY_FORMAT,
        "grammar": {
            "digest": grammar_digest,
            "digest_preimage_base64": base64.b64encode(grammar_preimage).decode("ascii"),
            "payload": grammar_bytes.decode("ascii"),
            "payload_base64": base64.b64encode(grammar_bytes).decode("ascii"),
            "revision": GRAMMAR_REVISION,
        },
        "inventory": inventory,
        "profile": {
            "digest": profile_digest,
            "id": PROFILE_ID,
            "preimage_base64": base64.b64encode(profile_preimage).decode("ascii"),
            "version": 2,
        },
        "schemas": schemas,
        "source_design_sha256": hashlib.sha256(source_design).hexdigest(),
        "source_registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
    }
    return _canonical(authority)


def compile_to_path(design: Path, registry: Path, output: Path) -> None:
    """Compile fully before atomically replacing an output path."""
    compiled = compile_authority(design.read_bytes(), registry.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary_created = False
    try:
        with temporary.open("xb") as stream:
            temporary_created = True
            stream.write(compiled)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
        temporary_created = False
    finally:
        if temporary_created and temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compile_to_path(args.design, args.registry, args.output)


if __name__ == "__main__":
    main()

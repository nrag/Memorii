"""Compile and validate the corpus-independent CTV binding authority v2."""

from __future__ import annotations

import argparse
import ast
import base64
import errno
import hashlib
import json
import os
import re
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


PROFILE_ID = "semantic_ingestion_typed_value"
PROFILE_VERSION = "2"
SCHEMA_VERSION = "1"
FORMAT = "memorii-sia-ctv-binding-authority-v2"
FORBIDDEN_INPUT_TERMS = (
    "recipe",
    "fixture",
    "package",
    "signer",
    "mutation",
    "golden_vectors",
)
REGISTRY_ROOTS = {
    "TraceabilityRegistryRoot.anchor_bindings": "TraceabilityRegistryRootAnchorBindings",
    "TraceabilityRegistryRoot.artifact_dag": "TraceabilityRegistryRootArtifactDag",
    "TraceabilityRegistryRoot.assertion_templates": "TraceabilityRegistryRootAssertionTemplates",
    "TraceabilityRegistryRoot.heading_defaults": "TraceabilityRegistryRootHeadingDefaults",
    "TraceabilityRegistryRoot.overrides": "TraceabilityRegistryRootOverrides",
    "TraceabilityRegistryRoot.requirement_bindings": "TraceabilityRegistryRootRequirementBindings",
    "TraceabilityRegistryRoot.structural_rules": "TraceabilityRegistryRootStructuralRules",
    "TraceabilityRegistryRoot.test_evidence_groups": "TraceabilityRegistryRootTestEvidenceGroups",
}
EXPECTED_GRAMMAR = {
    "profile_id": PROFILE_ID, "profile_version": PROFILE_VERSION,
    "null": "json-null", "boolean": "json-boolean",
    "integer": "tagged-canonical-base10-unbounded",
    "string": "unicode-scalar-string",
    "bytes": "tagged-canonical-padded-rfc4648-base64",
    "datetime": "tagged-utc-microseconds-z",
    "duration": "tagged-signed-int64-microseconds",
    "list": "tagged-ordered-list", "tuple": "tagged-ordered-tuple",
    "set": "tagged-canonical-encoded-byte-order-unique-set",
    "frozenset": "tagged-canonical-encoded-byte-order-unique-frozenset",
    "map": "tagged-unicode-scalar-key-order-unique-map",
    "enum": "tagged-schema-and-canonical-literal-scalar-member",
    "enum_member": "string|boolean|tagged-canonical-integer|null",
    "unknown_tag": "reject", "unknown_schema": "reject",
    "unknown_enum_schema_or_member": "reject",
}
EXPECTED_PROTOCOL_CLASSES = {
    "AuthenticatedIngressContextResolver",
    "CapabilityBaselineApprovalVerifier",
    "CurrentBootstrapReleaseVerifier",
    "DeploymentAuthorizationTrustStore",
    "DeploymentAuthorizationVerifier",
    "GraphObservationAuthorizer",
    "SemanticIngestionAtomicStore",
    "SemanticIngestionOutcomeAuthorizer",
}
EXPECTED_STRENUM_CLASSES = {"SourceKind"}
EXPECTED_UNREACHABLE_DEFAULT_NONE_FIELDS = {
    ("ActionTransitionRoleRequirement", "maximum_cardinality_override"),
    ("ActionTransitionRoleRequirement", "minimum_cardinality_override"),
    ("AuthenticatedIngressContext", "language_declaration"),
    ("AuthenticatedIngressContext", "semantic_egress_governance"),
    ("AuthenticatedIngressContext", "semantic_source_authority"),
    ("AuthenticatedIngressContext", "semantic_source_interval"),
    ("OracleEffectRoleCardinality", "maximum_cardinality"),
}
EXPECTED_GENERATION_MEMBER_DISCRIMINATORS = (
    ("TraceabilityRawDesignGenerationMember", "design_document"),
    ("TraceabilityRawRegistryGenerationMember", "registry_source"),
    ("TraceabilityReportSchemaGenerationMember", "report_schema"),
    (
        "TraceabilityRunnerEnvironmentProfileGenerationMember",
        "runner_environment_profile",
    ),
    ("TraceabilityTestArtifactGenerationMember", "test_artifact"),
    ("TraceabilityResultArtifactGenerationMember", "result_artifact"),
    ("TraceabilityStdoutGenerationMember", "stdout_artifact"),
    ("TraceabilityStderrGenerationMember", "stderr_artifact"),
    (
        "TraceabilityGoldenTypedInputFixtureGenerationMember",
        "golden_typed_input_fixture",
    ),
    ("TraceabilityBootstrapAnchorGenerationMember", "bootstrap_anchor"),
    (
        "TraceabilityBootstrapAnchorHistoryGenerationMember",
        "bootstrap_anchor_history",
    ),
    ("TraceabilityRecoveryRootGenerationMember", "recovery_root"),
    (
        "TraceabilityRecoveryRootHistoryGenerationMember",
        "recovery_root_history",
    ),
    ("TraceabilityRecoveryPolicyGenerationMember", "recovery_policy"),
    (
        "TraceabilityRecoveryPolicyHistoryGenerationMember",
        "recovery_policy_history",
    ),
    ("TraceabilityLifecycleRootGenerationMember", "trust_lifecycle_root"),
    ("TraceabilityTrustSnapshotGenerationMember", "trust_snapshot"),
    (
        "TraceabilityStructuralManifestGenerationMember",
        "structural_manifest",
    ),
    (
        "TraceabilityCoverageApprovalGenerationMember",
        "coverage_approval",
    ),
    ("TraceabilityCoverageRootGenerationMember", "coverage_root"),
    (
        "TraceabilityRunnerObservationGenerationMember",
        "runner_environment_observation",
    ),
    ("TraceabilityRunnerReportGenerationMember", "runner_report"),
    (
        "TraceabilityExecutionEvidenceGenerationMember",
        "execution_evidence",
    ),
    ("TraceabilityExecutionRootGenerationMember", "execution_root"),
    ("TraceabilityReleaseGenerationMember", "release"),
    ("TraceabilityReleaseHistoryGenerationMember", "release_history"),
    ("TraceabilityPointerHistoryGenerationMember", "pointer_history"),
    (
        "TraceabilityGoldenVectorManifestGenerationMember",
        "golden_vector_manifest",
    ),
)


def validate_unicode_scalars(value: Any) -> None:
    """Reject every non-scalar string before it can be JSON-escaped."""
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError("strings must contain only Unicode scalar values") from error
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("canonical JSON object keys must be strings")
            validate_unicode_scalars(key)
            validate_unicode_scalars(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            validate_unicode_scalars(item)


def canonical(value: Any) -> bytes:
    validate_unicode_scalars(value)
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        .encode("utf-8")
        + b"\n"
    )


def strict_json_loads(value: str | bytes) -> Any:
    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object name: {key}")
            result[key] = item
        return result

    decoded = json.loads(value, object_pairs_hook=closed_object)
    validate_unicode_scalars(decoded)
    return decoded


def lp(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        raw = value
    else:
        validate_unicode_scalars(value)
        raw = value.encode("utf-8")
    return len(raw).to_bytes(8, "big") + raw


def digest(domain: bytes, payload: bytes) -> str:
    return hashlib.sha256(domain + payload).hexdigest()


def _write_exact(
    stream: Any,
    payload: bytes,
    writer: Callable[[Any, bytes | memoryview], int],
) -> None:
    view = memoryview(payload)
    while view:
        count = writer(stream, view)
        if not isinstance(count, int) or count <= 0 or count > len(view):
            raise OSError("authority temporary write did not make progress")
        view = view[count:]


def _unsupported_sync_error(error: OSError) -> bool:
    return error.errno in {
        errno.EINVAL,
        errno.ENOTSUP,
        getattr(errno, "EOPNOTSUPP", errno.ENOTSUP),
    }


def _fsync_directory(
    directory: Path,
    *,
    opener: Callable[[Path, int], int] = os.open,
    fsync: Callable[[int], None] = os.fsync,
) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = opener(directory, flags)
    except OSError as error:
        if _unsupported_sync_error(error):
            return
        raise
    try:
        try:
            fsync(descriptor)
        except OSError as error:
            if not _unsupported_sync_error(error):
                raise
    finally:
        os.close(descriptor)


def publish_authority_atomically(
    target: Path,
    payload: bytes,
    *,
    writer: Callable[[Any, bytes | memoryview], int] | None = None,
    flusher: Callable[[Any], None] | None = None,
    mode_setter: Callable[[int, int], None] | None = None,
    file_fsync: Callable[[int], None] | None = None,
    replacer: Callable[[str, str], None] | None = None,
    directory_fsync: Callable[[Path], None] | None = None,
) -> None:
    """Publish one fully validated authority without exposing partial bytes."""
    target = target.resolve()
    if target.exists():
        if not target.is_file():
            raise ValueError("authority target must resolve to a regular file")
        target_mode = target.stat().st_mode & 0o7777
    else:
        # Match the historical regular-file creation mode without umask variance.
        target_mode = 0o644
    temporary_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    replaced = False
    try:
        with os.fdopen(temporary_descriptor, "wb") as stream:
            _write_exact(stream, payload, writer or (lambda file, data: file.write(data)))
            (flusher or (lambda file: file.flush()))(stream)
            (mode_setter or os.fchmod)(stream.fileno(), target_mode)
            (file_fsync or os.fsync)(stream.fileno())
        (replacer or os.replace)(str(temporary), str(target))
        replaced = True
        (directory_fsync or _fsync_directory)(target.parent)
    finally:
        if not replaced:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def marked(document: str, marker: str, language: str) -> bytes:
    pattern = (
        rf"^`\[{re.escape(marker)}-BEGIN\]`\n```{language}\n"
        rf"(.*?)```\n`\[{re.escape(marker)}-END\]`$"
    )
    matches = re.findall(pattern, document, re.DOTALL | re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"{marker}: expected exactly one marked block")
    try:
        validate_unicode_scalars(matches[0])
        return matches[0].encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{marker}: marked payload must be strict UTF-8") from error


def replace_marked(
    document: str, marker: str, language: str, replacement: bytes
) -> str:
    pattern = (
        rf"(^`\[{re.escape(marker)}-BEGIN\]`\n```{language}\n)"
        rf"(.*?)"
        rf"(```\n`\[{re.escape(marker)}-END\]`$)"
    )
    matches = list(re.finditer(pattern, document, re.DOTALL | re.MULTILINE))
    if len(matches) != 1:
        raise ValueError(f"{marker}: expected exactly one marked block")
    replacement_text = replacement.decode("utf-8")
    validate_unicode_scalars(replacement_text)
    match = matches[0]
    return (
        document[: match.start()]
        + match.group(1)
        + replacement_text
        + match.group(3)
        + document[match.end() :]
    )


def v2_source_design_sha256(document: str) -> str:
    redacted = replace_marked(
        document,
        "SIA-CTV-ENUM-REGISTRY-V1",
        "json",
        b"<v1-baseline-excluded-from-v2-authority>\n",
    )
    return hashlib.sha256(redacted.encode("utf-8")).hexdigest()


def parse_closed_grammar(payload: bytes) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in payload.decode("ascii").splitlines():
        if line.count("=") != 1:
            raise ValueError("v2 grammar row must contain exactly one '='")
        key, value = line.split("=")
        if not key or not value or key in rows:
            raise ValueError("v2 grammar has empty or duplicate entry")
        rows[key] = value
    if rows != EXPECTED_GRAMMAR:
        raise ValueError("v2 grammar has missing, extra, or altered entries")
    return rows


def assigned_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(assigned_names(item) for item in target.elts))
    if isinstance(target, ast.Starred):
        return assigned_names(target.value)
    return set()


class ModuleBindingCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)
        for expression in (*node.decorator_list, *node.bases):
            self.visit(expression)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)
        self._visit_function_header(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)
        self._visit_function_header(node)

    def _visit_function_header(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        for expression in (
            *node.decorator_list,
            *node.args.defaults,
            *(item for item in node.args.kw_defaults if item is not None),
        ):
            self.visit(expression)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self.names.update(assigned_names(target))
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.names.update(assigned_names(node.target))
        if node.value is not None:
            self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.names.update(assigned_names(node.target))
        self.visit(node.value)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self.names.update(assigned_names(target))

    def visit_TypeAlias(self, node: ast.AST) -> None:
        target = getattr(node, "name", None)
        value = getattr(node, "value", None)
        if not isinstance(target, ast.expr) or not isinstance(value, ast.expr):
            raise ValueError("unsupported type alias declaration")
        self.names.update(assigned_names(target))
        self.visit(value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.names.update(assigned_names(node.target))
        self.visit(node.value)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.names.add(alias.asname or alias.name.split(".", 1)[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                self.names.add("BaseModel")
            else:
                self.names.add(alias.asname or alias.name)

    def visit_For(self, node: ast.For) -> None:
        self.names.update(assigned_names(node.target))
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.names.update(assigned_names(node.target))
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                self.names.update(assigned_names(item.optional_vars))
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                self.names.update(assigned_names(item.optional_vars))
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name is not None:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)
        for case in node.cases:
            for pattern in ast.walk(case.pattern):
                if isinstance(pattern, (ast.MatchAs, ast.MatchStar)):
                    if pattern.name is not None:
                        self.names.add(pattern.name)
                elif isinstance(pattern, ast.MatchMapping) and pattern.rest is not None:
                    self.names.add(pattern.rest)
            if case.guard is not None:
                self.visit(case.guard)
            for statement in case.body:
                self.visit(statement)


def module_binding_names(tree: ast.Module) -> set[str]:
    collector = ModuleBindingCollector()
    collector.visit(tree)
    return collector.names


def validate_data_expression(node: ast.expr) -> None:
    """Validate a closed literal/metadata expression without parsing strings."""
    if isinstance(node, (ast.Name, ast.Constant)):
        return
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            validate_data_expression(item)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        validate_data_expression(node.operand)
        return
    raise ValueError(f"unsupported data expression: {ast.unparse(node)}")


def validate_field_data_expression(node: ast.expr) -> None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        raise ValueError("Annotated metadata must be Field(...)")
    if node.func.id != "Field":
        raise ValueError("only Field(...) is permitted in schema aliases")
    for argument in node.args:
        validate_data_expression(argument)
    for keyword in node.keywords:
        if keyword.arg is None:
            raise ValueError("schema alias Field(...) may not use **kwargs")
        validate_data_expression(keyword.value)


def validate_type_expression(node: ast.expr) -> None:
    """Validate a closed type-position expression without reinterpreting data."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            parsed = ast.parse(node.value, mode="eval").body
        except SyntaxError as error:
            raise ValueError(f"invalid forward reference: {node.value}") from error
        if isinstance(parsed, ast.Constant) and parsed.value is Ellipsis:
            raise ValueError("quoted ellipsis is not a type expression")
        validate_type_expression(parsed)
        return
    if isinstance(node, ast.Constant) and node.value is Ellipsis:
        raise ValueError("ellipsis is permitted only in exact tuple[T, ...]")
    if isinstance(node, (ast.Name, ast.Constant)):
        return
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            validate_type_expression(item)
        return
    if isinstance(node, ast.Subscript):
        if not isinstance(node.value, ast.Name):
            raise ValueError("schema alias subscript owner must be a direct name")
        arguments = subscript_arguments(node)
        owner = node.value.id
        if owner in {"tuple", "list", "set", "frozenset"}:
            validate_collection_arguments(owner, arguments)
            for index, argument in enumerate(arguments):
                if (
                    owner == "tuple"
                    and index == 1
                    and isinstance(argument, ast.Constant)
                    and argument.value is Ellipsis
                ):
                    continue
                validate_type_expression(argument)
            return
        if owner == "dict":
            validate_map_arguments(arguments)
            for argument in arguments:
                validate_type_expression(argument)
            return
        if owner == "Literal":
            # Literal members are data, never quoted forward references.
            for argument in arguments:
                validate_data_expression(argument)
            return
        if owner == "Annotated":
            if not arguments:
                raise ValueError("Annotated requires a projected type")
            validate_type_expression(arguments[0])
            for metadata in arguments[1:]:
                validate_field_data_expression(metadata)
            return
        for argument in arguments:
            validate_type_expression(argument)
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        validate_type_expression(node.left)
        validate_type_expression(node.right)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        validate_type_expression(node.operand)
        return
    raise ValueError(f"unsupported type expression: {ast.unparse(node)}")


def annotated_parts(node: ast.expr) -> tuple[ast.expr, list[ast.expr]] | None:
    if not (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Annotated"
    ):
        return None
    arguments = (
        list(node.slice.elts)
        if isinstance(node.slice, ast.Tuple)
        else [node.slice]
    )
    if not arguments:
        raise ValueError("Annotated requires a projected type")
    return arguments[0], arguments[1:]


def subscript_arguments(node: ast.Subscript) -> list[ast.expr]:
    """Return the syntax-level arguments of a direct-name generic."""
    return list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]


def validate_collection_arguments(container: str, arguments: list[ast.expr]) -> None:
    """Enforce the closed CTV collection declaration grammar before projection."""
    ellipsis_indexes = [
        index
        for index, argument in enumerate(arguments)
        if isinstance(argument, ast.Constant) and argument.value is Ellipsis
    ]
    if container in {"list", "set", "frozenset"}:
        if len(arguments) != 1 or ellipsis_indexes:
            raise ValueError(f"{container} annotation requires exactly one item")
        return
    if container == "tuple":
        if not ellipsis_indexes:
            return
        if len(arguments) != 2 or ellipsis_indexes != [1]:
            raise ValueError(
                "tuple annotation must use finite items or exactly tuple[T, ...]"
            )


def validate_map_arguments(arguments: list[ast.expr]) -> None:
    """Maps are closed binary generic declarations before projection decides reachability."""
    if len(arguments) != 2 or any(
        isinstance(argument, ast.Constant) and argument.value is Ellipsis
        for argument in arguments
    ):
        raise ValueError("dict annotation requires exactly two type arguments")


def validate_annotated_metadata(
    metadata: list[ast.expr], metadata_owner: str | None
) -> None:
    if metadata_owner != "TraceabilityGenerationMember" or len(metadata) != 1:
        raise ValueError("Annotated requires one exact CTV routing metadata item")
    item = metadata[0]
    if (
        not isinstance(item, ast.Call)
        or not isinstance(item.func, ast.Name)
        or item.func.id != "Field"
        or item.args
        or len(item.keywords) != 1
        or item.keywords[0].arg != "discriminator"
        or not isinstance(item.keywords[0].value, ast.Constant)
        or item.keywords[0].value.value != "artifact_kind"
    ):
        raise ValueError(
            "unsupported Annotated metadata; only TraceabilityGenerationMember "
            "Field(discriminator='artifact_kind') routing metadata is permitted"
        )


def unwrap_annotated(
    node: ast.expr, metadata_owner: str | None
) -> ast.expr | None:
    parts = annotated_parts(node)
    if parts is None:
        return None
    projected, metadata = parts
    validate_annotated_metadata(metadata, metadata_owner)
    return projected


def parse_field_call(node: ast.Call) -> dict[str, Any]:
    if not isinstance(node.func, ast.Name) or node.func.id != "Field":
        raise ValueError("model field default must be Field(...)")
    if node.args:
        raise ValueError("Field(...) positional defaults are unsupported")
    allowed = {"default", "ge", "gt", "le"}
    seen: set[str] = set()
    constraints: dict[str, int] = {}
    default: dict[str, Any] = {"kind": "required"}
    for keyword in node.keywords:
        if keyword.arg is None:
            raise ValueError("Field(...) **kwargs are unsupported")
        if keyword.arg not in allowed or keyword.arg in seen:
            raise ValueError(f"unsupported or duplicate Field keyword: {keyword.arg}")
        seen.add(keyword.arg)
        value = ast.literal_eval(keyword.value)
        if keyword.arg == "default":
            if value is not None and not isinstance(value, (str, bool, int)):
                raise ValueError("Field default must be a canonical literal scalar")
            default = {"kind": "literal", "value": value}
        else:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"Field {keyword.arg} must be an integer literal")
            constraints[keyword.arg] = value
    return {"constraints": constraints, "default": default}


def parse_literal_default(node: ast.expr) -> dict[str, Any]:
    """Normalize a direct scalar default exactly like ``Field(default=...)``."""
    try:
        value = ast.literal_eval(node)
    except ValueError as error:
        raise ValueError("model field default must be a canonical literal scalar") from error
    if value is not None and not isinstance(value, (str, bool, int)):
        raise ValueError("model field default must be a canonical literal scalar")
    if isinstance(value, float) or isinstance(value, int) and isinstance(value, bool):
        raise ValueError("model field default must be a canonical literal scalar")
    return {"constraints": {}, "default": {"kind": "literal", "value": value}}


def is_frozen_forbid_model_config(node: ast.stmt) -> bool:
    if not (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "model_config"
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "ConfigDict"
        and not node.value.args
    ):
        return False
    keywords = {keyword.arg: keyword.value for keyword in node.value.keywords}
    return (
        set(keywords) == {"extra", "frozen"}
        and isinstance(keywords["extra"], ast.Constant)
        and keywords["extra"].value == "forbid"
        and isinstance(keywords["frozen"], ast.Constant)
        and keywords["frozen"].value is True
    )


def validate_protocol_method(node: ast.FunctionDef) -> None:
    if (
        node.decorator_list
        or getattr(node, "type_params", ())
        or node.args.posonlyargs
        or node.args.vararg is not None
        or node.args.kwarg is not None
        or node.args.defaults
        or any(value is not None for value in node.args.kw_defaults)
        or len(node.body) != 1
        or not isinstance(node.body[0], ast.Expr)
        or not isinstance(node.body[0].value, ast.Constant)
        or node.body[0].value.value is not Ellipsis
        or node.returns is None
    ):
        raise ValueError(f"{node.name}: unsupported Protocol method shape")
    for argument in (*node.args.args, *node.args.kwonlyargs):
        if argument.arg == "self" and argument.annotation is None:
            continue
        if argument.annotation is None:
            raise ValueError(f"{node.name}: Protocol argument lacks annotation")
        validate_type_expression(argument.annotation)
    validate_type_expression(node.returns)


def validate_class_body(node: ast.ClassDef) -> str:
    base_node = node.bases[0] if node.bases else None
    base = base_node.id if isinstance(base_node, ast.Name) else ""
    if base == "Protocol":
        if node.name not in EXPECTED_PROTOCOL_CLASSES:
            raise ValueError(f"{node.name}: unregistered Protocol exception")
        for child in node.body:
            if not isinstance(child, ast.FunctionDef):
                raise ValueError(f"{node.name}: Protocol body must contain method stubs")
            validate_protocol_method(child)
        return "protocol"
    if base == "StrEnum":
        if node.name not in EXPECTED_STRENUM_CLASSES:
            raise ValueError(f"{node.name}: unregistered StrEnum exception")
        for child in node.body:
            if (
                not isinstance(child, ast.Assign)
                or len(child.targets) != 1
                or not isinstance(child.targets[0], ast.Name)
                or not isinstance(child.value, ast.Constant)
                or not isinstance(child.value.value, str)
            ):
                raise ValueError(f"{node.name}: StrEnum body must be string literals")
        return "strenum"
    for child in node.body:
        if is_frozen_forbid_model_config(child):
            continue
        if (
            not isinstance(child, ast.AnnAssign)
            or not isinstance(child.target, ast.Name)
            or child.simple != 1
        ):
            raise ValueError(
                f"{node.name}: model body must contain only simple annotated fields"
            )
        validate_type_expression(child.annotation)
        if child.value is not None:
            if isinstance(child.value, ast.Call):
                parse_field_call(child.value)
            else:
                parse_literal_default(child.value)
    return "model"


def validate_schema_module(tree: ast.Module) -> None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if (
                node.decorator_list
                or node.keywords
                or getattr(node, "type_params", ())
                or len(node.bases) > 1
                or any(not isinstance(base, ast.Name) for base in node.bases)
            ):
                raise ValueError(
                    f"{node.name}: unsupported class declaration shape"
                )
            validate_class_body(node)
            continue
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            validate_type_expression(node.value)
            continue
        raise ValueError(
            "schema fences permit only direct class declarations and "
            "single-name declarative aliases"
        )


def declarations(document: str) -> tuple[dict[str, ast.ClassDef], dict[str, ast.expr]]:
    classes: dict[str, ast.ClassDef] = {}
    aliases: dict[str, ast.expr] = {}
    declaration_kinds: dict[str, str] = {}
    for block in re.findall(r"```python\n(.*?)```", document, re.DOTALL):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        if not any(isinstance(node, ast.ClassDef) for node in tree.body):
            continue
        validate_schema_module(tree)
        if "BaseModel" in module_binding_names(tree):
            raise ValueError(
                "BaseModel must remain an unbound inert external model base"
            )
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if node.name in declaration_kinds:
                    raise ValueError(
                        f"duplicate schema identifier: {node.name} "
                        f"({declaration_kinds[node.name]}/class)"
                    )
                declaration_kinds[node.name] = "class"
                classes[node.name] = node
            elif (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                name = node.targets[0].id
                if name in declaration_kinds:
                    raise ValueError(
                        f"duplicate schema identifier: {name} "
                        f"({declaration_kinds[name]}/alias)"
                    )
                declaration_kinds[name] = "alias"
                aliases[name] = node.value
    protocol_classes = {
        name
        for name, node in classes.items()
        if len(node.bases) == 1
        and isinstance(node.bases[0], ast.Name)
        and node.bases[0].id == "Protocol"
    }
    strenum_classes = {
        name
        for name, node in classes.items()
        if len(node.bases) == 1
        and isinstance(node.bases[0], ast.Name)
        and node.bases[0].id == "StrEnum"
    }
    if protocol_classes != EXPECTED_PROTOCOL_CLASSES:
        raise ValueError("Protocol exception inventory differs from authority")
    if strenum_classes != EXPECTED_STRENUM_CLASSES:
        raise ValueError("StrEnum exception inventory differs from authority")
    return classes, aliases


def literal_member(node: ast.expr) -> Any:
    value = ast.literal_eval(node)
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return {"$type": "integer", "value": str(value)}
    raise ValueError(f"unsupported Literal member: {ast.unparse(node)}")


class Compiler:
    def __init__(
        self, classes: dict[str, ast.ClassDef], aliases: dict[str, ast.expr]
    ) -> None:
        if "BaseModel" in classes or "BaseModel" in aliases:
            raise ValueError("BaseModel must remain an undeclared inert external base")
        self.classes = classes
        self.aliases = aliases
        self.enum_registry: dict[str, list[Any]] = {}
        self.projected_classes: set[str] = set()
        self.projected_aliases: set[str] = set()
        self.alias_node_names = {id(node): name for name, node in aliases.items()}

    def validate_generation_member_union(self, node: ast.expr) -> None:
        def alternatives(value: ast.expr) -> list[ast.expr]:
            if isinstance(value, ast.BinOp) and isinstance(value.op, ast.BitOr):
                return alternatives(value.left) + alternatives(value.right)
            return [value]

        members = alternatives(node)
        if len(members) < 2 or any(not isinstance(member, ast.Name) for member in members):
            raise ValueError(
                "TraceabilityGenerationMember must wrap its exact model union"
            )
        names = tuple(member.id for member in members if isinstance(member, ast.Name))
        observed: list[tuple[str, str]] = []
        discriminator_values: set[str] = set()
        for name in names:
            if name not in self.classes:
                raise ValueError(f"{name}: generation union member is not a model")
            fields = [
                field
                for _owner, field_name, field in self.class_fields(name)
                if field_name == "artifact_kind"
            ]
            if len(fields) != 1:
                raise ValueError(
                    f"{name}: generation union member requires one artifact_kind"
                )
            annotation = fields[0].annotation
            if not (
                isinstance(annotation, ast.Subscript)
                and isinstance(annotation.value, ast.Name)
                and annotation.value.id == "Literal"
            ):
                raise ValueError(
                    f"{name}.artifact_kind must be a one-member Literal"
                )
            literal_members = (
                list(annotation.slice.elts)
                if isinstance(annotation.slice, ast.Tuple)
                else [annotation.slice]
            )
            if (
                len(literal_members) != 1
                or not isinstance(literal_members[0], ast.Constant)
                or not isinstance(literal_members[0].value, str)
            ):
                raise ValueError(
                    f"{name}.artifact_kind must be a one-string Literal"
                )
            discriminator = literal_members[0].value
            if discriminator in discriminator_values:
                raise ValueError(
                    f"duplicate generation discriminator: {discriminator}"
                )
            discriminator_values.add(discriminator)
            observed.append((name, discriminator))
        if tuple(observed) != EXPECTED_GENERATION_MEMBER_DISCRIMINATORS:
            raise ValueError(
                "TraceabilityGenerationMember alternatives differ from authority"
            )

    def unwrap_projected_annotated(
        self, node: ast.expr, metadata_owner: str | None
    ) -> ast.expr | None:
        projected = unwrap_annotated(node, metadata_owner)
        if projected is not None and metadata_owner == "TraceabilityGenerationMember":
            self.validate_generation_member_union(projected)
        return projected

    def class_fields(
        self, name: str, stack: tuple[str, ...] = ()
    ) -> list[tuple[str, str, ast.AnnAssign]]:
        if name in stack:
            raise ValueError(f"cyclic model inheritance: {' -> '.join(stack + (name,))}")
        node = self.classes[name]
        result: list[tuple[str, str, ast.AnnAssign]] = []
        positions: dict[str, int] = {}
        if len(node.bases) > 1:
            raise ValueError(f"{name}: multiple inheritance is unsupported")
        for base in node.bases:
            if not isinstance(base, ast.Name):
                raise ValueError(
                    f"{name}: qualified or generic base is unsupported: "
                    f"{ast.unparse(base)}"
                )
            if base.id == "BaseModel":
                continue
            if base.id not in self.classes:
                raise ValueError(f"{name}: unknown model base: {base.id}")
            self.projected_classes.add(base.id)
            for owner, field, declared in self.class_fields(
                base.id, stack + (name,)
            ):
                positions[field] = len(result)
                result.append((owner, field, declared))
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                field = child.target.id
                if field in positions:
                    result[positions[field]] = (name, field, child)
                else:
                    positions[field] = len(result)
                    result.append((name, field, child))
        return result

    def resolved_literals(
        self,
        node: ast.expr,
        stack: frozenset[str],
        metadata_owner: str | None,
    ) -> list[ast.expr]:
        if isinstance(node, ast.Name) and node.id in self.aliases:
            if node.id in stack:
                raise ValueError(f"recursive alias: {node.id}")
            return self.resolved_literals(
                self.aliases[node.id], stack | {node.id}, node.id
            )
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Literal"
        ):
            return (
                list(node.slice.elts)
                if isinstance(node.slice, ast.Tuple)
                else [node.slice]
            )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self.resolved_literals(
                node.left, stack, metadata_owner
            ) + self.resolved_literals(node.right, stack, metadata_owner)
        projected = self.unwrap_projected_annotated(node, metadata_owner)
        if projected is not None:
            return self.resolved_literals(projected, stack, metadata_owner)
        return []

    def register_enum(self, schema: str, nodes: list[ast.expr]) -> list[Any]:
        members: list[Any] = []
        identities: set[bytes] = set()
        for node in nodes:
            member = literal_member(node)
            identity = canonical(member)
            if identity in identities:
                raise ValueError(f"{schema}: duplicate typed Literal member")
            identities.add(identity)
            members.append(member)
        if not members:
            raise ValueError(f"{schema}: empty Literal")
        previous = self.enum_registry.setdefault(schema, members)
        if canonical(previous) != canonical(members):
            raise ValueError(f"{schema}: conflicting enum registry row")
        return members

    def field_policy(self, field: ast.AnnAssign) -> dict[str, Any]:
        if field.value is None:
            return {"constraints": {}, "default": {"kind": "required"}}
        if isinstance(field.value, ast.Call):
            return parse_field_call(field.value)
        return parse_literal_default(field.value)

    def normalize(
        self,
        node: ast.expr,
        *,
        owner: str | None = None,
        field: str | None = None,
        model_stack: tuple[str, ...] = (),
        alias_stack: tuple[str, ...] = (),
    ) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                parsed = ast.parse(node.value, mode="eval").body
            except SyntaxError as error:
                raise ValueError(f"invalid forward reference: {node.value}") from error
            return self.normalize(
                parsed,
                owner=owner,
                field=field,
                model_stack=model_stack,
                alias_stack=alias_stack,
            )
        if isinstance(node, ast.Constant) and node.value is None:
            return {"kind": "null"}
        if isinstance(node, ast.Name):
            name = node.id
            if name in {"str", "bool", "int", "bytes", "datetime", "timedelta"}:
                return {"kind": "scalar", "name": name}
            if name in {"Any", "object"}:
                raise ValueError(f"unsupported open annotation: {name}")
            if name == "None":
                return {"kind": "null"}
            if name in self.aliases:
                self.projected_aliases.add(name)
                if name in alias_stack:
                    raise ValueError(f"recursive alias: {name}")
                literals = self.resolved_literals(
                    self.aliases[name], frozenset({name}), name
                )
                if literals:
                    return {
                        "kind": "enum",
                        "members": self.register_enum(name, literals),
                        "schema": name,
                    }
                return self.normalize(
                    self.aliases[name],
                    model_stack=model_stack,
                    alias_stack=alias_stack + (name,),
                )
            if name in self.classes:
                self.projected_classes.add(name)
                base = self.classes[name].bases
                if (
                    len(base) == 1
                    and isinstance(base[0], ast.Name)
                    and base[0].id in {"Protocol", "StrEnum"}
                ):
                    raise ValueError(
                        f"{name}: Protocol/StrEnum is outside the CTV projection"
                    )
                if name in model_stack:
                    return {"kind": "model_ref", "name": name}
                fields = []
                for declaring_owner, field_name, declared in self.class_fields(name):
                    fields.append(
                        {
                            "annotation": self.normalize(
                                declared.annotation,
                                owner=declaring_owner,
                                field=field_name,
                                model_stack=model_stack + (name,),
                                alias_stack=alias_stack,
                            ),
                            "declaring_owner": declaring_owner,
                            "field_name": field_name,
                            **self.field_policy(declared),
                        }
                    )
                return {"fields": fields, "kind": "model", "name": name}
            raise ValueError(f"unresolved annotation: {name}")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            alternatives = [
                self.normalize(
                    node.left,
                    owner=owner,
                    field=field,
                    model_stack=model_stack,
                    alias_stack=alias_stack,
                ),
                self.normalize(
                    node.right,
                    owner=owner,
                    field=field,
                    model_stack=model_stack,
                    alias_stack=alias_stack,
                ),
            ]
            alternatives.sort(key=canonical)
            if len({canonical(item) for item in alternatives}) != len(alternatives):
                raise ValueError("duplicate union alternative")
            return {"alternatives": alternatives, "kind": "union"}
        if isinstance(node, ast.Subscript):
            container = node.value.id if isinstance(node.value, ast.Name) else ""
            arguments = subscript_arguments(node)
            if container == "Literal":
                if owner is None or field is None:
                    raise ValueError("inline Literal has no declaring field")
                schema = f"{owner}.{field}"
                return {
                    "kind": "enum",
                    "members": self.register_enum(schema, arguments),
                    "schema": schema,
                }
            if container == "Annotated":
                projected = self.unwrap_projected_annotated(
                    node, self.alias_node_names.get(id(node))
                )
                if projected is None:
                    raise AssertionError("Annotated dispatch lost its wrapper")
                return self.normalize(
                    projected,
                    owner=owner,
                    field=field,
                    model_stack=model_stack,
                    alias_stack=alias_stack,
                )
            if container in {"tuple", "list", "set", "frozenset"}:
                validate_collection_arguments(container, arguments)
                normalized = []
                for argument in arguments:
                    if isinstance(argument, ast.Constant) and argument.value is Ellipsis:
                        continue
                    validate_type_expression(argument)
                    normalized.append(
                        self.normalize(
                            argument,
                            owner=owner,
                            field=field,
                            model_stack=model_stack,
                            alias_stack=alias_stack,
                        )
                    )
                return {
                    "items": normalized,
                    "kind": "collection",
                    "name": container,
                    "variadic": container != "tuple" or (
                        len(arguments) == 2
                        and isinstance(arguments[1], ast.Constant)
                        and arguments[1].value is Ellipsis
                    ),
                }
            if container == "dict":
                validate_map_arguments(arguments)
                key = self.normalize(arguments[0], model_stack=model_stack)
                if key != {"kind": "scalar", "name": "str"}:
                    raise ValueError("only string-keyed maps are supported")
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
            raise ValueError(f"unsupported generic annotation: {ast.unparse(node)}")
        raise ValueError(f"unsupported annotation: {ast.unparse(node)}")


def compile_authority(design_bytes: bytes, registry_bytes: bytes) -> dict[str, Any]:
    if not design_bytes or not registry_bytes:
        raise ValueError("design and registry inputs must be non-empty")
    design = design_bytes.decode("utf-8")
    grammar = marked(design, "SIA-CTV-GRAMMAR-V2", "text")
    grammar_rows = parse_closed_grammar(grammar)
    inventory_bytes = marked(
        design, "SIA-TRACEABILITY-SCHEMA-INVENTORY-V1", "text"
    )
    enum_marked = marked(design, "SIA-CTV-ENUM-REGISTRY-V2", "json")
    inventory = inventory_bytes.decode("ascii").splitlines()
    if len(inventory) != 56 or inventory != sorted(set(inventory)):
        raise ValueError("schema inventory must contain 56 sorted unique coordinates")
    classes, aliases = declarations(design)
    compiler = Compiler(classes, aliases)
    schemas = []
    for coordinate in inventory:
        declared_name = REGISTRY_ROOTS.get(
            coordinate.removesuffix(".v1"), coordinate.removesuffix(".v1")
        )
        if declared_name not in classes and declared_name not in aliases:
            raise ValueError(f"{coordinate}: root declaration is absent")
        graph = compiler.normalize(ast.Name(id=declared_name))
        graph_bytes = canonical(graph)
        fingerprint_preimage = (
            b"memorii:sia-ctv-schema-fingerprint:v2\0"
            + lp(coordinate)
            + lp(graph_bytes)
        )
        fingerprint = hashlib.sha256(fingerprint_preimage).hexdigest()
        schemas.append(
            {
                "binding_digest": "",
                "binding_preimage_base64": "",
                "coordinate": coordinate,
                "declared_root": declared_name,
                "normalized_graph": graph,
                "normalized_graph_bytes_base64": base64.b64encode(
                    graph_bytes
                ).decode("ascii"),
                "schema_fingerprint": fingerprint,
                "schema_fingerprint_preimage_base64": base64.b64encode(
                    fingerprint_preimage
                ).decode("ascii"),
            }
        )
    parsed_enum = strict_json_loads(enum_marked)
    compiled_enum = dict(sorted(compiler.enum_registry.items()))
    if canonical(parsed_enum) != canonical(compiled_enum):
        raise ValueError(
            "marked enum registry is not the exhaustive compiled registry: "
            f"missing={sorted(set(parsed_enum) - set(compiled_enum))[:8]} "
            f"extra={sorted(set(compiled_enum) - set(parsed_enum))[:8]} "
            f"counts={len(parsed_enum)}/{len(compiled_enum)}"
        )
    enum_bytes = canonical(compiled_enum)
    grammar_preimage = b"memorii:sia-ctv-grammar:v2\0" + grammar
    grammar_digest = hashlib.sha256(grammar_preimage).hexdigest()
    enum_preimage = b"memorii:sia-ctv-enum-registry:v2\0" + enum_bytes
    enum_digest = hashlib.sha256(enum_preimage).hexdigest()
    profile_preimage = b"".join(
        (
            b"memorii:sia-ctv-profile:v2\0",
            lp(grammar_rows["profile_id"]),
            lp(grammar_rows["profile_version"]),
            lp("sia-ctv-grammar-v2"),
            lp(grammar_digest),
            lp(grammar),
            lp("sia-ctv-enum-registry-v2"),
            lp(enum_digest),
            lp(enum_bytes),
        )
    )
    profile_digest = hashlib.sha256(profile_preimage).hexdigest()
    for schema in schemas:
        binding_preimage = b"".join(
            (
                b"memorii:sia-ctv-binding:v2\0",
                lp(grammar_rows["profile_id"]),
                lp(grammar_rows["profile_version"]),
                lp(profile_digest),
                lp(schema["coordinate"]),
                lp(SCHEMA_VERSION),
                lp(schema["schema_fingerprint"]),
            )
        )
        schema["binding_preimage_base64"] = base64.b64encode(
            binding_preimage
        ).decode("ascii")
        schema["binding_digest"] = hashlib.sha256(binding_preimage).hexdigest()
    return {
        "enum_registry": {
            "canonical_bytes_base64": base64.b64encode(enum_bytes).decode("ascii"),
            "digest": enum_digest,
            "digest_preimage_base64": base64.b64encode(enum_preimage).decode(
                "ascii"
            ),
            "rows": compiled_enum,
        },
        "format": FORMAT,
        "grammar": {
            "digest": grammar_digest,
            "digest_preimage_base64": base64.b64encode(grammar_preimage).decode(
                "ascii"
            ),
            "payload": grammar.decode("ascii"),
            "payload_base64": base64.b64encode(grammar).decode("ascii"),
            "revision": "sia-ctv-grammar-v2",
        },
        "inventory": inventory,
        "profile": {
            "digest": profile_digest,
            "id": PROFILE_ID,
            "preimage_base64": base64.b64encode(profile_preimage).decode("ascii"),
            "version": 2,
        },
        "schemas": schemas,
        "source_design_sha256": v2_source_design_sha256(design),
        "source_registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
    }


def validate_closed_authority(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("authority root must be an object")
    expected = {
        "enum_registry",
        "format",
        "grammar",
        "inventory",
        "profile",
        "schemas",
        "source_design_sha256",
        "source_registry_sha256",
    }
    if set(value) != expected or value["format"] != FORMAT:
        raise ValueError("authority root is incomplete or has unknown fields")
    if len(value["schemas"]) != 56 or len(value["inventory"]) != 56:
        raise ValueError("authority must contain exactly 56 coordinates")
    coordinates = [item["coordinate"] for item in value["schemas"]]
    if coordinates != value["inventory"] or coordinates != sorted(set(coordinates)):
        raise ValueError("authority schema order/uniqueness mismatch")
    if value["profile"]["version"] != 2:
        raise ValueError("v1 substitution is forbidden")


def validate_candidate(value: Any, expected_bytes: bytes) -> None:
    validate_closed_authority(value)
    if canonical(value) != expected_bytes:
        raise ValueError("authority differs from independent design compilation")


def assert_source_change_detected(
    design_bytes: bytes,
    registry_bytes: bytes,
    expected_bytes: bytes,
    label: str,
) -> None:
    try:
        changed = canonical(compile_authority(design_bytes, registry_bytes))
    except (UnicodeDecodeError, ValueError):
        return
    if changed == expected_bytes:
        raise AssertionError(f"source mutation was not detected: {label}")


def assert_source_rejected(
    design_bytes: bytes, registry_bytes: bytes, label: str
) -> None:
    try:
        compile_authority(design_bytes, registry_bytes)
    except (UnicodeDecodeError, ValueError):
        return
    raise AssertionError(f"invalid source mutation was accepted: {label}")


def adversarial_self_test(
    authority: dict[str, Any],
    expected_bytes: bytes,
    design_bytes: bytes,
    registry_bytes: bytes,
    scratch_parent: Path,
    scratch_name: str,
) -> None:
    scratch_parent = scratch_parent.resolve()
    mutations = []
    candidate = deepcopy(authority)
    candidate["profile"]["version"] = 1
    mutations.append(candidate)
    candidate = deepcopy(authority)
    candidate["unexpected_root"] = None
    mutations.append(candidate)
    candidate = deepcopy(authority)
    candidate["schemas"].pop()
    mutations.append(candidate)
    candidate = deepcopy(authority)
    first_enum = next(iter(candidate["enum_registry"]["rows"]))
    candidate["enum_registry"]["rows"][first_enum].append("not-declared")
    mutations.append(candidate)
    candidate = deepcopy(authority)
    candidate["schemas"][0]["binding_digest"] = "0" * 64
    mutations.append(candidate)
    candidate = deepcopy(authority)
    candidate["grammar"]["revision"] = "sia-ctv-grammar-v1"
    mutations.append(candidate)
    for index, mutation in enumerate(mutations):
        try:
            validate_candidate(mutation, expected_bytes)
        except ValueError:
            continue
        raise AssertionError(f"adversarial authority mutation {index} was accepted")

    first_root_key = next(iter(sorted(authority)))
    duplicate_root = (
        "{"
        + json.dumps(first_root_key, ensure_ascii=True)
        + ":"
        + json.dumps(
            authority[first_root_key],
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + ","
    ).encode("ascii") + expected_bytes[1:]
    schema_binding = authority["schemas"][0]["binding_digest"]
    nested_member = (
        '"binding_digest":'
        + json.dumps(schema_binding, ensure_ascii=True)
    ).encode("ascii")
    duplicate_nested = expected_bytes.replace(
        nested_member, nested_member + b"," + nested_member, 1
    )
    for label, duplicate_json in (
        ("duplicate checked-authority root key", duplicate_root),
        ("duplicate checked-authority schema-row key", duplicate_nested),
    ):
        try:
            strict_json_loads(duplicate_json)
        except ValueError:
            continue
        raise AssertionError(f"{label} passed strict JSON parsing")

    document = design_bytes.decode("utf-8")
    grammar = marked(document, "SIA-CTV-GRAMMAR-V2", "text")
    grammar_lines = grammar.decode("ascii").splitlines()
    for index, line in enumerate(grammar_lines):
        missing = grammar_lines[:index] + grammar_lines[index + 1 :]
        assert_source_change_detected(
            replace_marked(
                document,
                "SIA-CTV-GRAMMAR-V2",
                "text",
                ("\n".join(missing) + "\n").encode("ascii"),
            ).encode("utf-8"),
            registry_bytes,
            expected_bytes,
            f"grammar row missing: {line}",
        )
        key, value = line.split("=", 1)
        altered = grammar_lines.copy()
        altered[index] = f"{key}={value}-altered"
        assert_source_change_detected(
            replace_marked(
                document,
                "SIA-CTV-GRAMMAR-V2",
                "text",
                ("\n".join(altered) + "\n").encode("ascii"),
            ).encode("utf-8"),
            registry_bytes,
            expected_bytes,
            f"grammar row altered: {key}",
        )
    for label, lines in (
        ("grammar extra", grammar_lines + ["unexpected=reject"]),
        ("grammar duplicate", grammar_lines + [grammar_lines[0]]),
    ):
        assert_source_change_detected(
            replace_marked(
                document,
                "SIA-CTV-GRAMMAR-V2",
                "text",
                ("\n".join(lines) + "\n").encode("ascii"),
            ).encode("utf-8"),
            registry_bytes,
            expected_bytes,
            label,
        )
    for key, replacement in (
        ("profile_id", "semantic_ingestion_typed_value_substituted"),
        ("profile_version", "1"),
    ):
        altered = [
            f"{key}={replacement}" if row.startswith(f"{key}=") else row
            for row in grammar_lines
        ]
        assert_source_change_detected(
            replace_marked(
                document,
                "SIA-CTV-GRAMMAR-V2",
                "text",
                ("\n".join(altered) + "\n").encode("ascii"),
            ).encode("utf-8"),
            registry_bytes,
            expected_bytes,
            f"{key} substitution",
        )

    for label, changed_document in (
        (
            "v2 marker missing",
            document.replace(
                "`[SIA-CTV-GRAMMAR-V2-BEGIN]`",
                "`[SIA-CTV-GRAMMAR-V2-REMOVED]`",
                1,
            ),
        ),
        (
            "v2 marker substituted",
            document.replace(
                "`[SIA-CTV-GRAMMAR-V2-BEGIN]`",
                "`[SIA-CTV-GRAMMAR-V1-BEGIN]`",
                1,
            ).replace(
                "`[SIA-CTV-GRAMMAR-V2-END]`",
                "`[SIA-CTV-GRAMMAR-V1-END]`",
                1,
            ),
        ),
    ):
        assert_source_change_detected(
            changed_document.encode("utf-8"),
            registry_bytes,
            expected_bytes,
            label,
        )

    v1_payload = marked(document, "SIA-CTV-ENUM-REGISTRY-V1", "json")
    v1_changed_document = replace_marked(
        document,
        "SIA-CTV-ENUM-REGISTRY-V1",
        "json",
        v1_payload.replace(b"\n", b"\n ", 1),
    )
    if canonical(
        compile_authority(v1_changed_document.encode("utf-8"), registry_bytes)
    ) != expected_bytes:
        raise AssertionError("v1-only mutation changed v2 authority")

    v2_payload = marked(document, "SIA-CTV-ENUM-REGISTRY-V2", "json")
    v2_changed_document = replace_marked(
        document,
        "SIA-CTV-ENUM-REGISTRY-V2",
        "json",
        v2_payload.replace(b"\n", b"\n ", 1),
    )
    if marked(v2_changed_document, "SIA-CTV-ENUM-REGISTRY-V1", "json") != v1_payload:
        raise AssertionError("v2 mutation changed v1 baseline bytes")
    assert_source_change_detected(
        v2_changed_document.encode("utf-8"),
        registry_bytes,
        expected_bytes,
        "v2 enum registry mutation",
    )
    parsed_v2_enum = strict_json_loads(v2_payload)
    unicode_literal_anchor = (
        '    execution_result: Literal["pass", "fail", "indeterminate"]\n'
        "    result_artifact_digest: str | None"
    )
    if document.count(unicode_literal_anchor) != 1:
        raise AssertionError("Unicode scalar self-test declaration anchor is not unique")
    unicode_schema = "NormativeExecutionEvidenceRecordBody.execution_result"
    if parsed_v2_enum.get(unicode_schema) != ["pass", "fail", "indeterminate"]:
        raise AssertionError("Unicode scalar self-test enum row changed")
    unicode_document = document.replace(
        unicode_literal_anchor,
        '    execution_result: Literal["pass", "fail", "indeterminate", "caf\u00e9", "cafe\u0301"]\n'
        "    result_artifact_digest: str | None",
        1,
    )
    unicode_enum = deepcopy(parsed_v2_enum)
    unicode_enum[unicode_schema].extend(("caf\u00e9", "cafe\u0301"))
    unicode_document = replace_marked(
        unicode_document,
        "SIA-CTV-ENUM-REGISTRY-V2",
        "json",
        canonical(unicode_enum),
    )
    unicode_authority = canonical(
        compile_authority(unicode_document.encode("utf-8"), registry_bytes)
    )
    unicode_payload = marked(
        unicode_document, "SIA-CTV-ENUM-REGISTRY-V2", "json"
    )
    if unicode_payload != canonical(unicode_enum):
        raise AssertionError("marked Unicode payload was not preserved exactly")
    for literal in (b"caf\xc3\xa9", b"cafe\xcc\x81"):
        if literal not in unicode_payload or literal not in unicode_authority:
            raise AssertionError("valid Unicode scalar was not emitted as strict UTF-8")
    composed = "caf\u00e9"
    decomposed = "cafe\u0301"
    if composed == decomposed or composed.encode("utf-8") == decomposed.encode("utf-8"):
        raise AssertionError("Unicode normalization collapsed distinct scalar sequences")
    recursive_unicode_value = {
        composed: {"nested": [composed, decomposed]},
        decomposed: [composed, decomposed],
    }
    expected_recursive_unicode = (
        b'{"cafe\xcc\x81":["caf\xc3\xa9","cafe\xcc\x81"],'
        b'"caf\xc3\xa9":{"nested":["caf\xc3\xa9","cafe\xcc\x81"]}}\n'
    )
    recursive_unicode_bytes = canonical(recursive_unicode_value)
    if (
        recursive_unicode_bytes != expected_recursive_unicode
        or recursive_unicode_bytes.count(b"\n") != 1
        or not recursive_unicode_bytes.endswith(b"\n")
    ):
        raise AssertionError("recursive Unicode canonical form drifted")
    for label, value in (
        ("canonical value surrogate", {"value": chr(0xD800)}),
        ("canonical key surrogate", {chr(0xD800): "value"}),
        ("canonical nested surrogate", ["value", {"nested": chr(0xD800)}]),
    ):
        try:
            canonical(value)
        except ValueError:
            continue
        raise AssertionError(f"Unicode scalar rejection failed: {label}")
    for label, payload in (
        ("escaped surrogate JSON", b'{"value":"\\ud800"}'),
        ("invalid UTF-8 JSON", b'{"value":"\xed\xa0\x80"}'),
    ):
        try:
            strict_json_loads(payload)
        except (UnicodeDecodeError, ValueError):
            continue
        raise AssertionError(f"Unicode scalar JSON rejection failed: {label}")
    marked_surrogate_document = (
        "`[SIA-CTV-UNICODE-TEST-BEGIN]`\n```json\n"
        + chr(0xD800)
        + "\n```\n`[SIA-CTV-UNICODE-TEST-END]`"
    )
    try:
        marked(marked_surrogate_document, "SIA-CTV-UNICODE-TEST", "json")
    except ValueError:
        pass
    else:
        raise AssertionError("marked payload accepted a Unicode surrogate")
    assert_source_rejected(
        unicode_document.encode("utf-8").replace(b"caf\xc3\xa9", b"\xed\xa0\x80", 1),
        registry_bytes,
        "invalid UTF-8 design source",
    )
    duplicate_key = next(iter(parsed_v2_enum))
    duplicate_prefix = (
        "{"
        + json.dumps(duplicate_key, ensure_ascii=True)
        + ":"
        + json.dumps(
            parsed_v2_enum[duplicate_key],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        + ","
    ).encode("ascii")
    duplicate_enum_payload = duplicate_prefix + canonical(parsed_v2_enum)[1:]
    assert_source_rejected(
        replace_marked(
            document,
            "SIA-CTV-ENUM-REGISTRY-V2",
            "json",
            duplicate_enum_payload,
        ).encode("utf-8"),
        registry_bytes,
        "duplicate complete v2 enum key",
    )
    assert_source_change_detected(
        design_bytes,
        registry_bytes + b" ",
        expected_bytes,
        "registry source identity mutation",
    )

    declared_root = authority["schemas"][0]["declared_root"]
    baseline_schema = authority["schemas"][0]
    base_model_declaration = f"class {declared_root}(BaseModel):"
    if document.count(base_model_declaration) != 1:
        raise AssertionError("BaseModel preservation fixture is not unique")

    def assert_declaration_collision_rejected(
        changed_document: str, label: str
    ) -> None:
        try:
            declarations(changed_document)
        except ValueError:
            return
        raise AssertionError(f"declaration collision was accepted: {label}")

    for member_name, _discriminator in EXPECTED_GENERATION_MEMBER_DISCRIMINATORS:
        assert_declaration_collision_rejected(
            document.replace(
                base_model_declaration,
                f"{member_name} = str\n\n{base_model_declaration}",
                1,
            ),
            f"tagged-union member shadow: {member_name}",
        )
    real_member_name = EXPECTED_GENERATION_MEMBER_DISCRIMINATORS[0][0]
    next_member_name = EXPECTED_GENERATION_MEMBER_DISCRIMINATORS[1][0]
    next_member_declaration = f"class {next_member_name}("
    if document.count(next_member_declaration) != 1:
        raise AssertionError("reverse class/alias fixture anchor is not unique")
    assert_declaration_collision_rejected(
        document.replace(
            next_member_declaration,
            f"{real_member_name} = str\n\n{next_member_declaration}",
            1,
        ),
        f"class-then-alias tagged-union member collision: {real_member_name}",
    )
    duplicate_class = (
        "class Layer1DuplicateSchema(BaseModel):\n"
        "    value: str\n\n"
        "class Layer1DuplicateSchema(BaseModel):\n"
        "    value: str\n\n"
        f"{base_model_declaration}"
    )
    assert_declaration_collision_rejected(
        document.replace(base_model_declaration, duplicate_class, 1),
        "identical class/class duplicate",
    )
    duplicate_alias = (
        "Layer1DuplicateAlias = str\n"
        "Layer1DuplicateAlias = str\n\n"
        f"{base_model_declaration}"
    )
    assert_declaration_collision_rejected(
        document.replace(base_model_declaration, duplicate_alias, 1),
        "identical alias/alias duplicate",
    )

    baseline_classes, baseline_aliases = declarations(document)
    projection = Compiler(baseline_classes, baseline_aliases)
    for schema in authority["schemas"]:
        projection.normalize(ast.Name(id=schema["declared_root"]))
    exception_classes = EXPECTED_PROTOCOL_CLASSES | EXPECTED_STRENUM_CLASSES
    if projection.projected_classes & exception_classes:
        raise AssertionError("Protocol/StrEnum exception entered CTV projection")
    default_none_fields = {
        (owner, child.target.id)
        for owner, node in baseline_classes.items()
        for child in node.body
        if isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
        and isinstance(child.value, ast.Call)
        and any(
            keyword.arg == "default"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is None
            for keyword in child.value.keywords
        )
    }
    if default_none_fields != EXPECTED_UNREACHABLE_DEFAULT_NONE_FIELDS:
        raise AssertionError("Field(default=None) exception inventory changed")
    if projection.projected_classes & {
        owner for owner, _field in default_none_fields
    }:
        raise AssertionError("current Field(default=None) field became reachable")

    collection_field = "layer1_collection_shape"
    scalar_str = {"kind": "scalar", "name": "str"}
    scalar_int = {"kind": "scalar", "name": "int"}
    for annotation, expected_collection in (
        (
            "list[str]",
            {"items": [scalar_str], "kind": "collection", "name": "list", "variadic": True},
        ),
        (
            "set[str]",
            {"items": [scalar_str], "kind": "collection", "name": "set", "variadic": True},
        ),
        (
            "frozenset[str]",
            {
                "items": [scalar_str],
                "kind": "collection",
                "name": "frozenset",
                "variadic": True,
            },
        ),
        (
            "tuple[str, int]",
            {
                "items": [scalar_str, scalar_int],
                "kind": "collection",
                "name": "tuple",
                "variadic": False,
            },
        ),
        (
            "tuple[str, ...]",
            {
                "items": [scalar_str],
                "kind": "collection",
                "name": "tuple",
                "variadic": True,
            },
        ),
        (
            "tuple[()]",
            {
                "items": [],
                "kind": "collection",
                "name": "tuple",
                "variadic": False,
            },
        ),
    ):
        collection_authority = compile_authority(
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n    {collection_field}: {annotation}",
                1,
            ).encode("utf-8"),
            registry_bytes,
        )
        collection_schema = next(
            schema
            for schema in collection_authority["schemas"]
            if schema["coordinate"] == baseline_schema["coordinate"]
        )
        collection_annotation = next(
            field["annotation"]
            for field in collection_schema["normalized_graph"]["fields"]
            if field["field_name"] == collection_field
        )
        if collection_annotation != expected_collection:
            raise AssertionError(
                f"collection normalization differs for {annotation}: "
                f"{collection_annotation!r}"
            )

    invalid_collection_annotations = (
        ("list multiple items", "list[str, int]"),
        ("list ellipsis", "list[...]"),
        ("set multiple items", "set[str, int]"),
        ("set ellipsis", "set[...]"),
        ("frozenset multiple items", "frozenset[str, int]"),
        ("frozenset ellipsis", "frozenset[...]"),
        ("tuple leading ellipsis", "tuple[..., str]"),
        ("tuple trailing extra item", "tuple[str, ..., int]"),
        ("tuple ellipsis only", "tuple[...]"),
        ("tuple two ellipses", "tuple[..., ...]"),
        ("tuple trailing duplicate ellipsis", "tuple[str, ..., ...]"),
        ("tuple leading and trailing ellipsis", "tuple[..., str, ...]"),
    )
    for label, annotation in invalid_collection_annotations:
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n    {collection_field}: {annotation}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            label,
        )
    for label, annotation in invalid_collection_annotations:
        quoted = repr(annotation)
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n    {collection_field}: {quoted}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            f"quoted {label}",
        )
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n"
                f"    {collection_field}: tuple[{quoted}, ...]",
                1,
            ).encode("utf-8"),
            registry_bytes,
            f"quoted nested {label}",
        )
        inherited_collection = (
            "class Layer1BadCollectionParent(BaseModel):\n"
            f"    {collection_field}: {quoted}\n\n"
            f"class {declared_root}(Layer1BadCollectionParent):"
        )
        assert_source_rejected(
            document.replace(base_model_declaration, inherited_collection, 1).encode(
                "utf-8"
            ),
            registry_bytes,
            f"quoted inherited {label}",
        )
    for label, alias in (
        ("alias list multiple items", "list[str, int]"),
        ("alias set multiple items", "set[str, int]"),
        ("alias frozenset multiple items", "frozenset[str, int]"),
        ("alias tuple leading ellipsis", "tuple[..., str]"),
    ):
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"Layer1BadCollection = {alias}\n\n{base_model_declaration}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            label,
        )
    for label, annotation in invalid_collection_annotations:
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"Layer1QuotedBadCollection = {annotation!r}\n\n"
                f"{base_model_declaration}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            f"quoted alias {label}",
        )

    valid_map_annotation = "dict[str, int]"
    valid_map_graph = {
        "key": scalar_str,
        "kind": "map",
        "value": scalar_int,
    }
    valid_nested_map_graph = {
        "items": [valid_map_graph],
        "kind": "collection",
        "name": "list",
        "variadic": True,
    }

    def assert_projected_map(
        route: str, changed_document: str, expected_annotation: dict[str, Any]
    ) -> None:
        candidate = compile_authority(changed_document.encode("utf-8"), registry_bytes)
        candidate_schema = next(
            schema
            for schema in candidate["schemas"]
            if schema["coordinate"] == baseline_schema["coordinate"]
        )
        candidate_field = next(
            field
            for field in candidate_schema["normalized_graph"]["fields"]
            if field["field_name"] == collection_field
        )
        if candidate_field["annotation"] != expected_annotation:
            raise AssertionError(f"valid dict[str, int] normalization changed: {route}")

    for route, changed_document, expected_annotation in (
        (
            "direct",
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n    {collection_field}: {valid_map_annotation}",
                1,
            ),
            valid_map_graph,
        ),
        (
            "whole quoted",
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n    {collection_field}: {valid_map_annotation!r}",
                1,
            ),
            valid_map_graph,
        ),
        (
            "nested list",
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n    {collection_field}: list[{valid_map_annotation}]",
                1,
            ),
            valid_nested_map_graph,
        ),
        (
            "reachable alias",
            document.replace(
                base_model_declaration,
                f"Layer1ValidMap = {valid_map_annotation}\n\n"
                f"{base_model_declaration}\n    {collection_field}: Layer1ValidMap",
                1,
            ),
            valid_map_graph,
        ),
        (
            "inherited field",
            document.replace(
                base_model_declaration,
                "class Layer1ValidMapParent(BaseModel):\n"
                f"    {collection_field}: {valid_map_annotation}\n\n"
                f"class {declared_root}(Layer1ValidMapParent):",
                1,
            ),
            valid_map_graph,
        ),
    ):
        assert_projected_map(route, changed_document, expected_annotation)
    protocol_anchor = "        release_bytes: bytes,"
    if document.count(protocol_anchor) != 1:
        raise AssertionError("Protocol map self-test anchor is not unique")
    protocol_return_anchor = "    ) -> VerifiedCapabilityBaselineApproval: ..."
    if document.count(protocol_return_anchor) != 1:
        raise AssertionError("Protocol map return self-test anchor is not unique")
    for label, invalid_map in (
        ("one argument", "dict[str]"),
        ("three arguments", "dict[str, int, bool]"),
    ):
        for route, changed_document in (
            (
                "direct",
                document.replace(
                    base_model_declaration,
                    f"{base_model_declaration}\n    {collection_field}: {invalid_map}",
                    1,
                ),
            ),
            (
                "quoted",
                document.replace(
                    base_model_declaration,
                    f"{base_model_declaration}\n    {collection_field}: {invalid_map!r}",
                    1,
                ),
            ),
            (
                "nested",
                document.replace(
                    base_model_declaration,
                    f"{base_model_declaration}\n    {collection_field}: list[{invalid_map}]",
                    1,
                ),
            ),
            (
                "alias",
                document.replace(
                    base_model_declaration,
                    f"Layer1BadMap = {invalid_map}\n\n{base_model_declaration}",
                    1,
                ),
            ),
            (
                "inherited",
                document.replace(
                    base_model_declaration,
                    "class Layer1BadMapParent(BaseModel):\n"
                    f"    {collection_field}: {invalid_map}\n\n"
                    f"class {declared_root}(Layer1BadMapParent):",
                    1,
                ),
            ),
            (
                "Protocol",
                document.replace(protocol_anchor, f"        release_bytes: {invalid_map},", 1),
            ),
        ):
            assert_source_rejected(
                changed_document.encode("utf-8"),
                registry_bytes,
                f"dict {label} {route}",
            )
    for route, changed_document in (
        (
            "unprojected alias",
            document.replace(
                base_model_declaration,
                f"Layer1ValidMap = {valid_map_annotation}\n\n{base_model_declaration}",
                1,
            ),
        ),
        (
            "Protocol argument",
            document.replace(
                protocol_anchor, f"        release_bytes: {valid_map_annotation},", 1
            ),
        ),
        (
            "Protocol return",
            document.replace(
                protocol_return_anchor,
                f"    ) -> {valid_map_annotation}: ...",
                1,
            ),
        ),
    ):
        nonprojected = compile_authority(changed_document.encode("utf-8"), registry_bytes)
        if canonical(nonprojected["schemas"]) != canonical(authority["schemas"]):
            raise AssertionError(f"valid {route} map entered CTV projection")

    for container in ("list", "set", "frozenset"):
        quoted_ellipsis = f'{container}["..."]'
        for label, annotation in (
            ("direct", quoted_ellipsis),
            ("quoted", repr(quoted_ellipsis)),
            ("nested", f"tuple[{quoted_ellipsis}, ...]"),
        ):
            assert_source_rejected(
                document.replace(
                    base_model_declaration,
                    f"{base_model_declaration}\n"
                    f"    {collection_field}: {annotation}",
                    1,
                ).encode("utf-8"),
                registry_bytes,
                f"{container} quoted-child ellipsis {label}",
            )
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"Layer1QuotedEllipsis = {quoted_ellipsis}\n\n"
                f"{base_model_declaration}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            f"{container} quoted-child ellipsis alias",
        )
        inherited_ellipsis = (
            "class Layer1QuotedEllipsisParent(BaseModel):\n"
            f"    {collection_field}: {quoted_ellipsis}\n\n"
            f"class {declared_root}(Layer1QuotedEllipsisParent):"
        )
        assert_source_rejected(
            document.replace(base_model_declaration, inherited_ellipsis, 1).encode(
                "utf-8"
            ),
            registry_bytes,
            f"{container} quoted-child ellipsis inherited",
        )

    for quoted_tuple_child in (
        'tuple["...", str]',
        'tuple[str, "..."]',
        'tuple["...", ...]',
        'tuple[..., "..."]',
    ):
        for label, annotation in (
            ("direct", quoted_tuple_child),
            ("whole quoted", repr(quoted_tuple_child)),
            ("nested", f"list[{quoted_tuple_child}]"),
        ):
            assert_source_rejected(
                document.replace(
                    base_model_declaration,
                    f"{base_model_declaration}\n"
                    f"    {collection_field}: {annotation}",
                    1,
                ).encode("utf-8"),
                registry_bytes,
                f"tuple quoted-child ellipsis {quoted_tuple_child} {label}",
            )
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"Layer1TupleQuotedEllipsis = {quoted_tuple_child}\n\n"
                f"{base_model_declaration}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            f"tuple quoted-child ellipsis {quoted_tuple_child} alias",
        )
        inherited_tuple = (
            "class Layer1TupleQuotedEllipsisParent(BaseModel):\n"
            f"    {collection_field}: {quoted_tuple_child}\n\n"
            f"class {declared_root}(Layer1TupleQuotedEllipsisParent):"
        )
        assert_source_rejected(
            document.replace(base_model_declaration, inherited_tuple, 1).encode(
                "utf-8"
            ),
            registry_bytes,
            f"tuple quoted-child ellipsis {quoted_tuple_child} inherited",
        )

    for container in ("list", "set", "frozenset", "tuple"):
        field_type = f"{container}[Field(default=None)]"
        quoted_field_type = f'{container}["Field(default=None)"]'
        for label, annotation in (
            ("direct", field_type),
            ("quoted", quoted_field_type),
            ("nested", f"tuple[{field_type}, ...]"),
        ):
            assert_source_rejected(
                document.replace(
                    base_model_declaration,
                    f"{base_model_declaration}\n"
                    f"    {collection_field}: {annotation}",
                    1,
                ).encode("utf-8"),
                registry_bytes,
                f"{container} Field-as-type {label}",
            )
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"Layer1FieldAsType = {field_type}\n\n{base_model_declaration}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            f"{container} Field-as-type alias",
        )
        inherited_field = (
            "class Layer1FieldAsTypeParent(BaseModel):\n"
            f"    {collection_field}: {field_type}\n\n"
            f"class {declared_root}(Layer1FieldAsTypeParent):"
        )
        assert_source_rejected(
            document.replace(base_model_declaration, inherited_field, 1).encode(
                "utf-8"
            ),
            registry_bytes,
            f"{container} Field-as-type inherited",
        )

    for annotation in ('"list[str]"', '"tuple[str, int]"', '"tuple[str, ...]"'):
        compile_authority(
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n    {collection_field}: {annotation}",
                1,
            ).encode("utf-8"),
            registry_bytes,
        )
    literal_control = ast.parse('Literal["list[str, int]"]', mode="eval").body
    if not isinstance(literal_control, ast.Subscript):
        raise AssertionError("Literal string control did not parse as a subscript")
    validate_type_expression(literal_control)
    if literal_member(literal_control.slice) != "list[str, int]":
        raise AssertionError("Literal string control was parsed as a type")
    metadata_control = ast.parse(
        'Field(default="list[str, int]")', mode="eval"
    ).body
    if not isinstance(metadata_control, ast.Call):
        raise AssertionError("Field metadata string control did not parse as a call")
    if parse_field_call(metadata_control) != {
        "constraints": {},
        "default": {"kind": "literal", "value": "list[str, int]"},
    }:
        raise AssertionError("Field metadata string control was parsed as a type")
    metadata_name_control = ast.parse("Field(default=SomeName)", mode="eval").body
    if not isinstance(metadata_name_control, ast.Call):
        raise AssertionError("Field name control did not parse as a call")
    validate_field_data_expression(metadata_name_control)
    for label, alias_source in (
        (
            "unprojected dynamic Annotated metadata",
            "Layer1BadMetadata = Annotated[str, Field(default=evil())]",
        ),
        (
            "unprojected dynamic Field alias",
            "Layer1BadMetadata = Field(default=globals())",
        ),
        (
            "unprojected dynamic Literal member",
            "Layer1BadMetadata = Literal[evil()]",
        ),
        (
            "unprojected Field kwargs expansion",
            "Layer1BadMetadata = Field(**{})",
        ),
    ):
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"{alias_source}\n\n{base_model_declaration}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            label,
        )
    for label, replacement in (
        ("unknown base", f"class {declared_root}(UnknownBase):"),
        ("qualified base", f"class {declared_root}(models.BaseModel):"),
        ("generic base", f"class {declared_root}(BaseModel[str]):"),
        (
            "multiple inheritance",
            f"class {declared_root}(BaseModel, BaseModel):",
        ),
    ):
        assert_source_rejected(
            document.replace(base_model_declaration, replacement, 1).encode("utf-8"),
            registry_bytes,
            label,
        )

    shadowed_base_model = (
        "class BaseModel:\n"
        "    pass\n\n"
        f"{base_model_declaration}"
    )
    assert_source_rejected(
        document.replace(
            base_model_declaration, shadowed_base_model, 1
        ).encode("utf-8"),
        registry_bytes,
        "locally declared BaseModel",
    )
    aliased_base_model = f"BaseModel = str\n\n{base_model_declaration}"
    assert_source_rejected(
        document.replace(
            base_model_declaration, aliased_base_model, 1
        ).encode("utf-8"),
        registry_bytes,
        "locally aliased BaseModel",
    )
    for label, binding_source in (
        ("annotated BaseModel assignment", "BaseModel: type = str"),
        ("Python 3.12 BaseModel type alias", "type BaseModel = str"),
        ("destructuring BaseModel assignment", "BaseModel, other = str, str"),
        ("BaseModel import alias", "import pydantic as BaseModel"),
        ("BaseModel from-import", "from pydantic import BaseModel"),
        ("BaseModel function", "def BaseModel():\n    pass"),
        ("BaseModel async function", "async def BaseModel():\n    pass"),
        ("BaseModel additive assignment", "BaseModel += str"),
        ("BaseModel matrix assignment", "BaseModel @= str"),
        ("BaseModel deletion", "del BaseModel"),
    ):
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"{binding_source}\n\n{base_model_declaration}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            label,
        )

    for label, executable_source in (
        ("named expression", "(BaseModel := str)"),
        ("module loop", "for BaseModel in ():\n    pass"),
        (
            "async loop",
            "async def layer1_async_loop():\n"
            "    async for BaseModel in source:\n"
            "        pass",
        ),
        ("module with", "with context as BaseModel:\n    pass"),
        (
            "async with",
            "async def layer1_async_with():\n"
            "    async with context as BaseModel:\n"
            "        pass",
        ),
        (
            "exception binding",
            "try:\n"
            "    pass\n"
            "except Exception as BaseModel:\n"
            "    pass",
        ),
        (
            "match capture",
            "match value:\n"
            "    case BaseModel:\n"
            "        pass",
        ),
        ("star import", "from layer1_dynamic_namespace import *"),
        ("globals assignment", 'globals()["BaseModel"] = str'),
        ("globals deletion", 'del globals()["BaseModel"]'),
        ("vars assignment", 'vars()["BaseModel"] = str'),
        ("vars deletion", 'del vars()["BaseModel"]'),
    ):
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"{executable_source}\n\n{base_model_declaration}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            label,
        )

    for label, class_statement in (
        (
            "dynamic annotations mutation",
            '__annotations__["layer1_dynamic"] = str',
        ),
        ("class globals mutation", 'globals()["layer1_dynamic"] = str'),
        ("class setattr mutation", 'setattr(cls, "layer1_dynamic", str)'),
        ("model method", "def layer1_method(self):\n        ..."),
        ("nested class", "class Layer1Nested:\n        pass"),
        ("arbitrary class assignment", "layer1_dynamic = str"),
        (
            "decorated model validator",
            '@validator("layer1_dynamic")\n'
            "    def validate_layer1(cls, value):\n"
            "        return value",
        ),
    ):
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n    {class_statement}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            label,
        )
    for label, field_default in (
        ("unsupported default call", "Factory()"),
        ("Field positional default", "Field(None)"),
        ("Field default_factory", "Field(default_factory=list)"),
        ("Field alias", 'Field(alias="layer1_dynamic")'),
        ("Field discriminator", 'Field(discriminator="kind")'),
        ("Field kwargs expansion", "Field(**{})"),
        ("Field unsupported constraint", "Field(lt=1)"),
    ):
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n"
                f"    layer1_dynamic: str = {field_default}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            label,
        )

    default_document = document.replace(
        base_model_declaration,
        f"{base_model_declaration}\n"
        "    layer1_default_field: str | None = Field(default=None)",
        1,
    )
    default_authority = compile_authority(
        default_document.encode("utf-8"), registry_bytes
    )
    default_schema = next(
        schema
        for schema in default_authority["schemas"]
        if schema["coordinate"] == baseline_schema["coordinate"]
    )
    if default_schema["normalized_graph"]["fields"][0]["default"] != {
        "kind": "literal",
        "value": None,
    }:
        raise AssertionError("reachable Field(default=None) was not normalized")
    if default_schema["schema_fingerprint"] == baseline_schema["schema_fingerprint"]:
        raise AssertionError("reachable Field(default=None) did not affect fingerprint")

    for external_exception in (
        "CapabilityBaselineApprovalVerifier",
        "SourceKind",
    ):
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"class {declared_root}({external_exception}):",
                1,
            ).encode("utf-8"),
            registry_bytes,
            f"reachable {external_exception}",
        )

    legitimate_metadata = baseline_aliases["TraceabilityGenerationMember"]
    if not (
        isinstance(legitimate_metadata, ast.Subscript)
        and isinstance(legitimate_metadata.value, ast.Name)
        and legitimate_metadata.value.id == "Annotated"
    ):
        raise AssertionError("legitimate Annotated routing alias is absent")
    legitimate_arguments = (
        list(legitimate_metadata.slice.elts)
        if isinstance(legitimate_metadata.slice, ast.Tuple)
        else [legitimate_metadata.slice]
    )
    validate_annotated_metadata(
        legitimate_arguments[1:], "TraceabilityGenerationMember"
    )
    projection.validate_generation_member_union(legitimate_arguments[0])

    generation_alias_pattern = (
        r"TraceabilityGenerationMember = Annotated\[.*?\n\]\n\n"
        r"class TraceabilityActivePointerIntent"
    )

    def replace_generation_alias(
        source: str, replacement: str, prefix: str = ""
    ) -> str:
        changed, count = re.subn(
            generation_alias_pattern,
            prefix
            + "TraceabilityGenerationMember = "
            + replacement
            + "\n\nclass TraceabilityActivePointerIntent",
            source,
            count=1,
            flags=re.DOTALL,
        )
        if count != 1:
            raise AssertionError("authorized generation alias fixture is not unique")
        return changed

    metadata_suffix = ", Field(discriminator='artifact_kind')]"
    for label, wrapped in (
        ("generation alias wrapped Literal", 'Literal["x"]'),
        ("generation alias wrapped scalar", "str"),
        (
            "generation alias wrapped nonunion",
            "TraceabilityRawDesignGenerationMember",
        ),
        ("generation alias unknown member", "Layer1UnknownGenerationMember | str"),
        ("generation alias nonmodel member", "NormativeUnitKind | str"),
    ):
        assert_source_rejected(
            replace_generation_alias(
                document, f"Annotated[{wrapped}{metadata_suffix}"
            ).encode("utf-8"),
            registry_bytes,
            label,
        )

    wrapped_union = ast.unparse(legitimate_arguments[0])
    missing_kind_union = wrapped_union.replace(
        "TraceabilityRawDesignGenerationMember",
        "Layer1MissingKindGenerationMember",
        1,
    )
    missing_kind_class = (
        "class Layer1MissingKindGenerationMember(BaseModel):\n"
        "    other_kind: Literal['design_document']\n\n"
    )
    assert_source_rejected(
        replace_generation_alias(
            document,
            f"Annotated[{missing_kind_union}{metadata_suffix}",
            missing_kind_class,
        ).encode("utf-8"),
        registry_bytes,
        "generation member lacking artifact_kind",
    )

    duplicate_discriminator_document = document.replace(
        'artifact_kind: Literal["registry_source"]',
        'artifact_kind: Literal["design_document"]',
        1,
    )
    assert_source_rejected(
        duplicate_discriminator_document.encode("utf-8"),
        registry_bytes,
        "duplicate generation discriminator",
    )

    for label, annotation, alias_source in (
        (
            "direct Annotated default_factory",
            "Annotated[str, Field(default_factory=list)]",
            "",
        ),
        (
            "quoted Annotated default_factory",
            '"Annotated[str, Field(default_factory=list)]"',
            "",
        ),
        (
            "aliased Annotated default_factory",
            "Layer1BadAnnotated",
            "Layer1BadAnnotated = Annotated[str, Field(default_factory=list)]\n\n",
        ),
        (
            "Annotated default metadata",
            "Annotated[str, Field(default=None)]",
            "",
        ),
        (
            "Annotated alias metadata",
            'Annotated[str, Field(alias="value")]',
            "",
        ),
        (
            "Annotated constraint metadata",
            "Annotated[str, Field(ge=1)]",
            "",
        ),
        (
            "Annotated positional metadata",
            "Annotated[str, Field('artifact_kind')]",
            "",
        ),
        (
            "Annotated kwargs metadata",
            "Annotated[str, Field(**{})]",
            "",
        ),
        (
            "Annotated arbitrary call metadata",
            "Annotated[str, UnknownMetadata()]",
            "",
        ),
        (
            "Annotated arbitrary name metadata",
            "Annotated[str, marker]",
            "",
        ),
        (
            "Annotated multiple metadata",
            "Annotated[str, Field(discriminator='artifact_kind'), marker]",
            "",
        ),
    ):
        mutated_declaration = (
            f"{alias_source}{base_model_declaration}\n"
            f"    layer1_metadata_field: {annotation}"
        )
        assert_source_rejected(
            document.replace(
                base_model_declaration, mutated_declaration, 1
            ).encode("utf-8"),
            registry_bytes,
            label,
        )

    for label, metadata in (
        ("literal alias default", "Field(default=None)"),
        ("literal alias default_factory", "Field(default_factory=list)"),
        ("literal alias field alias", 'Field(alias="value")'),
        ("literal alias constraint", "Field(ge=1)"),
        ("literal alias positional", "Field('artifact_kind')"),
        ("literal alias kwargs", "Field(**{})"),
        ("literal alias arbitrary call", "UnknownMetadata()"),
        ("literal alias arbitrary name", "marker"),
        (
            "literal alias multiple metadata",
            "Field(discriminator='artifact_kind'), marker",
        ),
        (
            "literal alias invalid discriminator",
            "Field(discriminator='artifact_kind')",
        ),
    ):
        literal_alias_source = (
            f'Layer1BadLiteral = Annotated[Literal["x"], {metadata}]\n\n'
            f"{base_model_declaration}\n"
            "    layer1_literal_field: Layer1BadLiteral"
        )
        assert_source_rejected(
            document.replace(
                base_model_declaration, literal_alias_source, 1
            ).encode("utf-8"),
            registry_bytes,
            label,
        )
    for label, annotation in (
        (
            "direct Literal Annotated default_factory",
            'Annotated[Literal["x"], Field(default_factory=list)]',
        ),
        (
            "quoted Literal Annotated default_factory",
            '"Annotated[Literal[\\"x\\"], Field(default_factory=list)]"',
        ),
    ):
        assert_source_rejected(
            document.replace(
                base_model_declaration,
                f"{base_model_declaration}\n"
                f"    layer1_literal_field: {annotation}",
                1,
            ).encode("utf-8"),
            registry_bytes,
            label,
        )
    nested_literal_alias = (
        'Layer1InnerLiteral = Literal["x"]\n'
        "Layer1OuterLiteral = "
        "Annotated[Layer1InnerLiteral, Field(default_factory=list)]\n\n"
        f"{base_model_declaration}\n"
        "    layer1_literal_field: Layer1OuterLiteral"
    )
    assert_source_rejected(
        document.replace(
            base_model_declaration, nested_literal_alias, 1
        ).encode("utf-8"),
        registry_bytes,
        "nested Literal alias default_factory",
    )

    local_base_declaration = (
        "class Layer1SelfTestBase(BaseModel):\n"
        "    layer1_self_test_field: str\n\n"
        f"class {declared_root}(Layer1SelfTestBase):"
    )
    local_inheritance_document = document.replace(
        base_model_declaration, local_base_declaration, 1
    )
    local_authority = compile_authority(
        local_inheritance_document.encode("utf-8"), registry_bytes
    )
    local_classes, local_aliases = declarations(local_inheritance_document)
    local_projection = Compiler(local_classes, local_aliases)
    local_projection.normalize(ast.Name(id=declared_root))
    if "Layer1SelfTestBase" not in local_projection.projected_classes:
        raise AssertionError("local inherited parent absent from projection closure")
    local_schema = next(
        schema
        for schema in local_authority["schemas"]
        if schema["coordinate"] == baseline_schema["coordinate"]
    )
    expected_inherited_field = {
        "annotation": {"kind": "scalar", "name": "str"},
        "constraints": {},
        "declaring_owner": "Layer1SelfTestBase",
        "default": {"kind": "required"},
        "field_name": "layer1_self_test_field",
    }
    expected_fields = [
        expected_inherited_field,
        *baseline_schema["normalized_graph"]["fields"],
    ]
    if local_schema["normalized_graph"]["fields"] != expected_fields:
        raise AssertionError("local inheritance field ownership/order was not preserved")
    if local_schema["schema_fingerprint"] == baseline_schema["schema_fingerprint"]:
        raise AssertionError("local inheritance did not change schema fingerprint")
    if local_schema["binding_digest"] == baseline_schema["binding_digest"]:
        raise AssertionError("local inheritance did not change binding digest")
    if local_authority["profile"] != authority["profile"]:
        raise AssertionError("local inheritance unexpectedly changed v2 profile")

    inherited_default_declaration = (
        "class Layer1DefaultParent(BaseModel):\n"
        "    inherited_default: str | None = Field(default=None)\n\n"
        f"class {declared_root}(Layer1DefaultParent):"
    )
    inherited_default_document = document.replace(
        base_model_declaration, inherited_default_declaration, 1
    )
    inherited_default_authority = compile_authority(
        inherited_default_document.encode("utf-8"), registry_bytes
    )
    inherited_classes, inherited_aliases = declarations(inherited_default_document)
    inherited_projection = Compiler(inherited_classes, inherited_aliases)
    inherited_projection.normalize(ast.Name(id=declared_root))
    if "Layer1DefaultParent" not in inherited_projection.projected_classes:
        raise AssertionError("default-bearing parent absent from projection closure")
    inherited_schema = next(
        schema
        for schema in inherited_default_authority["schemas"]
        if schema["coordinate"] == baseline_schema["coordinate"]
    )
    inherited_field = inherited_schema["normalized_graph"]["fields"][0]
    if (
        inherited_field["declaring_owner"] != "Layer1DefaultParent"
        or inherited_field["default"] != {"kind": "literal", "value": None}
    ):
        raise AssertionError("inherited Field(default=None) was not normalized")
    if inherited_schema["schema_fingerprint"] == baseline_schema["schema_fingerprint"]:
        raise AssertionError("inherited default did not change schema fingerprint")
    if inherited_schema["binding_digest"] == baseline_schema["binding_digest"]:
        raise AssertionError("inherited default did not change binding digest")

    zero_base_document = document.replace(
        base_model_declaration, f"class {declared_root}:", 1
    )
    zero_base_authority = compile_authority(
        zero_base_document.encode("utf-8"), registry_bytes
    )
    zero_base_schema = next(
        schema
        for schema in zero_base_authority["schemas"]
        if schema["coordinate"] == baseline_schema["coordinate"]
    )
    for field in ("normalized_graph", "schema_fingerprint", "binding_digest"):
        if zero_base_schema[field] != baseline_schema[field]:
            raise AssertionError(f"zero-base model changed baseline {field}")

    def assert_publication_preserves(
        label: str,
        initial: bytes | None,
        **failpoint: Callable[..., Any],
    ) -> None:
        nonlocal partial_write_calls
        if failpoint.get("writer") is partial_write_then_error:
            partial_write_calls = 0
        with tempfile.TemporaryDirectory(
            prefix=f".{scratch_name}.self-test.", dir=scratch_parent
        ) as temporary:
            target = Path(temporary) / "authority.json"
            initial_mode: int | None = None
            if initial is not None:
                target.write_bytes(initial)
                target.chmod(0o640)
                initial_mode = target.stat().st_mode & 0o7777
            try:
                publish_authority_atomically(target, expected_bytes, **failpoint)
            except OSError:
                pass
            else:
                raise AssertionError(f"publication failpoint did not fail: {label}")
            if initial is None:
                if target.exists():
                    raise AssertionError(f"absent target changed by {label}")
            else:
                if target.read_bytes() != initial:
                    raise AssertionError(f"seeded target changed by {label}")
                if initial_mode is None:
                    raise AssertionError(f"seeded target mode missing for {label}")
                if target.stat().st_mode & 0o7777 != initial_mode:
                    raise AssertionError(f"seeded target mode changed by {label}")
            if list(target.parent.glob(f".{target.name}.*.tmp")):
                raise AssertionError(f"publication temporary remains after {label}")

    def fail_write(_stream: Any, _payload: bytes | memoryview) -> int:
        raise OSError("injected write failure")

    def zero_write(_stream: Any, _payload: bytes | memoryview) -> int:
        return 0

    partial_write_calls = 0

    def partial_write_then_error(stream: Any, payload: bytes | memoryview) -> int:
        nonlocal partial_write_calls
        if partial_write_calls == 0:
            partial_write_calls += 1
            return stream.write(payload[:1])
        raise OSError("injected partial-write failure")

    def fail_flush(_stream: Any) -> None:
        raise OSError("injected flush failure")

    def fail_mode_setter(_descriptor: int, _mode: int) -> None:
        raise OSError(errno.EIO, "injected mode-set failure")

    def fail_file_fsync(_descriptor: int) -> None:
        raise OSError(errno.EIO, "injected file fsync failure")

    def fail_replace(_source: str, _target: str) -> None:
        raise OSError("injected replace failure")

    for initial_name, initial in (("absent", None), ("seeded", b"seeded-authority\n")):
        for label, failpoint in (
            ("write", {"writer": fail_write}),
            ("short write", {"writer": zero_write}),
            ("partial write", {"writer": partial_write_then_error}),
            ("flush", {"flusher": fail_flush}),
            ("mode set", {"mode_setter": fail_mode_setter}),
            ("file fsync", {"file_fsync": fail_file_fsync}),
            ("replace", {"replacer": fail_replace}),
        ):
            assert_publication_preserves(
                f"{initial_name} {label}", initial, **failpoint
            )

    invalid_publication = document.replace(
        base_model_declaration,
        f"{base_model_declaration}\n    {collection_field}: list[str, int]",
        1,
    ).encode("utf-8")
    with tempfile.TemporaryDirectory(
        prefix=f".{scratch_name}.self-test.", dir=scratch_parent
    ) as temporary:
        target = Path(temporary) / "authority.json"
        target.write_bytes(b"seeded-authority\n")
        assert_source_rejected(
            invalid_publication,
            registry_bytes,
            "invalid input before publication",
        )
        if target.read_bytes() != b"seeded-authority\n":
            raise AssertionError("invalid compilation changed publication target")

    with tempfile.TemporaryDirectory(
        prefix=f".{scratch_name}.self-test.", dir=scratch_parent
    ) as temporary:
        target = Path(temporary) / "authority.json"
        target.write_bytes(b"old-authority\n")
        target.chmod(0o640)

        private_writer_calls = 0

        def private_partial_writer(stream: Any, payload: bytes | memoryview) -> int:
            nonlocal private_writer_calls
            if os.fstat(stream.fileno()).st_mode & 0o7777 != 0o600:
                raise AssertionError("temporary authority is not private during write")
            private_writer_calls += 1
            if private_writer_calls == 1:
                return stream.write(payload[:1])
            return stream.write(payload)

        publish_authority_atomically(
            target, expected_bytes, writer=private_partial_writer
        )
        if target.read_bytes() != expected_bytes:
            raise AssertionError("successful atomic publication differs from authority")
        if target.stat().st_mode & 0o7777 != 0o640:
            raise AssertionError("successful publication did not preserve target mode")
        if private_writer_calls < 2:
            raise AssertionError("private temporary control did not make partial progress")
        if list(target.parent.glob(f".{target.name}.*.tmp")):
            raise AssertionError("successful publication left a temporary sibling")

    with tempfile.TemporaryDirectory(
        prefix=f".{scratch_name}.self-test.", dir=scratch_parent
    ) as temporary:
        target = Path(temporary) / "authority.json"
        publish_authority_atomically(target, expected_bytes)
        if target.read_bytes() != expected_bytes or target.stat().st_mode & 0o7777 != 0o644:
            raise AssertionError("absent authority creation mode is not 0644")

        restrictive = Path(temporary) / "restrictive-authority.json"
        restrictive.write_bytes(b"old-authority\n")
        restrictive.chmod(0o600)
        publish_authority_atomically(restrictive, expected_bytes)
        if (
            restrictive.read_bytes() != expected_bytes
            or restrictive.stat().st_mode & 0o7777 != 0o600
        ):
            raise AssertionError("restrictive authority mode was not preserved")

        resolved = Path(temporary) / "resolved-authority.json"
        resolved.write_bytes(b"old-authority\n")
        resolved.chmod(0o640)
        link = Path(temporary) / "authority-link.json"
        link.symlink_to(resolved)
        publish_authority_atomically(link, expected_bytes)
        if (
            not link.is_symlink()
            or link.read_bytes() != expected_bytes
            or resolved.stat().st_mode & 0o7777 != 0o640
        ):
            raise AssertionError("symlink-resolved authority publication changed contract")

    def assert_post_replace_behavior(
        label: str,
        directory_fsync: Callable[[Path], None],
        *,
        should_raise: bool,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix=f".{scratch_name}.self-test.", dir=scratch_parent
        ) as temporary:
            target = Path(temporary) / "authority.json"
            target.write_bytes(b"old-authority\n")
            target.chmod(0o640)
            try:
                publish_authority_atomically(
                    target, expected_bytes, directory_fsync=directory_fsync
                )
            except OSError:
                if not should_raise:
                    raise AssertionError(f"unsupported directory sync raised: {label}")
            else:
                if should_raise:
                    raise AssertionError(f"real directory sync error did not raise: {label}")
            if (
                not target.exists()
                or target.read_bytes() != expected_bytes
                or target.stat().st_mode & 0o7777 != 0o640
            ):
                raise AssertionError(f"post-replace target state is not complete: {label}")
            if list(target.parent.glob(f".{target.name}.*.tmp")):
                raise AssertionError(f"post-replace temporary remains: {label}")

    def unsupported_open(directory: Path, error_number: int) -> None:
        def opener(_directory: Path, _flags: int) -> int:
            raise OSError(error_number, "unsupported directory open")

        _fsync_directory(
            directory,
            opener=opener,
        )

    def unsupported_fsync(directory: Path, error_number: int) -> None:
        def fsync(_descriptor: int) -> None:
            raise OSError(error_number, "unsupported directory fsync")

        _fsync_directory(
            directory,
            fsync=fsync,
        )

    def real_directory_error(directory: Path) -> None:
        _fsync_directory(
            directory,
            fsync=lambda _descriptor: (_ for _ in ()).throw(
                OSError(errno.EIO, "injected directory fsync failure")
            ),
        )

    def real_directory_open_error(directory: Path) -> None:
        def opener(_directory: Path, _flags: int) -> int:
            raise OSError(errno.EIO, "injected directory open failure")

        _fsync_directory(directory, opener=opener)

    for unsupported_errno in {
        errno.EINVAL,
        errno.ENOTSUP,
        getattr(errno, "EOPNOTSUPP", errno.ENOTSUP),
    }:
        assert_post_replace_behavior(
            f"unsupported open {unsupported_errno}",
            lambda directory, code=unsupported_errno: unsupported_open(directory, code),
            should_raise=False,
        )
        assert_post_replace_behavior(
            f"unsupported fsync {unsupported_errno}",
            lambda directory, code=unsupported_errno: unsupported_fsync(directory, code),
            should_raise=False,
        )
    assert_post_replace_behavior("real fsync", real_directory_error, should_raise=True)
    assert_post_replace_behavior("real open", real_directory_open_error, should_raise=True)

    with tempfile.TemporaryDirectory(
        prefix=f".{scratch_name}.self-test.", dir=scratch_parent
    ) as temporary:
        target = Path(temporary) / "authority.json"
        old_payload = canonical({"generation": "old"})
        new_payload = canonical({"generation": "new"})
        target.write_bytes(old_payload)
        observations: list[bytes] = []
        errors: list[BaseException] = []
        old_observed = threading.Event()
        replaced = threading.Event()

        def reader() -> None:
            try:
                observations.append(target.read_bytes())
                old_observed.set()
                if not replaced.wait(timeout=5):
                    errors.append(AssertionError("reader did not observe replacement"))
                    return
                observations.append(target.read_bytes())
            except FileNotFoundError as error:
                errors.append(error)

        reader_thread = threading.Thread(target=reader)
        reader_thread.start()
        def coordinated_replace(source: str, destination: str) -> None:
            if not old_observed.wait(timeout=5):
                raise AssertionError("reader did not observe old authority")
            os.replace(source, destination)
            replaced.set()

        publish_authority_atomically(target, new_payload, replacer=coordinated_replace)
        reader_thread.join(timeout=5)
        if (
            reader_thread.is_alive()
            or errors
            or observations != [old_payload, new_payload]
        ):
            raise AssertionError("concurrent atomic publication proof failed")

    cyclic_bases = (
        "class Layer1SelfTestCycleA(Layer1SelfTestCycleB):\n"
        "    pass\n\n"
        "class Layer1SelfTestCycleB(Layer1SelfTestCycleA):\n"
        "    pass\n\n"
        f"class {declared_root}(Layer1SelfTestCycleA):"
    )
    assert_source_rejected(
        document.replace(base_model_declaration, cyclic_bases, 1).encode("utf-8"),
        registry_bytes,
        "reachable local inheritance cycle",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    inputs = (str(args.design), str(args.registry), str(args.authority))
    if any(term in path.lower() for path in inputs[:2] for term in FORBIDDEN_INPUT_TERMS):
        raise ValueError("corpus/recipe/package inputs are forbidden")
    design_bytes = args.design.read_bytes()
    registry_bytes = args.registry.read_bytes()
    computed = compile_authority(design_bytes, registry_bytes)
    computed_bytes = canonical(computed)
    computed_candidate = strict_json_loads(computed_bytes)
    if computed_bytes != canonical(computed_candidate):
        raise AssertionError("compiled authority is not canonical compact UTF-8 JSON plus LF")
    validate_candidate(computed_candidate, computed_bytes)
    if args.write:
        publish_authority_atomically(args.authority, computed_bytes)
        actual = computed_candidate
    else:
        actual_bytes = args.authority.read_bytes()
        actual = strict_json_loads(actual_bytes)
        if actual_bytes != canonical(actual):
            raise ValueError("authority must be canonical compact UTF-8 JSON plus LF")
    validate_candidate(actual, computed_bytes)
    if args.self_test:
        adversarial_self_test(
            actual,
            computed_bytes,
            design_bytes,
            registry_bytes,
            args.authority.parent,
            args.authority.name,
        )
    print(
        json.dumps(
            {
                "authority_sha256": hashlib.sha256(computed_bytes).hexdigest(),
                "enum_rows": len(computed["enum_registry"]["rows"]),
                "profile_digest": computed["profile"]["digest"],
                "schemas": len(computed["schemas"]),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

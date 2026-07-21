"""Helpers for deterministic benchmark runs."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import random
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, Never, TypeAlias

from pydantic import BaseModel, ConfigDict, model_validator

from memorii.core.benchmark.models import BenchmarkRunConfig, BenchmarkScenarioFixture

SourceState: TypeAlias = Literal["clean", "dirty", "unversioned"]
_DynamicImportBinding: TypeAlias = Literal[
    "ambiguous",
    "builtin",
    "builtins_module",
    "function",
    "module",
]


class SourceIdentity(BaseModel):
    """Source revision and tree state used to decide report certifiability."""

    revision: str
    state: SourceState
    certifiable: bool

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_certifiability(self) -> SourceIdentity:
        expected = self.state == "clean" and self.revision != "local-source-tree"
        if self.certifiable != expected:
            raise ValueError("source identity certifiability must match revision and tree state")
        return self


def apply_seed(seed: int) -> None:
    random.seed(seed)


def build_run_id(*, config: BenchmarkRunConfig, fixtures: list[BenchmarkScenarioFixture]) -> str:
    fixture_key = "|".join(sorted(f"{fixture.scenario_id}:{fixture.category.value}" for fixture in fixtures))
    raw = f"{config.run_label}:{config.seed}:{fixture_key}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"bench-{digest}"


def build_benchmark_fingerprint(config: Mapping[str, object]) -> str:
    """Return a stable fingerprint for one explicitly owned benchmark layer."""
    payload = json.dumps(dict(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_json_digest(value: object) -> str:
    """Return the SHA-256 digest of one canonical JSON value."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a persisted artifact without loading it."""

    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_source_revision(*, root: Path, dry_run: bool) -> str:
    """Resolve immutable source identity without invoking a shell.

    CI should set ``MEMORII_SOURCE_REVISION`` to the checked-out commit. Local
    runs use the enclosing Git repository when available. Only dry runs may
    use the explicit local sentinel.
    """

    git_revision = _git_head_revision(root)
    configured = os.environ.get("MEMORII_SOURCE_REVISION")
    if configured is not None:
        revision = configured.strip()
        if not revision or revision != configured:
            raise ValueError("MEMORII_SOURCE_REVISION must be non-empty and normalized")
        if revision == "local-source-tree" and not dry_run:
            raise ValueError("live benchmark reports require a real source revision")
        if git_revision is not None and revision != git_revision:
            raise ValueError("MEMORII_SOURCE_REVISION does not match the checked-out Git HEAD")
        return revision

    if git_revision is not None:
        return git_revision
    if dry_run:
        return "local-source-tree"
    raise ValueError(
        "live benchmark reports require MEMORII_SOURCE_REVISION or an enclosing Git checkout"
    )


def resolve_source_state(*, root: Path) -> SourceState:
    """Return whether the executing source tree is clean and version controlled."""

    status = _git_status_porcelain(root)
    if status is None:
        return "unversioned"
    return "dirty" if status else "clean"


def resolve_source_identity(*, root: Path, dry_run: bool) -> SourceIdentity:
    """Resolve a single validated source identity for report construction."""

    revision = resolve_source_revision(root=root, dry_run=dry_run)
    state = resolve_source_state(root=root)
    return SourceIdentity(
        revision=revision,
        state=state,
        certifiable=state == "clean" and revision != "local-source-tree",
    )


def _git_status_porcelain(root: Path) -> str | None:
    repository_root = _find_git_root(root)
    if repository_root is None:
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), "status", "--porcelain=v1", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _find_git_root(root: Path) -> Path | None:
    for candidate in (root.resolve(), *root.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _git_head_revision(root: Path) -> str | None:
    for candidate in (root.resolve(), *root.resolve().parents):
        git_dir = candidate / ".git"
        if git_dir.is_file():
            pointer = git_dir.read_text(encoding="utf-8").strip()
            if not pointer.startswith("gitdir: "):
                continue
            git_dir = (candidate / pointer.removeprefix("gitdir: ")).resolve()
        if not git_dir.is_dir():
            continue
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = head.removeprefix("ref: ")
            ref_path = git_dir / ref
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8").strip()
            packed_refs = git_dir / "packed-refs"
            if packed_refs.is_file():
                for line in packed_refs.read_text(encoding="utf-8").splitlines():
                    if line and not line.startswith(("#", "^")):
                        revision, packed_ref = line.split(" ", 1)
                        if packed_ref == ref:
                            return revision
            return None
        return head or None
    return None


def build_source_tree_fingerprint(*, root: Path, relative_paths: list[str]) -> str:
    """Hash an explicitly owned set of source files and directories."""

    resolved_root = root.resolve()
    files: set[Path] = set()
    for relative_path in relative_paths:
        candidate = (resolved_root / relative_path).resolve()
        if not candidate.is_relative_to(resolved_root):
            raise ValueError(f"source fingerprint path escapes root: {relative_path}")
        if candidate.is_dir():
            files.update(
                path
                for path in candidate.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix in {".json", ".py", ".toml", ".yaml", ".yml"}
            )
        elif candidate.is_file():
            files.add(candidate)
        else:
            raise ValueError(f"source fingerprint path does not exist: {relative_path}")
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = path.relative_to(resolved_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_python_dependency_fingerprint(*, root: Path, entry_paths: list[str]) -> str:
    """Hash entry points and their complete local Python import closure.

    Static local imports are resolved from ``root``. Dynamic imports are
    rejected because silently omitting one would make the fingerprint an
    incomplete statement about the code that produced benchmark artifacts.
    """

    resolved_root = root.resolve()
    pending = list(_python_entry_files(root=resolved_root, entry_paths=entry_paths))
    files: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in files:
            continue
        files.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module_name in _statically_imported_modules(
            tree=tree,
            path=path,
            root=resolved_root,
        ):
            imported_path = _local_module_path(root=resolved_root, module_name=module_name)
            if imported_path is not None and imported_path not in files:
                pending.append(imported_path)
        _reject_dynamic_local_imports(tree=tree, path=path, root=resolved_root)
    return _fingerprint_files(root=resolved_root, files=files)


def _python_entry_files(*, root: Path, entry_paths: list[str]) -> set[Path]:
    files: set[Path] = set()
    for relative_path in entry_paths:
        candidate = (root / relative_path).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"Python dependency path escapes root: {relative_path}")
        if candidate.is_dir():
            files.update(path.resolve() for path in candidate.rglob("*.py") if path.is_file())
        elif candidate.is_file() and candidate.suffix == ".py":
            files.add(candidate)
        elif candidate.exists():
            raise ValueError(f"Python dependency path is not Python source: {relative_path}")
        else:
            raise ValueError(f"Python dependency path does not exist: {relative_path}")
    if not files:
        raise ValueError("Python dependency fingerprint requires at least one source file")
    return files


def _statically_imported_modules(
    *,
    tree: ast.AST,
    path: Path,
    root: Path,
) -> set[str]:
    modules: set[str] = set()
    current_module = _module_name_for_path(root=root, path=path)
    current_package = current_module if path.name == "__init__.py" else current_module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            relative_name = "." * node.level + (node.module or "")
            try:
                module_name = importlib.util.resolve_name(relative_name, current_package)
            except ImportError as error:
                raise ValueError(f"cannot resolve relative import in {path}:{node.lineno}") from error
        else:
            module_name = node.module
        if module_name is None:
            raise ValueError(f"cannot resolve import in {path}:{node.lineno}")
        modules.add(module_name)
        modules.update(
            candidate
            for alias in node.names
            if alias.name != "*"
            if (candidate := f"{module_name}.{alias.name}")
            if _local_module_path(root=root, module_name=candidate) is not None
        )
    return modules


def _module_name_for_path(*, root: Path, path: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    if not parts:
        raise ValueError(f"Python source is not contained in a package: {path}")
    return ".".join(parts)


def _local_module_path(*, root: Path, module_name: str) -> Path | None:
    module_path = root.joinpath(*module_name.split("."))
    source_path = module_path.with_suffix(".py")
    package_path = module_path / "__init__.py"
    if source_path.is_file():
        return source_path.resolve()
    if package_path.is_file():
        return package_path.resolve()
    return None


def _reject_dynamic_local_imports(*, tree: ast.AST, path: Path, root: Path) -> None:
    _DynamicImportValidator(path=path, root=root).visit(tree)


class _DynamicImportValidator(ast.NodeVisitor):
    """Reject dynamic imports that can make a local dependency closure incomplete."""

    def __init__(self, *, path: Path, root: Path) -> None:
        self._path = path
        self._root = root
        self._bindings: list[dict[str, _DynamicImportBinding | None]] = [
            {"__import__": "builtin"}
        ]

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound_name = alias.asname or alias.name.partition(".")[0]
            binding: _DynamicImportBinding | None = None
            if alias.name == "importlib" or (alias.asname is None and alias.name.startswith("importlib.")):
                binding = "module"
            elif alias.name == "builtins":
                binding = "builtins_module"
            self._bind(bound_name, binding)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            bound_name = alias.asname or alias.name
            binding: _DynamicImportBinding | None = None
            if node.level == 0 and node.module == "importlib" and alias.name == "import_module":
                binding = "function"
            elif node.level == 0 and node.module == "builtins" and alias.name == "__import__":
                binding = "builtin"
            self._bind(bound_name, binding)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        binding = self._expression_binding(node.value)
        for target in node.targets:
            self._bind_target(target, binding)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
        self._bind_target(
            node.target,
            self._expression_binding(node.value) if node.value is not None else None,
        )

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self._bind_target(node.target, self._expression_binding(node.value))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._bind(node.name, None)
        self._visit_callable_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._bind(node.name, None)
        self._visit_callable_scope(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._bindings.append({argument.arg: None for argument in _arguments(node.args)})
        self.visit(node.body)
        self._bindings.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._bind(node.name, None)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        for type_parameter in getattr(node, "type_params", ()):
            self.visit(type_parameter)
        self._bindings.append({})
        for statement in node.body:
            self.visit(statement)
        self._bindings.pop()

    def visit_Call(self, node: ast.Call) -> None:
        binding = self._expression_binding(node.func)
        if binding == "ambiguous":
            self._reject(node)
        if binding in {"builtin", "function"}:
            self._validate_dynamic_target(node=node, binding=binding)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._visit_for(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_for(node)

    def _visit_for(self, node: ast.For | ast.AsyncFor) -> None:
        self.visit(node.iter)
        self._bind_target(node.target, None)
        for statement in (*node.body, *node.orelse):
            self.visit(statement)

    def visit_With(self, node: ast.With) -> None:
        self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with(node)

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind_target(item.optional_vars, None)
        for statement in node.body:
            self.visit(statement)

    def _visit_callable_scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        for argument in _arguments(node.args):
            if argument.annotation is not None:
                self.visit(argument.annotation)
        if node.returns is not None:
            self.visit(node.returns)
        for type_parameter in getattr(node, "type_params", ()):
            self.visit(type_parameter)
        self._bindings.append({argument.arg: None for argument in _arguments(node.args)})
        for statement in node.body:
            self.visit(statement)
        self._bindings.pop()

    def _validate_dynamic_target(
        self,
        *,
        node: ast.Call,
        binding: _DynamicImportBinding,
    ) -> None:
        if not node.args:
            self._reject(node)
        target_node = node.args[0]
        if not isinstance(target_node, ast.Constant):
            self._reject(node)
        target = target_node.value
        if not isinstance(target, str) or not target or target.startswith("."):
            self._reject(node)
        if binding == "builtin" and _builtin_import_level(node) != 0:
            self._reject(node)
        if _local_module_path(root=self._root, module_name=target) is not None:
            self._reject(node)

    def _expression_binding(self, node: ast.expr) -> _DynamicImportBinding | None:
        if isinstance(node, ast.Name):
            return self._resolve(node.id)
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "import_module"
        ):
            owner_binding = self._expression_binding(node.value)
            if owner_binding == "module":
                return "function"
            if owner_binding == "ambiguous":
                return "ambiguous"
        if isinstance(node, ast.Attribute) and node.attr == "__import__":
            owner_binding = self._expression_binding(node.value)
            if owner_binding == "builtins_module":
                return "builtin"
            if owner_binding == "ambiguous":
                return "ambiguous"
        return None

    def _resolve(self, name: str) -> _DynamicImportBinding | None:
        for scope in reversed(self._bindings):
            if name in scope:
                return scope[name]
        return None

    def _bind(self, name: str, binding: _DynamicImportBinding | None) -> None:
        existing = self._bindings[-1].get(name)
        if existing in {
            "ambiguous",
            "builtin",
            "builtins_module",
            "function",
            "module",
        } and binding is None:
            self._bindings[-1][name] = "ambiguous"
            return
        self._bindings[-1][name] = binding

    def _bind_target(
        self,
        target: ast.expr,
        binding: _DynamicImportBinding | None,
    ) -> None:
        if isinstance(target, ast.Name):
            self._bind(target.id, binding)
        elif isinstance(target, (ast.List, ast.Tuple)):
            for element in target.elts:
                self._bind_target(element, None)

    def _reject(self, node: ast.Call) -> Never:
        raise ValueError(f"dynamic import cannot be fingerprinted: {self._path}:{node.lineno}")


def _arguments(arguments: ast.arguments) -> tuple[ast.arg, ...]:
    positional = (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
    optional = tuple(argument for argument in (arguments.vararg, arguments.kwarg) if argument)
    return (*positional, *optional)


def _builtin_import_level(node: ast.Call) -> int | None:
    level_node: ast.expr | None = node.args[4] if len(node.args) >= 5 else None
    for keyword in node.keywords:
        if keyword.arg == "level":
            level_node = keyword.value
            break
    if level_node is None:
        return 0
    if isinstance(level_node, ast.Constant) and isinstance(level_node.value, int):
        return level_node.value
    return None


def _fingerprint_files(*, root: Path, files: set[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()

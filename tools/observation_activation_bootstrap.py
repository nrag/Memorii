"""Pre-import verifier for a pinned Observation Activation deployment.

This module is deliberately importable by a trusted launcher before *any*
``memorii`` import.  It uses only the standard library and never installs a
distribution, reads configuration from the environment, parses JSON, or
executes an installed entry-point.  The launcher constructs
``DeploymentConfiguration`` directly from its protected deployment record and
passes the returned immutable facts to core after importing Memorii.

The verifier is a trusted-host boundary, rather than an attestation mechanism
for a hostile Python process.  In particular, it assumes its own stdlib and
interpreter observations have not been monkey patched before it runs.
"""

from __future__ import annotations

import base64
import csv
import importlib.machinery
import os
import platform
import re
import stat
import sys
import sysconfig
import zipfile
from dataclasses import dataclass
from collections.abc import Sequence
from email.parser import BytesParser
from hashlib import sha256
from io import StringIO
from pathlib import Path, PurePosixPath
from typing import Final, Literal, NoReturn
from types import ModuleType

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DIST_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_MAX_DISTRIBUTIONS: Final = 512
_MAX_FILES: Final = 250_000
_MAX_TOTAL_BYTES: Final = 64 * 1024 * 1024 * 1024
_MAX_FILE_BYTES: Final = 2 * 1024 * 1024 * 1024
_MAX_RECORD_BYTES: Final = 64 * 1024 * 1024
_MAX_PATH_DEPTH: Final = 128
_CHUNK: Final = 1024 * 1024


class BootstrapVerificationError(RuntimeError):
    """The selected deployment cannot safely be used for a Memorii import."""


def _fail(code: str) -> NoReturn:
    raise BootstrapVerificationError(code)


def _utf8(value: str) -> bytes:
    return value.encode("utf-8", "strict")


def _safe_relative(value: str, *, locator: bool = False) -> str:
    if type(value) is not str or not value or not value.isascii() or "\x00" in value or "\\" in value:
        _fail("bootstrap.path_invalid")
    if locator:
        if not (value.startswith("site/") or value.startswith("scripts/")):
            _fail("bootstrap.locator_invalid")
        value = value.split("/", 1)[1]
    # Check the raw spelling before PurePosixPath can normalize aliases such
    # as ``a/./b`` or ``a//b`` into a harmless-looking path.
    if value.startswith("/") or any(part in ("", ".", "..") for part in value.split("/")):
        _fail("bootstrap.path_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or len(path.parts) > _MAX_PATH_DEPTH:
        _fail("bootstrap.path_invalid")
    if any(part in ("", ".", "..") for part in path.parts):
        _fail("bootstrap.path_invalid")
    return "/".join(path.parts)


def _normalized_name(value: str) -> str:
    if type(value) is not str or not value.isascii():
        _fail("bootstrap.distribution_name_invalid")
    normalized = re.sub(r"[-_.]+", "-", value.lower())
    if normalized != value or not _DIST_NAME.fullmatch(value):
        _fail("bootstrap.distribution_name_invalid")
    return value


def _sha(value: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        _fail("bootstrap.sha256_invalid")
    return value


def _ascii_nonempty(value: str, code: str) -> str:
    if type(value) is not str or not value or not value.isascii():
        _fail(code)
    return value


@dataclass(frozen=True)
class DistributionRow:
    normalized_name: str
    version: str
    wheel_sha256: str
    record_sha256: str
    top_level_roots: tuple[str, ...]

    def __post_init__(self) -> None:
        _normalized_name(self.normalized_name)
        _ascii_nonempty(self.version, "bootstrap.distribution_version_invalid")
        _sha(self.wheel_sha256)
        _sha(self.record_sha256)
        if type(self.top_level_roots) is not tuple or not self.top_level_roots:
            _fail("bootstrap.distribution_roots_invalid")
        roots = tuple(_safe_relative(root) for root in self.top_level_roots)
        if roots != tuple(sorted(roots, key=_utf8)) or len(set(roots)) != len(roots):
            _fail("bootstrap.distribution_roots_invalid")


@dataclass(frozen=True)
class InstalledFileRow:
    normalized_distribution: str
    installed_relative_path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        _normalized_name(self.normalized_distribution)
        _safe_relative(self.installed_relative_path, locator=True)
        _sha(self.sha256)
        if type(self.size) is not int or self.size < 0 or self.size > _MAX_FILE_BYTES:
            _fail("bootstrap.installed_file_size_invalid")


@dataclass(frozen=True)
class DeploymentConfiguration:
    installation_root: Path
    scripts_root: Path
    python_implementation: str
    python_version: str
    platform_tag: str
    install_policy: Literal["wheel-no-compile-v1"]
    cache_policy: Literal["fresh-private-prefix-v1"]
    origin_policy: Literal["selected-distribution-root-v1"]
    distributions: tuple[DistributionRow, ...]
    installed_files: tuple[InstalledFileRow, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.installation_root, Path) or not self.installation_root.is_absolute():
            _fail("bootstrap.installation_root_invalid")
        if not isinstance(self.scripts_root, Path) or not self.scripts_root.is_absolute():
            _fail("bootstrap.scripts_root_invalid")
        if ".." in self.installation_root.parts or ".." in self.scripts_root.parts:
            _fail("bootstrap.anchor_not_canonical")
        if self.installation_root == self.scripts_root or self.installation_root.is_relative_to(self.scripts_root) or self.scripts_root.is_relative_to(self.installation_root):
            _fail("bootstrap.anchors_overlap")
        _ascii_nonempty(self.python_implementation, "bootstrap.python_implementation_invalid")
        _ascii_nonempty(self.python_version, "bootstrap.python_version_invalid")
        if type(self.platform_tag) is not str or not self.platform_tag:
            _fail("bootstrap.platform_invalid")
        if (self.install_policy, self.cache_policy, self.origin_policy) != (
            "wheel-no-compile-v1", "fresh-private-prefix-v1", "selected-distribution-root-v1"
        ):
            _fail("bootstrap.policy_invalid")
        if type(self.distributions) is not tuple or not self.distributions or type(self.installed_files) is not tuple:
            _fail("bootstrap.rows_invalid")
        if len(self.distributions) > _MAX_DISTRIBUTIONS or len(self.installed_files) > _MAX_FILES:
            _fail("bootstrap.cardinality_exceeded")
        if any(type(row) is not DistributionRow for row in self.distributions) or any(type(row) is not InstalledFileRow for row in self.installed_files):
            _fail("bootstrap.row_type_invalid")
        names = tuple(row.normalized_name for row in self.distributions)
        if names != tuple(sorted(names, key=_utf8)) or len(set(names)) != len(names) or names.count("memorii") != 1:
            _fail("bootstrap.distributions_invalid")
        keys = tuple((row.normalized_distribution, row.installed_relative_path) for row in self.installed_files)
        if keys != tuple(sorted(keys, key=lambda value: (_utf8(value[0]), _utf8(value[1]))) ) or len(set(keys)) != len(keys):
            _fail("bootstrap.installed_file_order_invalid")
        if any(row.normalized_distribution not in names for row in self.installed_files):
            _fail("bootstrap.installed_file_owner_invalid")
        if len({row.installed_relative_path for row in self.installed_files}) != len(self.installed_files):
            _fail("bootstrap.installed_file_locator_duplicate")
        if sum(row.size for row in self.installed_files) > _MAX_TOTAL_BYTES:
            _fail("bootstrap.installed_bytes_exceeded")


@dataclass(frozen=True)
class DeploymentVerificationFacts:
    """Facts core converts to its typed ``DeploymentVerificationReceipt``."""

    configuration_identity_digest: str
    python_implementation: str
    python_version: str
    platform_tag: str
    distributions: tuple[DistributionRow, ...]
    installed_files: tuple[InstalledFileRow, ...]
    install_policy: Literal["wheel-no-compile-v1"]
    cache_policy: Literal["fresh-private-prefix-v1"]
    origin_policy: Literal["selected-distribution-root-v1"]

    def __post_init__(self) -> None:
        _sha(self.configuration_identity_digest)
        _ascii_nonempty(self.python_implementation, "bootstrap.receipt_implementation_invalid")
        _ascii_nonempty(self.python_version, "bootstrap.receipt_version_invalid")
        if type(self.platform_tag) is not str or not self.platform_tag:
            _fail("bootstrap.receipt_platform_invalid")
        if type(self.distributions) is not tuple or any(type(row) is not DistributionRow for row in self.distributions):
            _fail("bootstrap.receipt_distributions_invalid")
        if type(self.installed_files) is not tuple or any(type(row) is not InstalledFileRow for row in self.installed_files):
            _fail("bootstrap.receipt_files_invalid")
        if (self.install_policy, self.cache_policy, self.origin_policy) != (
            "wheel-no-compile-v1", "fresh-private-prefix-v1", "selected-distribution-root-v1"
        ):
            _fail("bootstrap.receipt_policy_invalid")


def deployment_configuration_identity(configuration: DeploymentConfiguration) -> str:
    """Return E, using the same length-prefixed recipe consumed by core."""
    if type(configuration) is not DeploymentConfiguration:
        _fail("bootstrap.configuration_invalid")
    fields: list[bytes] = [
        b"memorii.observation-activation.environment.v1",
        _utf8(configuration.python_implementation), _utf8(configuration.python_version), _utf8(configuration.platform_tag),
        _utf8(configuration.install_policy), _utf8(configuration.cache_policy), _utf8(configuration.origin_policy),
        str(len(configuration.distributions)).encode("ascii"),
    ]
    for row in configuration.distributions:
        fields.extend((_utf8(row.normalized_name), _utf8(row.version), row.wheel_sha256.encode("ascii"), row.record_sha256.encode("ascii"), str(len(row.top_level_roots)).encode("ascii")))
        fields.extend(_utf8(root) for root in row.top_level_roots)
    fields.append(str(len(configuration.installed_files)).encode("ascii"))
    for row in configuration.installed_files:
        fields.extend((_utf8(row.normalized_distribution), _utf8(row.installed_relative_path), str(row.size).encode("ascii"), row.sha256.encode("ascii")))
    return sha256(b"".join(len(field).to_bytes(8, "big") + field for field in fields)).hexdigest()


def verify_deployment(
    configuration: DeploymentConfiguration, *, private_pycache_prefix: Path
) -> DeploymentVerificationFacts:
    """Verify the configured installed closure before importing ``memorii``."""
    if type(configuration) is not DeploymentConfiguration:
        _fail("bootstrap.configuration_invalid")
    _verify_interpreter(configuration, private_pycache_prefix)
    site_fd = _open_anchor(configuration.installation_root)
    try:
        scripts_fd = _open_anchor(configuration.scripts_root)
        try:
            if _same_inode(site_fd, scripts_fd):
                _fail("bootstrap.anchors_overlap")
            _verify_fresh_cache(configuration, site_fd)
            records = _verify_distribution_records(configuration, site_fd, scripts_fd)
            _verify_anchor_closure(configuration, site_fd, scripts_fd, records)
            _verify_distribution_roots(configuration, site_fd)
            _verify_initial_memorii_origin(configuration)
        except OSError as exc:
            raise BootstrapVerificationError("bootstrap.filesystem_verification_failed") from exc
        finally:
            os.close(scripts_fd)
    finally:
        os.close(site_fd)
    return DeploymentVerificationFacts(
        deployment_configuration_identity(configuration), platform.python_implementation(), platform.python_version(),
        sysconfig.get_platform(), configuration.distributions, configuration.installed_files,
        configuration.install_policy, configuration.cache_policy, configuration.origin_policy,
    )


class SelectedDistributionOriginGuard:
    """A meta-path guard that validates specs before their loaders execute."""

    def __init__(self, configuration: DeploymentConfiguration) -> None:
        self._configuration = configuration
        owners: dict[str, tuple[Path, ...]] = {}
        for distribution in configuration.distributions:
            for root in distribution.top_level_roots:
                name = _root_import_name(root)
                roots = owners.setdefault(name, ())
                # A namespace contributor can declare ``google/example``.
                # Its top-level namespace spec is rooted at ``site/google``;
                # the complete site closure still prevents an unrecorded peer.
                owners[name] = (*roots, configuration.installation_root / root.split("/", 1)[0])
        self._owners = owners
        self._installed = False

    def install(self) -> None:
        if self._installed or any(isinstance(finder, SelectedDistributionOriginGuard) for finder in sys.meta_path):
            _fail("bootstrap.origin_guard_already_installed")
        for name, module in tuple(sys.modules.items()):
            allowed = self._owners.get(name.split(".", 1)[0])
            if allowed is not None:
                _verify_spec_origin(getattr(module, "__spec__", None), allowed)
        sys.meta_path.insert(0, self)
        self._installed = True

    def remove(self) -> None:
        if self._installed:
            try:
                sys.meta_path.remove(self)
            except ValueError:
                _fail("bootstrap.origin_guard_missing")
            self._installed = False

    def find_spec(
        self, fullname: str, path: Sequence[str] | None = None, target: ModuleType | None = None
    ) -> importlib.machinery.ModuleSpec | None:
        root_name = fullname.split(".", 1)[0]
        allowed = self._owners.get(root_name)
        for finder in tuple(sys.meta_path):
            if finder is self:
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is None:
                continue
            if allowed is not None:
                _verify_spec_origin(spec, allowed)
            elif _spec_is_under(spec, (self._configuration.installation_root,)):
                _fail("bootstrap.module_owner_unknown")
            return spec
        if allowed is not None:
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        return None


def install_selected_distribution_origin_guard(configuration: DeploymentConfiguration) -> SelectedDistributionOriginGuard:
    """Install a pre-execution guard; retain it through all selected imports."""
    if type(configuration) is not DeploymentConfiguration:
        _fail("bootstrap.configuration_invalid")
    guard = SelectedDistributionOriginGuard(configuration)
    guard.install()
    return guard


def _verify_interpreter(configuration: DeploymentConfiguration, private_pycache_prefix: Path) -> None:
    actual = (platform.python_implementation(), platform.python_version(), sysconfig.get_platform())
    if actual != (configuration.python_implementation, configuration.python_version, configuration.platform_tag):
        _fail("bootstrap.interpreter_mismatch")
    if actual[0] != "CPython":
        _fail("bootstrap.interpreter_unsupported")
    version = sys.version_info
    if version < (3, 11):
        _fail("bootstrap.python_version_unsupported")
    if "memorii" in sys.modules or any(name.startswith("memorii.") for name in sys.modules):
        _fail("bootstrap.memorii_preloaded")
    if not isinstance(private_pycache_prefix, Path) or not private_pycache_prefix.is_absolute():
        _fail("bootstrap.pycache_prefix_invalid")
    prefix = sys.pycache_prefix
    if not isinstance(prefix, str) or not prefix or Path(prefix) != private_pycache_prefix:
        _fail("bootstrap.pycache_prefix_invalid")
    prefix_fd = _open_anchor(Path(prefix))
    try:
        # The launcher owns emptiness at process creation; this catches any
        # preexisting Memorii cache while permitting stdlib cache population.
        if _tree_contains_memorii_bytecode(prefix_fd):
            _fail("bootstrap.pycache_prefix_memorii_bytecode")
    finally:
        os.close(prefix_fd)


def _verify_fresh_cache(configuration: DeploymentConfiguration, site_fd: int) -> None:
    del configuration
    for path, mode in _walk_regular(site_fd):
        if path.endswith(".pyc") or "__pycache__" in path.split("/"):
            _fail("bootstrap.package_bytecode_present")
        if not stat.S_ISREG(mode):
            _fail("bootstrap.site_special_file")


def _verify_distribution_records(configuration: DeploymentConfiguration, site_fd: int, scripts_fd: int) -> dict[str, tuple[str, int, str]]:
    configured = {row.installed_relative_path: row for row in configuration.installed_files}
    claims: dict[str, tuple[str, int, str]] = {}
    for distribution in configuration.distributions:
        record_path = _record_path(distribution, configured)
        record_bytes = _read_exact(site_fd, record_path, _MAX_RECORD_BYTES)
        if sha256(record_bytes).hexdigest() != distribution.record_sha256:
            _fail("bootstrap.record_digest_mismatch")
        metadata_path = record_path.rsplit("/", 1)[0] + "/METADATA"
        metadata = _read_exact(site_fd, metadata_path, _MAX_RECORD_BYTES)
        _verify_metadata(metadata, distribution)
        for raw_path, digest, size in _parse_record(record_bytes, record_path):
            locator = _record_locator(configuration, record_path, raw_path)
            row = configured.get(locator)
            if row is None or row.normalized_distribution != distribution.normalized_name:
                _fail("bootstrap.record_configuration_mismatch")
            if locator in claims:
                _fail("bootstrap.record_duplicate_ownership")
            actual = _hash_file(site_fd if locator.startswith("site/") else scripts_fd, locator.split("/", 1)[1], row.size)
            if (
                actual != row.sha256
                or (digest is None and locator != "site/" + record_path)
                or (digest is not None and (digest != row.sha256 or size != row.size))
            ):
                _fail("bootstrap.record_file_mismatch")
            claims[locator] = (distribution.normalized_name, row.size, row.sha256)
        record_locator = "site/" + record_path
        if record_locator not in claims:
            _fail("bootstrap.record_self_missing")
    if set(claims) != set(configured):
        _fail("bootstrap.record_closure_mismatch")
    return claims


def _verify_anchor_closure(configuration: DeploymentConfiguration, site_fd: int, scripts_fd: int, claims: dict[str, tuple[str, int, str]]) -> None:
    configured = {row.installed_relative_path: row for row in configuration.installed_files}
    for path, mode in _walk_regular(site_fd):
        if not stat.S_ISREG(mode) or "__pycache__" in path.split("/") or path.endswith(".pyc"):
            _fail("bootstrap.site_entry_invalid")
        if "site/" + path not in configured or "site/" + path not in claims:
            _fail("bootstrap.site_entry_unrecorded")
    # Scripts may contain trusted launcher/interpreter files.  A configured
    # script remains distribution payload and must be regular and recorded.
    for locator in (path for path in configured if path.startswith("scripts/")):
        relative = locator.split("/", 1)[1]
        mode = _lstat_at(scripts_fd, relative)
        if not stat.S_ISREG(mode) or locator not in claims:
            _fail("bootstrap.script_entry_invalid")


def _verify_distribution_roots(configuration: DeploymentConfiguration, site_fd: int) -> None:
    seen: dict[str, str] = {}
    for row in configuration.distributions:
        for root in row.top_level_roots:
            owner = seen.setdefault(root, row.normalized_name)
            if owner != row.normalized_name:
                _fail("bootstrap.distribution_root_overlap")
            mode = _lstat_at(site_fd, root)
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                _fail("bootstrap.distribution_root_invalid")


def _verify_initial_memorii_origin(configuration: DeploymentConfiguration) -> None:
    expected = configuration.installation_root / "memorii"
    for entry in sys.path:
        if _path_entry_can_resolve_memorii(entry, expected):
            _fail("bootstrap.memorii_shadow_path")
    spec = importlib.machinery.PathFinder.find_spec("memorii")
    if spec is None or spec.origin is None or not _is_under(Path(spec.origin), (expected,)):
        _fail("bootstrap.memorii_origin_invalid")
    _verify_spec_origin(spec, (expected,))


def _path_entry_can_resolve_memorii(entry: object, expected: Path) -> bool:
    if type(entry) is not str:
        return False
    path = Path(entry or os.curdir)
    try:
        status = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISDIR(status.st_mode):
        for candidate in (path / "memorii", path / "memorii.py"):
            try:
                mode = os.lstat(candidate).st_mode
            except OSError:
                continue
            if (stat.S_ISDIR(mode) or stat.S_ISREG(mode)) and candidate != expected and candidate != expected.with_suffix(".py"):
                return True
        return False
    if stat.S_ISREG(status.st_mode) and zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as archive:
                return any(name == "memorii/__init__.py" or name.startswith("memorii/") or name == "memorii.py" for name in archive.namelist())
        except (OSError, zipfile.BadZipFile):
            return True
    return False


def _record_path(distribution: DistributionRow, configured: dict[str, InstalledFileRow]) -> str:
    candidates = [path.removeprefix("site/") for path, row in configured.items() if row.normalized_distribution == distribution.normalized_name and path.startswith("site/") and path.endswith(".dist-info/RECORD")]
    if len(candidates) != 1 or len(candidates[0].split("/")) != 2:
        _fail("bootstrap.record_path_ambiguous")
    return candidates[0]


def _verify_metadata(raw: bytes, distribution: DistributionRow) -> None:
    metadata = BytesParser().parsebytes(raw, headersonly=True)
    names = metadata.get_all("Name")
    versions = metadata.get_all("Version")
    if names is None or versions is None or len(names) != 1 or len(versions) != 1:
        _fail("bootstrap.metadata_mismatch")
    try:
        name = names[0].encode("ascii").decode("ascii")
        version = versions[0].encode("ascii").decode("ascii")
    except UnicodeError:
        _fail("bootstrap.metadata_mismatch")
    if re.sub(r"[-_.]+", "-", name.lower()) != distribution.normalized_name or version != distribution.version:
        _fail("bootstrap.metadata_mismatch")


def _parse_record(raw: bytes, record_path: str) -> tuple[tuple[str, str | None, int | None], ...]:
    del record_path
    try:
        rows = tuple(csv.reader(StringIO(raw.decode("utf-8", "strict"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise BootstrapVerificationError("bootstrap.record_invalid") from exc
    parsed: list[tuple[str, str | None, int | None]] = []
    seen: set[str] = set()
    for row in rows:
        if len(row) != 3 or not row[0] or row[0] in seen:
            _fail("bootstrap.record_invalid")
        seen.add(row[0])
        digest, size = row[1:]
        if not digest and not size:
            parsed.append((row[0], None, None))
            continue
        if not digest.startswith("sha256=") or not size.isascii() or not size.isdecimal() or (len(size) > 1 and size.startswith("0")):
            _fail("bootstrap.record_invalid")
        try:
            encoded = digest[7:]
            decoded = base64.b64decode(encoded + "=", altchars=b"-_", validate=True)
            if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != encoded:
                _fail("bootstrap.record_invalid")
        except ValueError as exc:
            raise BootstrapVerificationError("bootstrap.record_invalid") from exc
        parsed.append((row[0], decoded.hex(), int(size)))
    return tuple(parsed)


def _record_locator(configuration: DeploymentConfiguration, record_path: str, raw_path: str) -> str:
    del record_path
    if type(raw_path) is not str or not raw_path or "\x00" in raw_path or "\\" in raw_path:
        _fail("bootstrap.record_path_invalid")
    raw = PurePosixPath(raw_path)
    if raw.is_absolute() or len(raw.parts) > _MAX_PATH_DEPTH:
        _fail("bootstrap.record_path_invalid")
    # ``RECORD`` paths are relative to the dist-info parent (the site anchor).
    # Resolve only
    # lexically, then admit the result only when it is under a protected anchor;
    # later descriptor opens enforce no-follow traversal for every component.
    candidate = Path(os.path.normpath(str(configuration.installation_root / raw_path)))
    if _is_under(candidate, (configuration.installation_root,)):
        return "site/" + candidate.relative_to(configuration.installation_root).as_posix()
    if _is_under(candidate, (configuration.scripts_root,)):
        return "scripts/" + candidate.relative_to(configuration.scripts_root).as_posix()
    _fail("bootstrap.record_path_escape")


def _open_anchor(path: Path) -> int:
    if not path.is_absolute() or ".." in path.parts:
        _fail("bootstrap.anchor_not_canonical")
    current = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        for part in path.parts[1:]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
            os.close(current)
            current = following
        if not stat.S_ISDIR(os.fstat(current).st_mode):
            _fail("bootstrap.anchor_invalid")
        return current
    except OSError as exc:
        os.close(current)
        raise BootstrapVerificationError("bootstrap.anchor_invalid") from exc
    except BootstrapVerificationError:
        os.close(current)
        raise


def _same_inode(left: int, right: int) -> bool:
    a, b = os.fstat(left), os.fstat(right)
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _open_relative(root_fd: int, relative: str) -> int:
    _safe_relative(relative)
    current = os.dup(root_fd)
    try:
        parts = relative.split("/")
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index != len(parts) - 1:
                flags |= os.O_DIRECTORY
            following = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = following
        return current
    except OSError as exc:
        os.close(current)
        raise BootstrapVerificationError("bootstrap.nofollow_open_failed") from exc


def _lstat_at(root_fd: int, relative: str) -> int:
    fd = _open_relative(root_fd, relative)
    try:
        return os.fstat(fd).st_mode
    finally:
        os.close(fd)


def _read_exact(root_fd: int, relative: str, maximum: int) -> bytes:
    fd = _open_relative(root_fd, relative)
    try:
        size = os.fstat(fd).st_size
        if not stat.S_ISREG(os.fstat(fd).st_mode) or size > maximum:
            _fail("bootstrap.read_bound_exceeded")
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            data = os.read(fd, min(_CHUNK, remaining))
            if not data:
                _fail("bootstrap.file_changed")
            chunks.append(data)
            remaining -= len(data)
        if os.read(fd, 1):
            _fail("bootstrap.file_changed")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _hash_file(root_fd: int, relative: str, expected_size: int) -> str:
    fd = _open_relative(root_fd, relative)
    try:
        status = os.fstat(fd)
        if not stat.S_ISREG(status.st_mode) or status.st_size != expected_size or expected_size > _MAX_FILE_BYTES:
            _fail("bootstrap.file_size_mismatch")
        digest = sha256()
        remaining = expected_size
        while remaining:
            data = os.read(fd, min(_CHUNK, remaining))
            if not data:
                _fail("bootstrap.file_changed")
            digest.update(data)
            remaining -= len(data)
        if os.read(fd, 1):
            _fail("bootstrap.file_changed")
        return digest.hexdigest()
    finally:
        os.close(fd)


def _walk_regular(root_fd: int) -> tuple[tuple[str, int], ...]:
    result: list[tuple[str, int]] = []
    pending = [""]
    directories = 0
    while pending:
        prefix = pending.pop()
        directories += 1
        if directories > _MAX_FILES:
            _fail("bootstrap.directory_cardinality_exceeded")
        directory_fd = os.dup(root_fd) if not prefix else _open_relative(root_fd, prefix)
        try:
            if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
                _fail("bootstrap.anchor_entry_invalid")
            with os.scandir(directory_fd) as entries:
                for entry in entries:
                    path = entry.name if not prefix else prefix + "/" + entry.name
                    if len(path.split("/")) > _MAX_PATH_DEPTH or entry.is_symlink():
                        _fail("bootstrap.anchor_symlink_or_depth")
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if stat.S_ISDIR(mode):
                        pending.append(path)
                    elif stat.S_ISREG(mode):
                        result.append((path, mode))
                        if len(result) > _MAX_FILES:
                            _fail("bootstrap.cardinality_exceeded")
                    else:
                        _fail("bootstrap.anchor_special_file")
        except OSError as exc:
            raise BootstrapVerificationError("bootstrap.anchor_walk_failed") from exc
        finally:
            os.close(directory_fd)
    return tuple(result)


def _tree_contains_memorii_bytecode(root_fd: int) -> bool:
    for path, _ in _walk_regular(root_fd):
        parts = path.split("/")
        if path.endswith(".pyc") and any(part == "memorii" or part.startswith("memorii.") for part in parts):
            return True
    return False


def _root_import_name(root: str) -> str:
    name = root.split("/", 1)[0]
    if name.endswith(".py"):
        name = name[:-3]
    elif name.endswith((".so", ".pyd", ".dylib")):
        name = name.split(".", 1)[0]
    return name


def _is_under(candidate: Path, roots: tuple[Path, ...]) -> bool:
    try:
        return any(candidate.is_relative_to(root) for root in roots)
    except ValueError:
        return False


def _spec_is_under(spec: object, roots: tuple[Path, ...]) -> bool:
    origin = getattr(spec, "origin", None)
    if origin is None:
        locations = getattr(spec, "submodule_search_locations", None)
        return bool(locations) and all(_is_under(Path(location), roots) for location in locations)
    return isinstance(origin, str) and origin not in ("built-in", "frozen") and _is_under(Path(origin), roots)


def _verify_spec_origin(spec: object, roots: tuple[Path, ...]) -> None:
    """Reject a selected module before its loader can execute package code."""
    if not _spec_is_under(spec, roots):
        if getattr(spec, "origin", None) is None:
            _fail("bootstrap.module_namespace_origin_invalid")
        _fail("bootstrap.module_origin_invalid")

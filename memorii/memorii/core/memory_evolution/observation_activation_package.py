"""Race-resistant installed package verification for an activation target."""

from __future__ import annotations

import base64
import csv
import importlib.metadata
import os
from email.parser import BytesParser
from hashlib import sha256
from io import StringIO
from pathlib import Path

from memorii.core.memory_evolution.observation_activation_target import (
    DeploymentConfiguration,
    ObservationActivationTargetError,
    ObservationActivationTargetManifest,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifestError,
    _open_canonical_source_root,
    _read_whole_file,
)


class ObservationActivationPackageError(ObservationActivationTargetError):
    """The loaded Memorii package is not the configured immutable payload."""


def verify_installed_observation_target(
    configuration: DeploymentConfiguration, manifest: ObservationActivationTargetManifest
) -> None:
    """Verify loaded package, metadata, RECORD, and package bytes without activation."""
    if type(configuration) is not DeploymentConfiguration or type(manifest) is not ObservationActivationTargetManifest:
        raise ObservationActivationPackageError("observation_activation_package_input_invalid")
    try:
        import memorii

        root = configuration.installation_root
        package_file = getattr(memorii, "__file__", None)
        expected_package = root / "memorii"
        if not isinstance(package_file, str) or Path(package_file).parent != expected_package:
            raise ObservationActivationPackageError("observation_activation_package_loaded_root_mismatch")
        distribution = importlib.metadata.distribution("memorii")
        distribution_package = distribution.locate_file("memorii")
        selected = next(row for row in configuration.distributions if row.normalized_name == "memorii")
        if (
            manifest.memorii_distribution_version != selected.version
            or manifest.memorii_wheel_sha256 != selected.wheel_sha256
            or not isinstance(distribution_package, Path)
            or distribution_package != expected_package
        ):
            raise ObservationActivationPackageError("observation_activation_package_metadata_mismatch")
        record_relative = _record_relative_path(configuration)
        descriptor = _open_canonical_source_root(root)
        try:
            scripts_descriptor = _open_canonical_source_root(configuration.scripts_root)
            try:
                site_status = os.fstat(descriptor)
                scripts_status = os.fstat(scripts_descriptor)
                if (site_status.st_dev, site_status.st_ino) == (scripts_status.st_dev, scripts_status.st_ino):
                    raise ObservationActivationPackageError("observation_activation_package_anchors_overlap")
            finally:
                os.close(scripts_descriptor)
            record_bytes = _read_whole_file(descriptor, record_relative, 4 * 1024 * 1024)
            if sha256(record_bytes).hexdigest() != selected.record_sha256:
                raise ObservationActivationPackageError("observation_activation_package_record_digest_mismatch")
            record_rows = _parse_record(record_bytes)
            configured = {row.installed_relative_path: row for row in configuration.installed_files}
            metadata_relative = record_relative.rsplit("/", 1)[0] + "/METADATA"
            metadata_bytes = _read_whole_file(descriptor, metadata_relative, 4 * 1024 * 1024)
            for location, raw in ((record_relative, record_bytes), (metadata_relative, metadata_bytes)):
                installed = configured.get(f"site/{location}")
                if (
                    installed is None
                    or installed.normalized_distribution != "memorii"
                    or installed.sha256 != sha256(raw).hexdigest()
                    or installed.size != len(raw)
                ):
                    raise ObservationActivationPackageError("observation_activation_package_metadata_pin_mismatch")
            metadata = BytesParser().parsebytes(metadata_bytes, headersonly=True)
            if metadata.get_all("Name") != ["memorii"] or metadata.get_all("Version") != [selected.version]:
                raise ObservationActivationPackageError("observation_activation_package_metadata_mismatch")
            if record_rows.get(metadata_relative) != (sha256(metadata_bytes).hexdigest(), len(metadata_bytes)):
                raise ObservationActivationPackageError("observation_activation_package_record_membership_mismatch")
            expected = {row.relative_path: row for row in manifest.package_files}
            actual = _walk_payload(descriptor, frozenset(expected))
            if actual != set(expected):
                raise ObservationActivationPackageError("observation_activation_package_payload_inventory_mismatch")
            configured = {row.installed_relative_path: row for row in configuration.installed_files}
            for path, row in expected.items():
                installed = configured.get(f"site/{path}")
                record = record_rows.get(path)
                if (
                    installed is None
                    or installed.normalized_distribution != "memorii"
                    or installed.sha256 != row.sha256
                    or installed.size != row.size
                    or record != (row.sha256, row.size)
                ):
                    raise ObservationActivationPackageError("observation_activation_package_record_membership_mismatch")
                first = _read_whole_file(descriptor, path, row.size)
                second = _read_whole_file(descriptor, path, row.size)
                if first != second or len(first) != row.size or sha256(first).hexdigest() != row.sha256:
                    raise ObservationActivationPackageError("observation_activation_package_payload_bytes_mismatch")
        finally:
            os.close(descriptor)
    except ObservationActivationPackageError:
        raise
    except (DecoderSourceManifestError, importlib.metadata.PackageNotFoundError, OSError, ValueError, StopIteration) as exc:
        raise ObservationActivationPackageError("observation_activation_package_verification_failed") from exc


def _record_relative_path(configuration: DeploymentConfiguration) -> str:
    matches = [
        row.installed_relative_path.removeprefix("site/")
        for row in configuration.installed_files
        if row.normalized_distribution == "memorii"
        and row.installed_relative_path.startswith("site/")
        and row.installed_relative_path.endswith(".dist-info/RECORD")
    ]
    if len(matches) != 1 or len(matches[0].split("/")) != 2:
        raise ObservationActivationPackageError("observation_activation_package_record_ambiguous")
    return matches[0]


def _parse_record(raw: bytes) -> dict[str, tuple[str, int]]:
    try:
        rows = list(csv.reader(StringIO(raw.decode("utf-8", "strict"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ObservationActivationPackageError("observation_activation_package_record_invalid") from exc
    result: dict[str, tuple[str, int]] = {}
    seen: set[str] = set()
    for row in rows:
        if len(row) != 3 or not row[0] or row[0] in seen:
            raise ObservationActivationPackageError("observation_activation_package_record_invalid")
        seen.add(row[0])
        digest, size = row[1:]
        if not digest and not size:
            if not row[0].endswith(".dist-info/RECORD"):
                raise ObservationActivationPackageError("observation_activation_package_record_unhashed")
            continue
        if (
            not digest.startswith("sha256=")
            or not size.isascii()
            or not size.isdecimal()
            or (len(size) > 1 and size.startswith("0"))
        ):
            raise ObservationActivationPackageError("observation_activation_package_record_invalid")
        try:
            encoded = digest[7:]
            decoded = base64.b64decode(encoded + "=", altchars=b"-_", validate=True)
            if base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != encoded:
                raise ValueError("noncanonical RECORD digest")
        except ValueError as exc:
            raise ObservationActivationPackageError("observation_activation_package_record_invalid") from exc
        if len(decoded) != 32:
            raise ObservationActivationPackageError("observation_activation_package_record_invalid")
        result[row[0]] = (decoded.hex(), int(size))
    return result


def _walk_payload(root_descriptor: int, expected: frozenset[str]) -> set[str]:
    """Walk the finite inventory through bounded no-follow directory handles."""
    directories = {"memorii"}
    for path in expected:
        pieces = path.split("/")
        directories.update("/".join(pieces[:index]) for index in range(1, len(pieces)))
    result: set[str] = set()
    pending = ["memorii"]
    while pending:
        relative = pending.pop()
        handles = [os.dup(root_descriptor)]
        try:
            for segment in relative.split("/"):
                handles.append(os.open(segment, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=handles[-1]))
            with os.scandir(handles[-1]) as entries:
                for entry in entries:
                    path = f"{relative}/{entry.name}"
                    if entry.is_symlink():
                        raise ObservationActivationPackageError("observation_activation_package_payload_symlink")
                    if entry.is_dir(follow_symlinks=False):
                        if path not in directories:
                            raise ObservationActivationPackageError("observation_activation_package_unlisted_directory")
                        pending.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        if path not in expected:
                            raise ObservationActivationPackageError(
                                "observation_activation_package_payload_inventory_mismatch"
                            )
                        result.add(path)
                    else:
                        raise ObservationActivationPackageError("observation_activation_package_payload_special")
        finally:
            for handle in reversed(handles):
                os.close(handle)
    return result

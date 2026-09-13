"""Publish already-signed production revocation evidence without any key material."""

from __future__ import annotations

import argparse
import json
import stat
import sysconfig
from importlib import import_module
from pathlib import Path

from memorii.core.memory_evolution.deployment_authorization import (
    DeploymentAuthorizationError,
    InstalledProductionRevocationReader,
)

_CONFIG_FORMAT = "memorii.semantic-ingestion.revocation-publisher.v1"


def revocation_publisher_config_path() -> Path:
    """Return the one operator-installed publisher configuration coordinate."""
    return (
        Path(sysconfig.get_path("data"))
        / "etc"
        / "memorii"
        / "semantic-ingestion"
        / "revocation-publisher-v1.json"
    )


def _secure_config_bytes(path: Path) -> bytes:
    if not path.is_absolute():
        raise DeploymentAuthorizationError("production_revocation_configuration")
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise DeploymentAuthorizationError("production_revocation_configuration")
        if metadata.st_mode & 0o022:
            raise DeploymentAuthorizationError("production_revocation_configuration")
        current = path.parent
        while current != current.parent:
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode) or metadata.st_mode & 0o022:
                raise DeploymentAuthorizationError("production_revocation_configuration")
            current = current.parent
        value = path.read_bytes()
    except OSError as exc:
        raise DeploymentAuthorizationError("production_revocation_configuration") from exc
    if not value:
        raise DeploymentAuthorizationError("production_revocation_configuration")
    return value


def _installed_publisher():
    """Load fixed public trust and storage coordinates; no caller chooses either."""
    try:
        raw = _secure_config_bytes(revocation_publisher_config_path())
        config = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DeploymentAuthorizationError("production_revocation_configuration") from exc
    if (
        type(config) is not dict
        or set(config) != {"format", "reader_root", "trust_keys"}
        or config["format"] != _CONFIG_FORMAT
        or type(config["trust_keys"]) is not dict
    ):
        raise DeploymentAuthorizationError("production_revocation_configuration")
    try:
        root = Path(config["reader_root"])
        if not root.is_absolute() or root.is_symlink():
            raise ValueError
        keys = {
            coordinate: bytes.fromhex(key)
            for coordinate, key in config["trust_keys"].items()
        }
        if not keys or any(
            not isinstance(coordinate, str)
            or not coordinate
            or not isinstance(key, bytes)
            or len(key) != 32
            for coordinate, key in keys.items()
        ):
            raise ValueError
        reader = InstalledProductionRevocationReader().from_fixed_configuration(
            {"reader_root": str(root)}
        )
        verifier_type = import_module("acceptance.production_revocation").IndependentProductionRevocationEvidenceVerifier
        verifier = verifier_type(
            reader=reader, trust_keys=keys
        )
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        raise DeploymentAuthorizationError("production_revocation_configuration") from exc
    return reader, verifier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-approval-release-digest", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args(argv)
    try:
        reader, verifier = _installed_publisher()
        receipt = Path(args.receipt).read_bytes()
        checkpoint = Path(args.checkpoint).read_bytes()
        verifier.verify(
            prior_approval_release_digest=args.prior_approval_release_digest,
            receipt=receipt,
            checkpoint=checkpoint,
            require_current_reader_bytes=False,
        )
        reader.publish_revocation_evidence(
            prior_approval_release_digest=args.prior_approval_release_digest,
            receipt=receipt,
            checkpoint=checkpoint,
        )
    except (DeploymentAuthorizationError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

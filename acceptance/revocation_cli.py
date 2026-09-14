"""Publish acceptance-verified production revocation evidence.

The command accepts candidate evidence paths only.  Its fixed administrator
configuration supplies both the public verification keys and one serialized
production storage configuration shared by the reader and publisher.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sysconfig
from pathlib import Path

from acceptance.production_revocation import (
    IndependentProductionRevocationEvidenceVerifier,
)
from acceptance.production_revocation_bridge import (
    SerializedProductionRevocationPublisher,
    configured_revocation_publisher,
    configured_revocation_reader,
)

_FORMAT = "memorii.acceptance.revocation-publisher.v1"
_CONFIG = (
    Path(sysconfig.get_path("data")) / "etc" / "memorii" / "acceptance" / "revocation-publisher-v1.json"
)


def revocation_publisher_config_path() -> Path:
    return _CONFIG


def _secure_file(path: Path) -> bytes:
    if not path.is_absolute():
        raise ValueError("acceptance_revocation_configuration")
    current = path
    validated_private_coordinate = False
    while True:
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ValueError("acceptance_revocation_configuration") from exc
        mode = stat.S_IMODE(metadata.st_mode)
        trusted_sticky_ancestor = (
            stat.S_ISDIR(metadata.st_mode)
            and metadata.st_uid in {os.geteuid(), 0}
            and bool(mode & stat.S_ISVTX)
            and validated_private_coordinate
        )
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid not in {os.geteuid(), 0}
            or (mode & 0o022 and not trusted_sticky_ancestor)
        ):
            raise ValueError("acceptance_revocation_configuration")
        if not mode & 0o022:
            validated_private_coordinate = True
        if current.parent == current:
            break
        current = current.parent
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise ValueError("acceptance_revocation_configuration")
    return path.read_bytes()


def _configured() -> tuple[SerializedProductionRevocationPublisher, IndependentProductionRevocationEvidenceVerifier]:
    try:
        value = json.loads(_secure_file(revocation_publisher_config_path()))
        if type(value) is not dict or set(value) != {"format", "storage"}:
            raise ValueError
        if value["format"] != _FORMAT or type(value["storage"]) is not dict:
            raise ValueError
        keys = {name: bytes.fromhex(key) for name, key in value["storage"].get("trust_keys", {}).items()}
        if not keys or any(type(name) is not str or not name or len(key) != 32 for name, key in keys.items()):
            raise ValueError
        reader = configured_revocation_reader(value["storage"])
        publisher = configured_revocation_publisher(value["storage"])
        return publisher, IndependentProductionRevocationEvidenceVerifier(reader=reader, trust_keys=keys)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("acceptance_revocation_configuration") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-approval-release-digest", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args(argv)
    try:
        publisher, verifier = _configured()
        receipt = Path(args.receipt).read_bytes()
        checkpoint = Path(args.checkpoint).read_bytes()
        verifier.verify(
            prior_approval_release_digest=args.prior_approval_release_digest,
            receipt=receipt,
            checkpoint=checkpoint,
            require_current_reader_bytes=False,
        )
        publisher.publish_verified(
            prior_approval_release_digest=args.prior_approval_release_digest,
            receipt=receipt,
            checkpoint=checkpoint,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

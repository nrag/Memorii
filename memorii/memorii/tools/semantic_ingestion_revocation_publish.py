"""Publish already-signed production revocation evidence without any key material."""

from __future__ import annotations

import argparse
from pathlib import Path

from memorii.core.memory_evolution.deployment_authorization import (
    DeploymentAuthorizationError,
    InstalledProductionRevocationReader,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--prior-approval-release-digest", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args(argv)
    try:
        reader = InstalledProductionRevocationReader().from_fixed_configuration(
            {"reader_root": args.root}
        )
        reader.publish_revocation_evidence(
            prior_approval_release_digest=args.prior_approval_release_digest,
            receipt=Path(args.receipt).read_bytes(),
            checkpoint=Path(args.checkpoint).read_bytes(),
        )
    except (DeploymentAuthorizationError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

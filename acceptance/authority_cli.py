"""Publish a prepared acceptance-authority transaction through fixed trust."""

from __future__ import annotations

import argparse
from importlib.metadata import entry_points
from pathlib import Path
import re
from typing import Mapping, Protocol, runtime_checkable

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


@runtime_checkable
class ConfiguredAcceptanceAuthorityPublisher(Protocol):
    def publish_authority(
        self,
        *,
        prepared_objects: Mapping[str, bytes],
        expected_commit_digest: str | None,
        expected_key_head: str | None,
        expected_status_generation: int | None,
        next_commit: bytes,
    ) -> str: ...


def _configured_publisher() -> ConfiguredAcceptanceAuthorityPublisher:
    candidates = tuple(entry_points(group="memorii.acceptance_evaluator_runtime"))
    if len(candidates) != 1:
        raise ValueError("acceptance_runtime_configuration")
    runtime = candidates[0].load()()
    if not isinstance(runtime, ConfiguredAcceptanceAuthorityPublisher):
        raise ValueError("acceptance_runtime_configuration")
    return runtime


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--object",
        action="append",
        default=[],
        metavar="DIGEST=PATH",
        help="Prepared registered artifact; repeat once per reachable object.",
    )
    parser.add_argument("--expected-commit-digest")
    parser.add_argument("--expected-key-head")
    parser.add_argument("--expected-status-generation", type=int)
    return parser


def _objects(values: list[str]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for value in values:
        digest, separator, path = value.partition("=")
        if not separator or not _DIGEST.fullmatch(digest) or digest in result or not path:
            raise ValueError("acceptance_authority_object_argument")
        result[digest] = Path(path).read_bytes()
    return result


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        publisher = _configured_publisher()
        digest = publisher.publish_authority(
            prepared_objects=_objects(args.object),
            expected_commit_digest=args.expected_commit_digest,
            expected_key_head=args.expected_key_head,
            expected_status_generation=args.expected_status_generation,
            next_commit=Path(args.commit).read_bytes(),
        )
    except (OSError, ValueError) as exc:
        _parser().error(str(exc))
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Independent stdlib-only oracle for activation target identity recipes."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _ascii(value: str) -> bytes:
    return value.encode("ascii")


def _utf8(value: str) -> bytes:
    return value.encode("utf-8")


def _lp(parts: list[bytes]) -> bytes:
    return b"".join(len(part).to_bytes(8, "big", signed=False) + part for part in parts)


def _result(parts: list[bytes]) -> dict[str, str]:
    preimage = _lp(parts)
    return {"preimage_hex": preimage.hex(), "sha256": hashlib.sha256(preimage).hexdigest()}


def _decimal(value: int | str) -> str:
    text = str(value)
    if not text.isascii() or not text.isdecimal() or (len(text) > 1 and text[0] == "0"):
        raise ValueError("noncanonical decimal")
    return text


def _ordered(rows: list[dict[str, object]], key) -> list[dict[str, object]]:
    return sorted(rows, key=key)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: identity_oracle.py INPUT.json")

    value = json.loads(Path(sys.argv[1]).read_bytes())
    package_files = _ordered(value["package_files"], lambda row: _utf8(str(row["relative_path"])))
    distributions = _ordered(value["environment"]["distributions"], lambda row: _utf8(str(row["name"])))
    installed_files = _ordered(
        value["environment"]["installed_files"],
        lambda row: (_utf8(str(row["distribution"])), _utf8(str(row["path"]))),
    )
    entries = _ordered(
        value["entries"],
        lambda row: (_utf8(str(row["schema_id"])), _ascii(_decimal(row["schema_version"]))),
    )

    payload_parts = [_ascii("memorii.observation-activation.package-payload.v1")]
    for row in package_files:
        payload_parts.extend(
            (_utf8(str(row["relative_path"])), _ascii(_decimal(row["size"])), _ascii(str(row["sha256"])))
        )
    payload = _result(payload_parts)

    environment = value["environment"]
    environment_parts = [
        _ascii("memorii.observation-activation.environment.v1"),
        _utf8(str(environment["python_implementation"])),
        _utf8(str(environment["python_version"])),
        _utf8(str(environment["platform_tag"])),
        _utf8(str(environment["install_policy"])),
        _utf8(str(environment["cache_policy"])),
        _utf8(str(environment["origin_policy"])),
        _ascii(_decimal(len(distributions))),
    ]
    for row in distributions:
        roots = sorted((_utf8(str(root)) for root in row["top_level_roots"]))
        environment_parts.extend(
            (
                _utf8(str(row["name"])),
                _utf8(str(row["version"])),
                _ascii(str(row["wheel_sha256"])),
                _ascii(str(row["record_sha256"])),
                _ascii(_decimal(len(roots))),
                *roots,
            )
        )
    environment_parts.append(_ascii(_decimal(len(installed_files))))
    for row in installed_files:
        environment_parts.extend(
            (
                _utf8(str(row["distribution"])),
                _utf8(str(row["path"])),
                _ascii(_decimal(row["size"])),
                _ascii(str(row["sha256"])),
            )
        )
    environment_result = _result(environment_parts)

    common = (
        _ascii(str(value["publication_digest"])),
        _ascii(str(value["registry_digest"])),
        _ascii(str(value["decoder_source_manifest_digest"])),
        _ascii(_decimal(len(entries))),
    )
    schema_parts = [
        _ascii("memorii.observation-activation.schema.v1"),
        _ascii(payload["sha256"]),
        _ascii(environment_result["sha256"]),
        *common,
    ]
    codec_parts = [
        _ascii("memorii.observation-activation.ledger-codec.v1"),
        _ascii(payload["sha256"]),
        _ascii(environment_result["sha256"]),
        *common,
    ]
    for row in entries:
        fields = (
            _utf8(str(row["schema_id"])),
            _ascii(_decimal(row["schema_version"])),
            _ascii(str(row["schema_fingerprint"])),
            _ascii(str(row["binding_digest"])),
            _ascii(str(row["entry_digest"])),
        )
        schema_parts.extend(fields)
        codec_parts.extend(
            (*fields, _utf8(str(row["decoder_id"])), _ascii(str(row["implementation_source_digest"])))
        )

    schema = _result(schema_parts)
    codec = _result(codec_parts)
    writer = _result(
        [
            _ascii("memorii.observation-activation.writer.v1"),
            _ascii(payload["sha256"]),
            _ascii(environment_result["sha256"]),
            _ascii(str(value["memorii_wheel_sha256"])),
        ]
    )
    sys.stdout.write(
        json.dumps(
            {"P": payload, "E": environment_result, "schema": schema, "codec": codec, "writer": writer},
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

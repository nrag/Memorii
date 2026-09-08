from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifestError,
    DecoderSourceSelection,
    ProtectedDecoderSourceManifestLimits,
    capture_decoder_source_files,
    parse_canonical_raw_json_object,
    parse_decoder_source_manifest,
    verify_decoder_source_manifest,
)

LIMITS = ProtectedDecoderSourceManifestLimits(
    maximum_manifest_bytes=20_000,
    maximum_manifest_nodes=200,
    maximum_manifest_depth=20,
    maximum_files=10,
    maximum_file_bytes=20_000,
)


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _manifest(rows: list[dict[str, str]]) -> bytes:
    return _raw(
        {
            "role": "decoder_source_manifest",
            "profile_id": "semantic_ingestion_typed_value",
            "profile_version": "3",
            "files": rows,
        }
    )


def _row(decoder_id: str, source_file_id: str, relative_path: str, content: bytes) -> dict[str, str]:
    return {
        "decoder_id": decoder_id,
        "source_file_id": source_file_id,
        "relative_path": relative_path,
        "sha256": sha256(content).hexdigest(),
    }


def test_verifies_shared_whole_file_and_derives_deterministic_snapshots(tmp_path: Path) -> None:
    shared = b"def validate(value):\n    return value\n"
    first = b"def encode_first(value):\n    return value\n"
    second = b"def encode_second(value):\n    return value\n"
    (tmp_path / "decoder").mkdir()
    (tmp_path / "decoder" / "shared.py").write_bytes(shared)
    (tmp_path / "decoder" / "first.py").write_bytes(first)
    (tmp_path / "decoder" / "second.py").write_bytes(second)
    raw = _manifest(
        [
            _row("decoder-a", "encoder", "decoder/first.py", first),
            _row("decoder-a", "validator", "decoder/shared.py", shared),
            _row("decoder-b", "encoder", "decoder/second.py", second),
            _row("decoder-b", "validator", "decoder/shared.py", shared),
        ]
    )

    verified = verify_decoder_source_manifest(raw, source_package_root=tmp_path, limits=LIMITS)

    assert verified.manifest.manifest_digest == sha256(raw).hexdigest()
    assert tuple(snapshot.decoder_id for snapshot in verified.snapshots) == ("decoder-a", "decoder-b")
    assert verified.snapshots[0].source_snapshot_digest != verified.snapshots[1].source_snapshot_digest
    assert tuple(row.raw_bytes for row in verified.snapshots[0].files) == (first, shared)


@pytest.mark.parametrize("relative_path", ["../escape.py", "decoder/../escape.py", "/absolute.py", "decoder\\escape.py", "decoder/%2e.py", "decoder/unicode-\u00e9.py", "decoder/"])
def test_rejects_noncanonical_or_escaping_relative_path(relative_path: str) -> None:
    raw = _manifest([_row("decoder", "source", relative_path, b"x")])
    with pytest.raises(DecoderSourceManifestError, match="relative_path_invalid"):
        parse_decoder_source_manifest(raw, limits=LIMITS)


def test_rejects_symlink_and_source_digest_substitution(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-decoder-source.py"
    outside.write_bytes(b"outside")
    (tmp_path / "decoder").mkdir()
    (tmp_path / "decoder" / "linked.py").symlink_to(outside)
    raw = _manifest([_row("decoder", "source", "decoder/linked.py", b"outside")])
    with pytest.raises(DecoderSourceManifestError, match="source_file_open_failed"):
        verify_decoder_source_manifest(raw, source_package_root=tmp_path, limits=LIMITS)

    (tmp_path / "decoder" / "linked.py").unlink()
    (tmp_path / "decoder" / "linked.py").write_bytes(b"changed")
    with pytest.raises(DecoderSourceManifestError, match="source_file_sha256_mismatch"):
        verify_decoder_source_manifest(raw, source_package_root=tmp_path, limits=LIMITS)


def test_rejects_duplicate_and_conflicting_shared_path_metadata() -> None:
    body = b"source"
    duplicate = _manifest([_row("decoder", "source", "decoder/a.py", body), _row("decoder", "source", "decoder/b.py", body)])
    with pytest.raises(DecoderSourceManifestError, match="decoder_source_file_duplicate"):
        parse_decoder_source_manifest(duplicate, limits=LIMITS)

    conflict = _manifest([_row("decoder-a", "one", "decoder/shared.py", body), _row("decoder-b", "two", "decoder/shared.py", body)])
    with pytest.raises(DecoderSourceManifestError, match="shared_path_metadata_conflict"):
        parse_decoder_source_manifest(conflict, limits=LIMITS)


def test_raw_canonical_intake_preserves_bytes_and_rejects_terminal_lf() -> None:
    raw = _raw({"files": [], "profile_id": "semantic_ingestion_typed_value", "profile_version": "3", "role": "decoder_source_manifest"})
    parsed = parse_canonical_raw_json_object(raw, limits=LIMITS)
    assert parsed.raw_bytes == raw
    with pytest.raises(DecoderSourceManifestError, match="terminal_lf_forbidden"):
        parse_canonical_raw_json_object(raw + b"\n", limits=LIMITS)
    with pytest.raises(DecoderSourceManifestError, match="not_rfc8785_canonical"):
        parse_canonical_raw_json_object(
            b'{"role":"decoder_source_manifest","profile_id":"semantic_ingestion_typed_value","profile_version":"3","files":[]}',
            limits=LIMITS,
        )


def test_rejects_non_utf8_source_even_when_its_raw_sha256_matches(tmp_path: Path) -> None:
    source = b"\xff"
    (tmp_path / "decoder").mkdir()
    (tmp_path / "decoder" / "invalid.py").write_bytes(source)
    raw = _manifest([_row("decoder", "source", "decoder/invalid.py", source)])
    with pytest.raises(DecoderSourceManifestError, match="source_file_utf8_invalid"):
        verify_decoder_source_manifest(raw, source_package_root=tmp_path, limits=LIMITS)


def test_rejects_escaped_unpaired_surrogate_and_fifo_without_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(DecoderSourceManifestError, match="unicode_scalar_invalid"):
        parse_canonical_raw_json_object(b'{"value":"\\ud800"}', limits=LIMITS)

    (tmp_path / "decoder").mkdir()
    fifo = tmp_path / "decoder" / "source.py"
    os.mkfifo(fifo)
    raw = _manifest([_row("decoder", "source", "decoder/source.py", b"")])
    real_open = os.open

    def guarded_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if path == "source.py":
            assert flags & os.O_NONBLOCK
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", guarded_open)
    with pytest.raises(DecoderSourceManifestError, match="source_file_not_regular"):
        verify_decoder_source_manifest(raw, source_package_root=tmp_path, limits=LIMITS)


@pytest.mark.parametrize(
    "generated_path",
    (
        "core/memory_evolution/observation_registry_sources/decoder/Generated/1.json",
        "core/memory_evolution/observation_registry_sources/registry.json",
        "core/memory_evolution/observation_registry_sources/decoder-source-manifest.json",
        "core/memory_evolution/observation_registry_sources/publication-manifest.json",
    ),
)
def test_default_source_exclusion_rejects_every_generated_registry_artifact(tmp_path: Path, generated_path: str) -> None:
    source = b'{"generated":true}'
    generated = tmp_path / generated_path
    generated.parent.mkdir(parents=True)
    generated.write_bytes(source)
    selection = DecoderSourceSelection("decoder", "generated", generated_path)
    raw = _manifest([_row("decoder", "generated", generated_path, source)])

    with pytest.raises(DecoderSourceManifestError, match="generated_source_forbidden"):
        capture_decoder_source_files((selection,), source_package_root=tmp_path, limits=LIMITS)
    with pytest.raises(DecoderSourceManifestError, match="generated_source_forbidden"):
        verify_decoder_source_manifest(raw, source_package_root=tmp_path, limits=LIMITS)


def test_generated_source_root_depth_cannot_evict_the_reserved_namespace(tmp_path: Path) -> None:
    generated_root = tmp_path / "core" / "memory_evolution" / "observation_registry_sources"
    generated_root.mkdir(parents=True)
    (generated_root / "registry.json").write_bytes(b"{}")
    selection = DecoderSourceSelection("decoder", "generated", "registry.json")
    raw = _manifest([_row("decoder", "generated", "registry.json", b"{}")])

    with pytest.raises(DecoderSourceManifestError, match="generated_source_forbidden"):
        capture_decoder_source_files((selection,), source_package_root=generated_root, limits=LIMITS)
    with pytest.raises(DecoderSourceManifestError, match="generated_source_forbidden"):
        verify_decoder_source_manifest(raw, source_package_root=generated_root, limits=LIMITS)


def test_validates_supplemental_exclusions_before_opening_the_source_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _manifest([_row("decoder", "native", "native.py", b"native")])

    def source_root_must_not_open(*args: object, **kwargs: object) -> int:
        raise AssertionError("source root opened before supplemental exclusions were validated")

    monkeypatch.setattr(os, "open", source_root_must_not_open)
    with pytest.raises(DecoderSourceManifestError, match="relative_path_invalid"):
        verify_decoder_source_manifest(
            raw,
            source_package_root=tmp_path,
            limits=LIMITS,
            forbidden_relative_paths=frozenset({"native\\invalid.py"}),
        )


def test_default_source_exclusion_preserves_a_real_native_file(tmp_path: Path) -> None:
    source = b"def decode(value):\n    return value\n"
    (tmp_path / "decoder").mkdir()
    (tmp_path / "decoder" / "native.py").write_bytes(source)
    selection = DecoderSourceSelection("decoder", "native", "decoder/native.py")
    raw = _manifest([_row("decoder", "native", "decoder/native.py", source)])

    assert capture_decoder_source_files((selection,), source_package_root=tmp_path, limits=LIMITS)[0].raw_bytes == source
    assert verify_decoder_source_manifest(raw, source_package_root=tmp_path, limits=LIMITS).files[0].raw_bytes == source

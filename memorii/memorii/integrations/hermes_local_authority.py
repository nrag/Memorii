"""Local Level 2 operator authorization for the installed Hermes provider.

This module only creates and validates the installation-bound configuration
record.  It deliberately does not construct a semantic runtime or OpenAI
client; that belongs to the later production factory composition slice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, NoReturn, cast

from memorii.core.memory_plane import JsonlMemoryPlaneStore, MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord

_SCHEMA_ID: Final = "memorii.semantic_ingestion.local_level2_sidecar"
_AUTHORIZATION_SCHEMA_ID: Final = "memorii.semantic_ingestion.local_level2_profile_authorization"
_AUTHORIZATION_DOMAIN: Final = b"memorii.local_level2_authorization.v1\0"
_SIDECAR_DOMAIN: Final = b"memorii.local_level2_sidecar.v1\0"
_INSTALLATION_DOMAIN: Final = b"memorii.local_level2_installation.v1\0"
_HOME_DOMAIN: Final = b"memorii.local_level2_home.v1\0"
_PROFILE_ID: Final = "memorii.project_assertions"
_PROFILE_VERSION: Final = 1
_PROFILE_SELECTION: Final = "memorii.project_assertions@1"
_MODEL_ID: Final = "gpt-4.1-nano"
_ACKNOWLEDGEMENT: Final = "local_level2_openai_egress"
_AUTHORIZATION_LIFETIME: Final = timedelta(days=7)
_PROFILE_DIGEST_FIELDS: Final = frozenset({
    "profile_manifest_digest",
    "semantic_contract_digest",
    "component_fingerprint_digest",
    "prompt_schema_digest",
    "predicate_catalog_digest",
    "egress_policy_digest",
})
_SIDECAR_FIELDS: Final = frozenset({
    "schema_id",
    "schema_version",
    "installation_id",
    "hermes_home_digest",
    "profile_selection",
    "local_level2_enabled",
    "authorization",
    "sidecar_digest",
})
_AUTHORIZATION_FIELDS: Final = frozenset({
    "schema_id",
    "schema_version",
    "authority_kind",
    "execution_class",
    "profile_id",
    "profile_version",
    "model_id",
    *_PROFILE_DIGEST_FIELDS,
    "installation_principal_digest",
    "hermes_home_digest",
    "issued_at",
    "expires_at",
    "operator_acknowledgement",
    "authorization_digest",
})


class LocalLevel2AuthorityError(ValueError):
    """A local-Level-2 record is unavailable or violates its closed contract."""


@dataclass(frozen=True)
class LocalLevel2Status:
    """Safe operator-facing authority state; it intentionally contains no secret."""

    available: bool
    reason: str | None
    authority: str | None
    profile: str | None
    model: str | None
    expires_at: str | None
    sidecar_digest: str | None
    production_certified: bool

    def as_json(self) -> str:
        return _canonical_json({
            "available": self.available,
            "authority": self.authority,
            "expires_at": self.expires_at,
            "model": self.model,
            "not_production_certified": not self.production_certified,
            "profile": self.profile,
            "reason": self.reason,
            "sidecar_digest": self.sidecar_digest,
        }).decode("ascii")


def authorize_local_level2(*, hermes_home: Path, now: datetime | None = None) -> LocalLevel2Status:
    """Atomically create the one bounded local authorization for this home."""
    profile_digests = _registered_profile_digests()
    try:
        return _authorize_local_level2_with_profile(
            hermes_home=hermes_home,
            now=now,
            profile_digests=profile_digests,
        )
    except OSError as error:
        raise LocalLevel2AuthorityError("local Level 2 authority storage is unavailable") from error


def _authorize_local_level2_with_profile(
    *,
    hermes_home: Path,
    now: datetime | None,
    profile_digests: Mapping[str, str],
) -> LocalLevel2Status:
    issued_at = _utc_now(now)
    home = _canonical_home(hermes_home)
    authority_root = home / "memorii"
    authority_root.mkdir(parents=True, exist_ok=True)
    installation_path = authority_root / "installation-id"
    installation_id = _load_or_create_installation_id(installation_path)
    home_digest = _home_digest(home, installation_id)
    authorization = {
        "schema_id": _AUTHORIZATION_SCHEMA_ID,
        "schema_version": 1,
        "authority_kind": "local_level2_operator",
        "execution_class": "local_level2",
        "profile_id": _PROFILE_ID,
        "profile_version": _PROFILE_VERSION,
        "model_id": _MODEL_ID,
        **profile_digests,
        "installation_principal_digest": _installation_digest(installation_id),
        "hermes_home_digest": home_digest,
        "issued_at": _format_time(issued_at),
        "expires_at": _format_time(issued_at + _AUTHORIZATION_LIFETIME),
        "operator_acknowledgement": _ACKNOWLEDGEMENT,
    }
    authorization["authorization_digest"] = _digest(_AUTHORIZATION_DOMAIN, authorization)
    sidecar = {
        "schema_id": _SCHEMA_ID,
        "schema_version": 1,
        "installation_id": installation_id,
        "hermes_home_digest": home_digest,
        "profile_selection": _PROFILE_SELECTION,
        "local_level2_enabled": True,
        "authorization": authorization,
    }
    sidecar["sidecar_digest"] = _digest(_SIDECAR_DOMAIN, sidecar)
    sidecar_path = authority_root / "local-level2.json"
    _atomic_write(sidecar_path, _canonical_json(sidecar) + b"\n")
    verified = load_local_level2_authority(hermes_home=home, now=issued_at)
    return _status_from_sidecar(verified)


def load_local_level2_authority(*, hermes_home: Path, now: datetime | None = None) -> dict[str, object]:
    """Load one exact sidecar or raise a closed authority-unavailable error."""
    try:
        home = _canonical_home(hermes_home)
        root = home / "memorii"
        installation_id = _read_installation_id(root / "installation-id")
        sidecar = _parse_canonical_sidecar(root / "local-level2.json")
        _validate_sidecar(sidecar, home=home, installation_id=installation_id, now=_utc_now(now))
        return sidecar
    except LocalLevel2AuthorityError:
        raise
    except OSError as error:
        raise LocalLevel2AuthorityError("local Level 2 authority storage is unavailable") from error


def local_level2_status(*, hermes_home: Path, now: datetime | None = None) -> LocalLevel2Status:
    """Return an unavailable diagnostic rather than allowing status to activate anything."""
    try:
        sidecar = load_local_level2_authority(hermes_home=hermes_home, now=now)
    except LocalLevel2AuthorityError as error:
        return LocalLevel2Status(False, str(error), None, None, None, None, None, False)
    return _status_from_sidecar(sidecar)


def inspect_local_memory(*, hermes_home: Path) -> dict[str, object]:
    """Read the installed memory plane without constructing a runtime or calling a model."""
    storage_root = _canonical_home(hermes_home) / "memorii" / "memory-plane"
    records_path = storage_root / "memory_records.jsonl"
    if not records_path.is_file():
        raise LocalLevel2AuthorityError(f"Memorii data was not found at {records_path}")
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage_root))
    write_revision, records = plane.read_write_snapshot()
    return _inspection_summary(storage_root=storage_root, write_revision=write_revision, records=records)


def _inspection_summary(
    *,
    storage_root: Path,
    write_revision: int,
    records: tuple[CanonicalMemoryRecord, ...],
) -> dict[str, object]:
    source_kinds = Counter(record.source_kind for record in records)
    graph_members = tuple(
        record
        for record in records
        if record.source_kind == "semantic_ingestion_bootstrap_graph_v3_member"
    )
    graph_kinds: Counter[str] = Counter()
    terminal_outcomes: Counter[str] = Counter()
    for record in graph_members:
        member = record.content.get("member")
        kind = member.get("kind") if isinstance(member, dict) else None
        graph_kinds[kind if isinstance(kind, str) else "unknown"] += 1
        if kind != "bootstrap_graph_canonical_source_result":
            continue
        try:
            from memorii.core.semantic_ingestion.contracts import (
                BootstrapGraphCanonicalSourceResultV3,
                BootstrapGraphPlanAtomicMemberV3,
                decode_semantic_contract,
            )

            atomic_member = BootstrapGraphPlanAtomicMemberV3.model_validate(
                member, strict=False
            )
            result = decode_semantic_contract(
                atomic_member.canonical_payload,
                BootstrapGraphCanonicalSourceResultV3,
            )
            terminal_outcomes[result.canonical_source_result.final_status] += 1
        except (TypeError, ValueError):
            terminal_outcomes["unknown"] += 1
    return {
        "captured_source_count": source_kinds["semantic_ingestion_source"],
        "graph_record_count": len(graph_members),
        "graph_record_counts_by_kind": dict(sorted(graph_kinds.items())),
        "graph_revision_delta_count": source_kinds[
            "semantic_ingestion_bootstrap_graph_v3_graph_revision_delta"
        ],
        "memory_plane_record_count": len(records),
        "observation_ledger_entry_count": source_kinds[
            "semantic_ingestion_observation_ledger_entry"
        ],
        "operation_terminal_counts_by_outcome": dict(sorted(terminal_outcomes.items())),
        "retrieval_visible_record_count": sum(
            record.visibility.value == "runtime_context" for record in records
        ),
        "runtime_context_projection_count": sum(
            record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
            for record in records
        ),
        "storage_root": str(storage_root),
        "write_revision": write_revision,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage local Level 2 Hermes Memorii authority.")
    commands = parser.add_subparsers(dest="command", required=True)
    authorize = commands.add_parser("authorize-local-level2")
    authorize.add_argument("--hermes-home", type=Path, required=True)
    authorize.add_argument("--acknowledge-openai-egress", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("--hermes-home", type=Path, required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--hermes-home", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "authorize-local-level2":
        if not args.acknowledge_openai_egress:
            parser.error("authorize-local-level2 requires --acknowledge-openai-egress")
        try:
            result = authorize_local_level2(hermes_home=args.hermes_home)
        except LocalLevel2AuthorityError as error:
            result = LocalLevel2Status(False, str(error), None, None, None, None, None, False)
            print(result.as_json())
            return 1
    elif args.command == "status":
        result = local_level2_status(hermes_home=args.hermes_home)
    else:
        try:
            print(json.dumps(inspect_local_memory(hermes_home=args.hermes_home), indent=2, sort_keys=True))
            return 0
        except LocalLevel2AuthorityError as error:
            print(_canonical_json({"available": False, "reason": str(error)}).decode("ascii"))
            return 1
    print(result.as_json())
    return 0


def _status_from_sidecar(sidecar: Mapping[str, object]) -> LocalLevel2Status:
    authorization = _mapping(sidecar["authorization"], "authorization")
    return LocalLevel2Status(
        available=True,
        reason=None,
        authority="local_level2",
        profile=_string(sidecar["profile_selection"], "profile_selection"),
        model=_string(authorization["model_id"], "model_id"),
        expires_at=_string(authorization["expires_at"], "expires_at"),
        sidecar_digest=_string(sidecar["sidecar_digest"], "sidecar_digest"),
        production_certified=False,
    )


def _validate_sidecar(sidecar: Mapping[str, object], *, home: Path, installation_id: str, now: datetime) -> None:
    _exact_fields(sidecar, _SIDECAR_FIELDS, "sidecar")
    if sidecar.get("schema_id") != _SCHEMA_ID or sidecar.get("schema_version") != 1:
        raise LocalLevel2AuthorityError("sidecar schema is unsupported")
    if sidecar.get("installation_id") != installation_id:
        raise LocalLevel2AuthorityError("sidecar installation binding is invalid")
    expected_home_digest = _home_digest(home, installation_id)
    if sidecar.get("hermes_home_digest") != expected_home_digest:
        raise LocalLevel2AuthorityError("sidecar Hermes-home binding is invalid")
    if sidecar.get("profile_selection") != _PROFILE_SELECTION or sidecar.get("local_level2_enabled") is not True:
        raise LocalLevel2AuthorityError("sidecar profile selection is invalid")
    sidecar_digest = _string(sidecar.get("sidecar_digest"), "sidecar_digest")
    if not secrets.compare_digest(sidecar_digest, _digest(_SIDECAR_DOMAIN, _without(sidecar, "sidecar_digest"))):
        raise LocalLevel2AuthorityError("sidecar digest is invalid")
    authorization = _mapping(sidecar.get("authorization"), "authorization")
    _exact_fields(authorization, _AUTHORIZATION_FIELDS, "authorization")
    expected = {
        "schema_id": _AUTHORIZATION_SCHEMA_ID,
        "schema_version": 1,
        "authority_kind": "local_level2_operator",
        "execution_class": "local_level2",
        "profile_id": _PROFILE_ID,
        "profile_version": _PROFILE_VERSION,
        "model_id": _MODEL_ID,
        "installation_principal_digest": _installation_digest(installation_id),
        "hermes_home_digest": expected_home_digest,
        "operator_acknowledgement": _ACKNOWLEDGEMENT,
    }
    expected.update(_registered_profile_digests())
    for field, value in expected.items():
        if authorization.get(field) != value:
            raise LocalLevel2AuthorityError(f"authorization {field} is invalid")
    authorization_digest = _string(authorization.get("authorization_digest"), "authorization_digest")
    if not secrets.compare_digest(
        authorization_digest,
        _digest(_AUTHORIZATION_DOMAIN, _without(authorization, "authorization_digest")),
    ):
        raise LocalLevel2AuthorityError("authorization digest is invalid")
    issued_at = _parse_time(authorization.get("issued_at"), "issued_at")
    expires_at = _parse_time(authorization.get("expires_at"), "expires_at")
    if expires_at != issued_at + _AUTHORIZATION_LIFETIME:
        raise LocalLevel2AuthorityError("authorization expiry is invalid")
    if now >= expires_at:
        raise LocalLevel2AuthorityError("authorization is expired")


def _parse_canonical_sidecar(path: Path) -> dict[str, object]:
    try:
        payload = path.read_bytes()
    except FileNotFoundError as error:
        raise LocalLevel2AuthorityError("local Level 2 authority is absent") from error
    except OSError as error:
        raise LocalLevel2AuthorityError("local Level 2 authority storage is unavailable") from error
    if not payload.endswith(b"\n"):
        raise LocalLevel2AuthorityError("sidecar is not canonical JSON")
    try:
        decoded = payload[:-1].decode("ascii")
        value = json.loads(decoded, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, LocalLevel2AuthorityError) as error:
        raise LocalLevel2AuthorityError("sidecar is not canonical JSON") from error
    if not isinstance(value, dict) or _canonical_json(value) != payload[:-1]:
        raise LocalLevel2AuthorityError("sidecar is not canonical JSON")
    return cast(dict[str, object], value)


def _load_or_create_installation_id(path: Path) -> str:
    if path.exists():
        return _read_installation_id(path)
    installation_id = secrets.token_hex(32)
    try:
        _atomic_write(path, (installation_id + "\n").encode("ascii"), exclusive=True)
    except FileExistsError:
        return _read_installation_id(path)
    return installation_id


def _read_installation_id(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise LocalLevel2AuthorityError("installation identity is absent") from error
    except OSError as error:
        raise LocalLevel2AuthorityError("local Level 2 authority storage is unavailable") from error
    if len(raw) != 65 or raw[-1:] != b"\n":
        raise LocalLevel2AuthorityError("installation identity is invalid")
    try:
        installation_id = raw[:-1].decode("ascii")
    except UnicodeDecodeError as error:
        raise LocalLevel2AuthorityError("installation identity is invalid") from error
    if len(installation_id) != 64 or any(character not in "0123456789abcdef" for character in installation_id):
        raise LocalLevel2AuthorityError("installation identity is invalid")
    return installation_id


def _atomic_write(path: Path, payload: bytes, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(temporary_name)
        try:
            _write_and_sync(descriptor, payload)
            os.close(descriptor)
            descriptor = -1
            # A hard link publishes only if the final path is absent.  The
            # active identity is therefore never exposed as a partial file.
            os.link(temporary_path, path)
            _fsync_directory(path.parent)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary_path.unlink(missing_ok=True)
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        _write_and_sync(descriptor, payload)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _write_and_sync(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("short atomic authority write")
        offset += written
    os.fsync(descriptor)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _canonical_home(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _utc_now(now: datetime | None) -> datetime:
    value = now if now is not None else datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise LocalLevel2AuthorityError("authority clock must be timezone-aware")
    return value.astimezone(UTC).replace(microsecond=0)


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_time(value: object, field: str) -> datetime:
    text = _string(value, field)
    if not text.endswith("Z"):
        raise LocalLevel2AuthorityError(f"authorization {field} is invalid")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise LocalLevel2AuthorityError(f"authorization {field} is invalid") from error
    if _format_time(parsed) != text:
        raise LocalLevel2AuthorityError(f"authorization {field} is invalid")
    return parsed


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(domain: bytes, value: Mapping[str, object]) -> str:
    return hashlib.sha256(domain + _canonical_json(value)).hexdigest()


def _registered_profile_digests() -> dict[str, str]:
    """Return digests computed from the exact installed profile bundle."""
    try:
        from memorii.core.semantic_ingestion.project_assertions_profile import (
            ProjectAssertionsProfileError,
            load_project_assertions_bundle,
        )

        return dict(load_project_assertions_bundle().profile_digests)
    except ProjectAssertionsProfileError as error:
        raise LocalLevel2AuthorityError("local Level 2 profile material is unavailable") from error


def _installation_digest(installation_id: str) -> str:
    return hashlib.sha256(_INSTALLATION_DOMAIN + installation_id.encode("ascii")).hexdigest()


def _home_digest(home: Path, installation_id: str) -> str:
    return hashlib.sha256(
        _HOME_DOMAIN + _canonical_home(home).as_posix().encode("utf-8") + b"\0" + installation_id.encode("ascii")
    ).hexdigest()


def _without(value: Mapping[str, object], field: str) -> dict[str, object]:
    return {key: item for key, item in value.items() if key != field}


def _exact_fields(value: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    if set(value) != expected:
        raise LocalLevel2AuthorityError(f"{label} fields are invalid")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise LocalLevel2AuthorityError(f"{field} is invalid")
    return cast(Mapping[str, object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise LocalLevel2AuthorityError(f"{field} is invalid")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LocalLevel2AuthorityError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> NoReturn:
    raise LocalLevel2AuthorityError("non-finite JSON value")


__all__ = [
    "LocalLevel2AuthorityError",
    "LocalLevel2Status",
    "authorize_local_level2",
    "load_local_level2_authority",
    "local_level2_status",
    "main",
]

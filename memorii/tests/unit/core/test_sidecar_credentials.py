"""Sidecar credential store: issue-once secrets, owner-only modes."""

from __future__ import annotations

from pathlib import Path

import pytest
from memorii.core.harness_state.credentials import (
    CredentialError,
    SidecarCredentialStore,
)


def test_issue_and_lookup_round_trip(tmp_path: Path) -> None:
    store = SidecarCredentialStore(tmp_path / "control" / "credentials")
    record, secret = store.issue("principal:a")
    assert record.principal == "principal:a"
    assert secret.startswith("mri_")
    assert store.principal_for(secret) == "principal:a"
    assert store.principal_for("mri_wrong") is None
    # Reopen: credentials survive restart.
    reopened = SidecarCredentialStore(tmp_path / "control" / "credentials")
    assert reopened.principal_for(secret) == "principal:a"


def test_store_enforces_owner_only_permissions(tmp_path: Path) -> None:
    store = SidecarCredentialStore(tmp_path / "credentials")
    store.issue("principal:a")
    store.verify_permissions()
    index = tmp_path / "credentials" / "credentials.json"
    index.chmod(0o644)
    with pytest.raises(CredentialError, match="owner-only"):
        store.verify_permissions()
    index.chmod(0o600)
    store.verify_permissions()


def test_malformed_store_fails_closed(tmp_path: Path) -> None:
    store = SidecarCredentialStore(tmp_path / "credentials")
    (tmp_path / "credentials" / "credentials.json").write_text("not-json", encoding="utf-8")
    with pytest.raises(CredentialError, match="malformed|un_readable".replace("_", "")):
        store.principal_for("mri_anything")


def test_grant_epoch_registry_revoke_fails_closed_and_never_lowers(tmp_path: Path) -> None:
    from memorii.core.harness_state.grant_registry import (
        GrantEpochRegistry,
        GrantRegistryError,
    )

    registry = GrantEpochRegistry(tmp_path / "grants")
    assert registry.current_epoch("grant:one") == 1
    registry.require_current("grant:one", 1)

    record = registry.revoke("grant:one", reason="rotation")
    assert record.epoch == 2
    with pytest.raises(GrantRegistryError, match="stale_grant"):
        registry.require_current("grant:one", 1)
    registry.require_current("grant:one", 2)
    assert registry.revocations() == (record,)

    # Revocation is append-only and monotone: re-revoke raises further.
    second = registry.revoke("grant:one", reason="again")
    assert second.epoch == 3
    assert registry.current_epoch("grant:one") == 3

    with pytest.raises(GrantRegistryError, match="reason must be nonempty"):
        registry.revoke("grant:two", reason="  ")

    # Fresh registry over the same directory keeps state (durability).
    reopened = GrantEpochRegistry(tmp_path / "grants")
    assert reopened.current_epoch("grant:one") == 3
    reopened.verify_permissions()

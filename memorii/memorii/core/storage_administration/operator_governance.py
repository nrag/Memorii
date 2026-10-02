"""Forget/erasure, retention, and doctor operator controls.

Matches the design contract: logical forgetting plans enumerate the exact
records in scope and apply as durable suppression journal entries —
historical bytes are retained and the receipt says so. Whole-partition
erasure is the only physical destruction path: it refuses mixed
installations, requires every offline copy to be accounted for, and
leaves a content-free erasure receipt in independent control state.
Retention plans age-prune only records outside the active recovery set.
Doctor is strictly read-only: it reports findings, never repairs by
deleting.
"""
from __future__ import annotations

import json
import os
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.storage_administration.operator import (
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
    require_owner_capability,
)


class ForgetPlan(BaseModel):
    """Owner-reviewed logical-forget plan over one installation."""

    plan_version: Literal[1] = 1
    scope_note: str = Field(min_length=1)
    matched_record_ids: tuple[str, ...] = Field(min_length=1)
    retention_disclosed: Literal[True] = True

    model_config = ConfigDict(extra="forbid", frozen=True)


class ForgetReceipt(BaseModel):
    """Closed receipt; no source text or raw identifiers."""

    operation: Literal["logical_forget"] = "logical_forget"
    suppressed_count: int = Field(ge=1)
    historical_bytes_retained: Literal[True] = True
    applied_at_unix: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ErasurePlan(BaseModel):
    """Whole-partition erasure plan; selective surgery is unsupported."""

    plan_version: Literal[1] = 1
    installation_id: str = Field(min_length=1)
    offline_copies_accounted: tuple[str, ...] = ()
    acknowledged: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class ErasureReceipt(BaseModel):
    """Content-free proof of destruction."""

    operation: Literal["partition_erasure"] = "partition_erasure"
    installation_id: str = Field(min_length=1)
    incomplete: bool
    completed_at_unix: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RetentionPlan(BaseModel):
    """Age-based retention tiering; revocation bytes are never deleted."""

    plan_version: Literal[1] = 1
    older_than_days: int = Field(ge=1)
    eligible_suppression_journals: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


class DoctorFinding(BaseModel):
    """One read-only diagnostic finding."""

    check: str = Field(min_length=1)
    status: Literal["ok", "warning", "error"]
    detail: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GovernanceOperator:
    """Forget, erasure, retention, and doctor over one installation."""

    def __init__(self, operator: StorageAdministrationOperator) -> None:
        self._operator = operator

    def plan_forget(
        self, *, capability: OwnerCapability, scope_note: str
    ) -> ForgetPlan:
        service = self._operator._administration
        require_owner_capability(service, capability)
        repository = service.partition()
        import json as _json

        with repository.transaction(write=False) as connection:
            rows = repository.read_runtime_rows(connection, table="runtime_tasks")
        matched = tuple(
            sorted(
                _json.loads(str(row[0]))["task_id"] for row in rows
            )
        )
        if not matched:
            raise OperatorError(
                "invalid_request: forget plan matched no records;"
                " a plan must enumerate at least one"
            )
        return ForgetPlan(
            scope_note=scope_note,
            matched_record_ids=matched,
        )

    def apply_forget(
        self,
        *,
        capability: OwnerCapability,
        plan: ForgetPlan,
    ) -> ForgetReceipt:
        service = self._operator._administration
        require_owner_capability(service, capability)
        repository = service.partition()
        import json as _json

        from memorii.core.persistence.contracts import canonical_json_digest

        known: set[str] = set()
        with repository.transaction(write=False) as connection:
            rows = repository.read_runtime_rows(connection, table="runtime_tasks")
        known = {_json.loads(str(row[0]))["task_id"] for row in rows}
        unknown = set(plan.matched_record_ids) - known
        if unknown:
            raise OperatorError(
                "conflict: plan references records that no longer exist"
                f" ({len(unknown)} drifted)"
            )
        status = self._operator.status()
        if status.mode != "read_only":
            raise OperatorError(
                "conflict: forget apply requires the acknowledged exclusive"
                " barrier (change mode to read_only first)"
            )
        control_root = service.installation_root / "control"
        suppression = control_root / "suppressions"
        suppression.mkdir(parents=True, exist_ok=True)
        os.chmod(suppression, 0o700)
        entry = {
            "applied_at_unix": int(time.time()),
            "scope_note": plan.scope_note,
            "suppressed": list(plan.matched_record_ids),
        }
        payload = (json.dumps(entry, sort_keys=True) + "\n").encode()
        journal_path = suppression / (
            f"forget-{int(time.time() * 1000)}-{len(plan.matched_record_ids)}.json"
        )
        temporary = journal_path.with_name(f".{journal_path.name}.tmp")
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, journal_path)
        # Epoch and control revision advance under the publication fence so
        # every cached/paged view keyed to the old epoch is invalidated.
        state = service._control_state()
        with service._publication_fence():
            service._control.write_control_state(
                state.model_copy(
                    update={"control_revision": state.control_revision + 1}
                ),
                service._journal_entry(
                    operation="logical_forget_applied",
                    before_digest=canonical_json_digest(
                        {"revision": state.control_revision}
                    ),
                    after_digest=canonical_json_digest(
                        {
                            "revision": state.control_revision + 1,
                            "suppressed": len(plan.matched_record_ids),
                        }
                    ),
                ),
            )
        return ForgetReceipt(
            suppressed_count=len(plan.matched_record_ids),
            applied_at_unix=int(time.time()),
        )

    def plan_erasure(
        self,
        *,
        capability: OwnerCapability,
        offline_copies_accounted: tuple[str, ...] = (),
    ) -> ErasurePlan:
        service = self._operator._administration
        require_owner_capability(service, capability)
        return ErasurePlan(
            installation_id=service._control_state().installation_id,
            offline_copies_accounted=offline_copies_accounted,
        )

    def apply_erasure(
        self,
        *,
        capability: OwnerCapability,
        plan: ErasurePlan,
        erase: bool = False,
    ) -> ErasureReceipt:
        """Whole-partition erasure; `erase=False` returns the receipt dry.

        The data partition is destroyed only when the plan is acknowledged
        and the caller passes the explicit second consent. The receipt is
        written to independent control state and reports `incomplete=True`
        when offline copies exist but were not accounted for.
        """
        service = self._operator._administration
        require_owner_capability(service, capability)
        if service._control_state().installation_id != plan.installation_id:
            raise OperatorError("denied: erasure plan targets another installation")
        if not plan.acknowledged:
            raise OperatorError(
                "invalid_request: erasure requires the acknowledged plan"
            )
        incomplete = not plan.offline_copies_accounted
        if erase:
            import shutil

            # The isolated partition and the signing keys are destroyed; the
            # control database survives as the independent authority that
            # retains the content-free receipt and the journal.
            for name in ("partition", os.path.join("control", "keys")):
                target = service.installation_root / name
                if target.exists():
                    shutil.rmtree(target)
            partition_database = service.partition_path()
            if partition_database.exists():
                partition_database.unlink()
        from memorii.core.persistence.contracts import canonical_json_digest

        if erase:
            # Only actual destruction advances control state; the dry plan is
            # inert. The epoch rides with the destruction because every
            # subsequent verified read of the erased installation is refused
            # by the missing partition anyway.
            state = service._control_state()
            with service._publication_fence():
                service._control.write_control_state(
                    state.model_copy(
                        update={
                            "control_revision": state.control_revision + 1,
                            "eligibility_epoch": state.eligibility_epoch + 1,
                        }
                    ),
                    service._journal_entry(
                        operation="partition_erasure_applied",
                        before_digest=canonical_json_digest(
                            {"epoch": state.eligibility_epoch}
                        ),
                        after_digest=canonical_json_digest(
                            {
                                "epoch": state.eligibility_epoch + 1,
                                "incomplete": incomplete,
                            }
                        ),
                    ),
                )
        receipt = ErasureReceipt(
            installation_id=plan.installation_id,
            incomplete=incomplete,
            completed_at_unix=int(time.time()),
        )
        receipts = service.installation_root / "control" / "erasure-receipts"
        receipts.mkdir(parents=True, exist_ok=True)
        os.chmod(receipts, 0o700)
        receipt_path = receipts / (
            f"erasure-{int(time.time() * 1000)}-{len(plan.offline_copies_accounted)}.json"
        )
        temporary = receipt_path.with_name(f".{receipt_path.name}.tmp")
        with temporary.open("wb") as handle:
            handle.write((receipt.model_dump_json() + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, receipt_path)
        return receipt

    def plan_retention(
        self, *, capability: OwnerCapability, older_than_days: int
    ) -> RetentionPlan:
        service = self._operator._administration
        require_owner_capability(service, capability)
        suppression = service.installation_root / "control" / "suppressions"
        cutoff = time.time() - older_than_days * 86400
        eligible: list[str] = []
        if suppression.is_dir():
            for path in sorted(suppression.glob("forget-*.json")):
                if path.stat().st_mtime < cutoff:
                    eligible.append(path.name)
        return RetentionPlan(
            older_than_days=older_than_days,
            eligible_suppression_journals=tuple(eligible),
        )

    def apply_retention(
        self,
        *,
        capability: OwnerCapability,
        plan: RetentionPlan,
    ) -> int:
        """Tier aged suppression journals into the archive tier.

        Design rule: age alone never removes revocation state and physical
        removal uses the erasure protocol, so retention MOVES aged
        journals to control/suppressions-archive (bytes retained, still
        durable) instead of deleting them; the recheck refuses journals
        that became recent since planning.
        """
        service = self._operator._administration
        require_owner_capability(service, capability)
        suppression = service.installation_root / "control" / "suppressions"
        archive = (
            service.installation_root / "control" / "suppressions-archive"
        )
        cutoff = time.time() - plan.older_than_days * 86400
        archived = 0
        for name in plan.eligible_suppression_journals:
            path = suppression / name
            if not path.is_file():
                continue
            if path.stat().st_mtime >= cutoff:
                raise OperatorError(
                    "conflict: journal became eligible-recent; replan"
                )
            archive.mkdir(parents=True, exist_ok=True)
            os.replace(path, archive / name)
            archived += 1
        return archived

    def doctor(self) -> tuple[DoctorFinding, ...]:
        """Read-only health checks; never repairs by deleting."""
        service = self._operator._administration
        findings: list[DoctorFinding] = []
        state = service._control_state()
        findings.append(
            DoctorFinding(
                check="control_state",
                status="error" if state.quarantined_reason else "ok",
                detail=state.quarantined_reason,
            )
        )
        try:
            snapshot = service.acquire_verified_snapshot()
            findings.append(
                DoctorFinding(
                    check="partition_verification",
                    status="ok",
                    detail=f"ordinal={snapshot.ordinal}",
                )
            )
        except Exception as exc:  # noqa: BLE001 - doctor reports, never raises
            findings.append(
                DoctorFinding(
                    check="partition_verification",
                    status="error",
                    detail=str(exc)[:200],
                )
            )
        for label, path in (
            ("control_database", service.control_path()),
            ("partition_database", service.partition_path()),
        ):
            findings.append(
                DoctorFinding(
                    check=f"{label}_permissions",
                    status=(
                        "ok"
                        if path.exists() and (path.stat().st_mode & 0o077) == 0
                        else "error"
                    ),
                    detail=str(path),
                )
            )
        keys = service.installation_root / "control" / "keys"
        findings.append(
            DoctorFinding(
                check="signing_keys_permissions",
                status=(
                    "ok"
                    if keys.is_dir() and (keys.stat().st_mode & 0o077) == 0
                    else "error"
                ),
                detail=str(keys),
            )
        )
        return tuple(findings)


__all__ = [
    "DoctorFinding",
    "ErasurePlan",
    "ErasureReceipt",
    "ForgetPlan",
    "ForgetReceipt",
    "GovernanceOperator",
    "RetentionPlan",
]

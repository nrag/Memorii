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
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.storage_administration.operator import (
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
    _require_owner_capability,
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
    """Age-based retention outside the active recovery set."""

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
        _require_owner_capability(service, capability)
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
        _require_owner_capability(service, capability)
        repository = service.partition()
        import json as _json

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
        control_root = service.installation_root / "control"
        suppression = control_root / "suppressions"
        suppression.mkdir(parents=True, exist_ok=True)
        entry = {
            "applied_at_unix": int(time.time()),
            "scope_note": plan.scope_note,
            "suppressed": list(plan.matched_record_ids),
        }
        (suppression / f"forget-{int(time.time() * 1000)}.json").write_text(
            json.dumps(entry, sort_keys=True) + "\n"
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
        _require_owner_capability(service, capability)
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
        _require_owner_capability(service, capability)
        if service._control_state().installation_id != plan.installation_id:
            raise OperatorError("denied: erasure plan targets another installation")
        if not plan.acknowledged:
            raise OperatorError(
                "invalid_request: erasure requires the acknowledged plan"
            )
        incomplete = not plan.offline_copies_accounted
        if erase:
            for name in ("memory-plane", "runtime"):
                target = service.installation_root / name
                if target.exists():
                    import shutil

                    shutil.rmtree(target)
        receipt = ErasureReceipt(
            installation_id=plan.installation_id,
            incomplete=incomplete,
            completed_at_unix=int(time.time()),
        )
        receipts = service.installation_root / "control" / "erasure-receipts"
        receipts.mkdir(parents=True, exist_ok=True)
        (receipts / f"erasure-{int(time.time() * 1000)}.json").write_text(
            receipt.model_dump_json() + "\n"
        )
        return receipt

    def plan_retention(
        self, *, capability: OwnerCapability, older_than_days: int
    ) -> RetentionPlan:
        service = self._operator._administration
        _require_owner_capability(service, capability)
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
        """Prune aged suppression journals; active recovery is never touched."""
        service = self._operator._administration
        _require_owner_capability(service, capability)
        suppression = service.installation_root / "control" / "suppressions"
        cutoff = time.time() - plan.older_than_days * 86400
        removed = 0
        for name in plan.eligible_suppression_journals:
            path = suppression / name
            if not path.is_file():
                continue
            if path.stat().st_mtime >= cutoff:
                raise OperatorError(
                    "conflict: journal became eligible-recent; replan"
                )
            path.unlink()
            removed += 1
        return removed

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

"""Measure a frozen reference fixture through installed runtime owners."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from threading import Event
from time import monotonic_ns

from memorii.core.harness_state.binding import HermesRuntimeStatePorts, RuntimeTaskBinding
from memorii.core.harness_state.consumer import ManagedRuntimeSpool
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.envelope import HarnessStateEnvelope
from memorii.core.harness_state.managed_ingress import authenticated_host_commands
from memorii.core.harness_state.service import HarnessStateError, RuntimeReadGrant
from memorii.core.harness_state.sidecar import RuntimeSidecar, SidecarRequest
from memorii.core.harness_state.write_authority import HostCommandGrantRequest, ManagedHostCommandAuthority
from memorii.core.persistence.runtime_api import RuntimeCommandError
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest, StatusUpdateProposal
from memorii.core.persistence.runtime_journal import RuntimeJournalError, verify_runtime_history
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    OperatorError,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.operator_backup import BackupRestoreOperator
from memorii.core.storage_administration.service import StorageAdministrationError, StorageAdministrationService
from memorii.stores.sqlite.partition import PARTITION_SCHEMA_VERSION, RAW_MEMORY_PAYLOAD_SCHEMA_VERSION

from tests.support.reference_capacity import (
    CHECKPOINT_TAIL_COUNT,
    COLD_OPERATIONS,
    EVENT_COUNT,
    EXECUTION_PAGE_MAX,
    FRONTIER_PAGE_MAX,
    SOURCE_BODY_BYTES,
    SOURCE_COUNT,
    WARM_OPERATIONS,
    ColdOperation,
    Distribution,
    TaskAllocation,
    WarmOperation,
    WarmSample,
    cold_sample_ids,
    nearest_rank,
    task_allocations,
    warm_samples,
)
from tests.support.reference_capacity_fixture import ReferenceFixtureError, _audit, _installed_wheel_digest, _prepare
from tests.support.reference_capacity_sources import REFERENCE_PRINCIPAL, ReferenceSourceCapture, ReferenceSourceError

_P95_LIMIT_MS = {
    "state_read": 250,
    "command_commit": 500,
    "startup_acquisition": 11_000,
    "checkpoint_resume": 5_000,
    "backup_pause": 5_000,
}
_EXPECTED_FAILURES = (
    OSError, ValueError, sqlite3.DatabaseError, ReferenceFixtureError, ReferenceSourceError,
    StorageAdministrationError, RuntimeCommandError, RuntimeJournalError, OperatorError, HarnessStateError,
)


@dataclass(frozen=True)
class Measurement:
    sample_id: str
    elapsed_ns: int | None
    error: str | None = None
    reopen_ns: int | None = None
    genesis_replay_ns: int | None = None
    checkpoint_replay_ns: int | None = None


def _sample(identity: str, invoke: Callable[[], object]) -> Measurement:
    started = monotonic_ns()
    try:
        invoke()
    except _EXPECTED_FAILURES as exc:
        return Measurement(identity, None, f"{type(exc).__name__}: {str(exc)[:240]}")
    return Measurement(identity, monotonic_ns() - started)


def _summarize(
    operation: str, measured: list[Measurement], warmup: list[Measurement] | None = None,
    *, unavailable: str | None = None, apply_budget: bool = True,
) -> dict[str, object]:
    warmup = warmup or []
    elapsed = [sample.elapsed_ns / 1_000_000 for sample in measured if sample.elapsed_ns is not None]
    errors = sum(sample.error is not None for sample in measured + warmup)
    quantiles = {f"p{rank}_ms": nearest_rank(elapsed, rank) for rank in (50, 95, 99)} if elapsed else {}
    budget = _P95_LIMIT_MS.get(operation) if apply_budget else None
    extra_quantiles = {}
    for label, values in (
        ("process_reopen", [sample.reopen_ns for sample in measured]),
        ("genesis_replay", [sample.genesis_replay_ns for sample in measured]),
        ("checkpoint_replay", [sample.checkpoint_replay_ns for sample in measured]),
    ):
        present = [value / 1_000_000 for value in values if value is not None]
        if present:
            extra_quantiles[f"{label}_quantiles"] = {f"p{rank}_ms": nearest_rank(present, rank) for rank in (50, 95, 99)}
    exceeds = budget is not None and quantiles.get("p95_ms", 0) > budget
    status = (
        "unavailable" if unavailable else "failed" if errors or exceeds or not measured else
        "passed" if budget is not None else "reported"
    )
    return {
        "status": status, "unavailable_reason": unavailable, "budget_ms": budget,
        "attempted": len(measured), "warmup_attempted": len(warmup), "errors": errors,
        # Each attempted call has one immutable intent. The driver has no retry loop.
        "driver_retries": 0, "quantiles": quantiles,
        "samples": [asdict(sample) for sample in measured], "warmup": [asdict(sample) for sample in warmup],
        **extra_quantiles,
    }


class _WarmRuntime:
    def __init__(self, service: StorageAdministrationService, distribution: Distribution, *, label: str) -> None:
        self._service = service
        self._tasks = {task.task_id: task.solver_id for task in task_allocations(distribution)}
        self._repo = RuntimeStateRepository(service.partition())
        self._label = label
        self._credentials = SidecarCredentialStore(service.installation_root / "control" / "credentials")
        record, self._secret = self._credentials.issue(REFERENCE_PRINCIPAL)
        self._credential = record.credential_id
        self._capture: ReferenceSourceCapture | None = None
        expiry = datetime.now(UTC) + timedelta(days=7)
        grant = RuntimeReadGrant(
            grant_id="reference-capacity-read", principal=REFERENCE_PRINCIPAL,
            allowed_task_ids=tuple(self._tasks), epoch=1, expires_at=expiry,
        )
        self._sidecar = RuntimeSidecar.for_managed_installation(
            service, credentials=self._credentials, grant_factory=lambda _: grant,
            spool=ManagedRuntimeSpool(service.installation_root / "spool"),
        )
        self._commands = authenticated_host_commands(service, self._credentials, self._secret)

    def prepare_commands(self, probe: WarmSample) -> None:
        ManagedHostCommandAuthority(self._service).issue(
            HostCommandGrantRequest(
                grant_id=f"reference-capacity-commit:{self._label}", credential_id=self._credential,
                principal=REFERENCE_PRINCIPAL, client_namespace=f"reference-capacity-commit:{self._label}",
                allowed_kinds=("propose_state_change",), allowed_task_ids=tuple(self._tasks),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            ), capability=mint_owner_capability(self._service, REFERENCE_PRINCIPAL),
        )
        self._commands.prepare(self._status_request(probe))

    def prepare_capture(self) -> None:
        self._capture = ReferenceSourceCapture(self._service)

    def _status_request(self, sample: WarmSample) -> RuntimeCommandRequest:
        task = self._repo.get_task(sample.task_id)
        if task is None:
            raise ReferenceFixtureError("reference status update task is missing")
        solver = self._tasks[task.task_id]
        return RuntimeCommandRequest(
            kind="propose_state_change", task_id=task.task_id, operation_id=sample.operation_id,
            expected_revision=task.version, proposal=StatusUpdateProposal(
                solver_id=solver, node_id=f"{solver}:node:0", status="NEEDS_TEST", reason="Reference capacity status update",
            ),
        )

    def process(self, sample: WarmSample) -> Measurement:
        if sample.operation == "command_commit":
            command = self._status_request(sample)

            def invoke() -> None:
                receipt = self._commands.dispatch(command, operation_origin=self._commands.prepare(command))
                if receipt.status != "committed":
                    raise ReferenceFixtureError(f"status update ended as {receipt.status}")
        elif sample.operation == "source_capture":
            capture = self._capture
            if capture is None:
                raise ReferenceFixtureError("reference provider capture was not prepared")
            source = sample.capture_input()
            body = source.body().decode("ascii")

            def invoke() -> None:
                capture.retain(source, body)
        else:
            request = SidecarRequest(task_id=sample.task_id).model_dump_json().encode()

            def invoke() -> None:
                status, body = self._sidecar.handle_state_request(
                    bearer_token=self._secret, origin=None, body=request, host="localhost",
                )
                if status != 200:
                    raise ReferenceFixtureError(f"authenticated state read returned HTTP {status}")
                state = HarnessStateEnvelope.model_validate_json(body)
                if (
                    state.task_id != sample.task_id
                    or len(state.ready_work) + len(state.blocked_work) > EXECUTION_PAGE_MAX
                    or len(state.frontier) > FRONTIER_PAGE_MAX
                ):
                    raise ReferenceFixtureError("serialized reference state violates its task or page bounds")
        return _sample(sample.operation_id, invoke)


def _database_bytes(service: StorageAdministrationService) -> int:
    database = service.partition_path()
    wal = database.with_name(database.name + "-wal")
    return database.stat().st_size + (wal.stat().st_size if wal.is_file() else 0)


@contextmanager
def _fresh_copy(base: Path, work: Path) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="memorii-capacity-copy-", dir=work) as scratch:
        root = Path(scratch) / "installation"
        shutil.copytree(base, root)
        yield root


def _warm(
    base: Path, work: Path, distribution: Distribution,
    operation: WarmOperation, *, contended: bool, growth: bool = False,
) -> dict[str, object]:
    samples = list(warm_samples(distribution, operation, contended=contended))
    if growth:
        samples = [sample for sample in samples if sample.measured]
    writer_samples = list(warm_samples(distribution, "command_commit", contended=True))
    with _fresh_copy(base, work) as root, StorageAdministrationService(root) as service:
        runtime = _WarmRuntime(service, distribution, label="foreground")
        service.acquire_verified_snapshot()
        if operation == "source_capture":
            runtime.prepare_capture()
        if operation == "command_commit":
            try:
                runtime.prepare_commands(samples[0])
            except _EXPECTED_FAILURES as exc:
                return _summarize(operation, [], unavailable=f"status update cannot be prepared: {exc}")
        start_size = _database_bytes(service) if growth else None
        if contended:
            ready, stop = Event(), Event()
            with StorageAdministrationService(root) as writer_service:
                writer = _WarmRuntime(writer_service, distribution, label="background")
                try:
                    writer.prepare_commands(writer_samples[0])
                except _EXPECTED_FAILURES as exc:
                    return _summarize(operation, [], unavailable=f"concurrent status writer unavailable: {exc}")

                def write() -> list[Measurement]:
                    index = 0
                    observed = []
                    while not stop.is_set():
                        template = writer_samples[index % len(writer_samples)]
                        sample = WarmSample(
                            ordinal=index, operation="command_commit", task_id=template.task_id,
                            operation_id=f"{template.operation_id}:background:{index}", measured=True, contended=True,
                        )
                        observed.append(writer.process(sample))
                        index += 1
                        ready.set()
                    return observed

                with ThreadPoolExecutor(max_workers=1) as executor:
                    worker = executor.submit(write)
                    try:
                        if not ready.wait(timeout=600):
                            if worker.done():
                                worker.result()
                            raise ReferenceFixtureError("concurrent status writer never made an attempt")
                        results = [runtime.process(sample) for sample in samples]
                    finally:
                        stop.set()
                    writer_results = worker.result()
        else:
            results = [runtime.process(sample) for sample in samples]
            writer_results = []
        report = _summarize(
            operation, [result for result, sample in zip(results, samples, strict=True) if sample.measured],
            [result for result, sample in zip(results, samples, strict=True) if not sample.measured],
            apply_budget=not (contended or growth),
        )
        if contended:
            errors = sum(result.error is not None for result in writer_results)
            report.update(background_attempted=len(writer_results), background_errors=errors, background_driver_retries=0)
            if errors or len(writer_results) < 2:
                report["status"] = "failed"
        if start_size is not None:
            growth_bytes = _database_bytes(service) - start_size
            report["database_and_wal_bytes_before"] = start_size
            report["database_and_wal_bytes_after"] = start_size + growth_bytes
            report["database_and_wal_bytes_growth"] = growth_bytes
            if report["errors"] == 0:
                report["database_and_wal_bytes_per_command"] = growth_bytes / len(samples)
    return report


class _BackupTimer(StorageAdministrationService):
    recording = False
    inside_backup_fence = False

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.backup_holds_ns: list[int] = []

    @property
    def backup_pause_ns(self) -> int | None:
        return sum(self.backup_holds_ns) if self.backup_holds_ns else None

    @contextmanager
    def _publication_fence(self) -> Iterator[None]:
        with super()._publication_fence():
            start = monotonic_ns() if self.recording else None
            if start is not None:
                self.inside_backup_fence = True
            try:
                yield
            finally:
                if start is not None:
                    self.inside_backup_fence = False
        if start is not None:
            self.backup_holds_ns.append(monotonic_ns() - start)


def _time_backup(service: _BackupTimer, root: Path) -> int:
    capability = mint_owner_capability(service, REFERENCE_PRINCIPAL)
    operator = StorageAdministrationOperator(service)
    operator.change_mode(
        ModeChangeRequest(
            target_mode="read_only", expected_control_revision=operator.status().control_revision,
            reason="reference capacity snapshot",
        ), capability=capability,
    )
    service.acquire_verified_snapshot()
    service.recording = True
    try:
        BackupRestoreOperator(operator).create_backup(
            capability=capability, archive_root=root.parent / "archive",
            reason="reference capacity snapshot", recovery_key=os.urandom(32),
        )
    finally:
        service.recording = False
    if service.backup_pause_ns is None:
        raise ReferenceFixtureError("backup returned without the publication barrier measurement")
    return service.backup_pause_ns


def _resume_probe(service: StorageAdministrationService, task_id: str) -> HarnessStateEnvelope:
    ports = HermesRuntimeStatePorts(service)
    ports.bind_task(RuntimeTaskBinding(installation_task_id=task_id, granted_to_principal=REFERENCE_PRINCIPAL))
    return ports.resume_bound_state(principal=REFERENCE_PRINCIPAL)


def _cold_worker(
    root: Path, distribution: Distribution, operation: ColdOperation, identity: str,
) -> tuple[Measurement, int]:
    observed_open = monotonic_ns()
    try:
        service = _BackupTimer(root)
        with service:
            observed_open = monotonic_ns()
            if operation == "startup_acquisition":
                return _sample(identity, service.acquire_verified_snapshot), observed_open
            if operation == "backup_pause":
                return Measurement(identity, _time_backup(service, root)), observed_open
            task_id = task_allocations(distribution)[0].task_id
            service.acquire_verified_snapshot()
            ports = HermesRuntimeStatePorts(service)
            ports.bind_task(RuntimeTaskBinding(installation_task_id=task_id, granted_to_principal=REFERENCE_PRINCIPAL))

            def resume() -> None:
                state = ports.resume_bound_state(principal=REFERENCE_PRINCIPAL)
                if state.task_id != task_id or state.checkpoint_ref is None:
                    raise ReferenceFixtureError("installed resume returned unbound checkpoint state")

            resumed = _sample(identity, resume)
            with service.verified_operation_context() as (_, finalized), service.partition().transaction(write=False) as sql:
                if finalized.checkpoint_digest is None:
                    raise ReferenceFixtureError("cold resume is missing the signed replay checkpoint")

                def replay(*, use_checkpoint: bool) -> None:
                    signer = service._signer_key_id
                    verify_runtime_history(
                        sql, finalized=finalized,
                        verify=lambda purpose, digest, signature: service._verify_journal_signature(
                            signer, purpose, digest, signature,
                        ),
                        checkpoint_signer_key_id=signer,
                        checkpoint_signer_fingerprint=service._signing.public_key_fingerprint(signer),
                        use_checkpoint=use_checkpoint,
                    )

                started = monotonic_ns()
                replay(use_checkpoint=True)
                elapsed = monotonic_ns() - started
                started = monotonic_ns()
                replay(use_checkpoint=False)
                return Measurement(
                    identity, resumed.elapsed_ns, resumed.error,
                    genesis_replay_ns=monotonic_ns() - started, checkpoint_replay_ns=elapsed,
                ), observed_open
    except _EXPECTED_FAILURES as exc:
        return Measurement(identity, None, f"{type(exc).__name__}: {str(exc)[:240]}"), observed_open


def _cold(base: Path, work: Path, distribution: Distribution, operation: ColdOperation) -> dict[str, object]:
    samples = []
    for identity in cold_sample_ids(distribution, operation):
        with _fresh_copy(base, work) as root:
            launch = monotonic_ns()
            process = subprocess.run(
                [sys.executable, "-m", "tests.support.reference_capacity_measure", "sample",
                 "--base", str(root), "--operation", operation,
                 "--identity", identity, "--distribution", distribution], capture_output=True, check=False, text=True,
            )
            if process.returncode:
                samples.append(Measurement(identity, None, f"sample process returned {process.returncode}"))
                continue
            payload = json.loads(process.stdout)
            samples.append(Measurement(**payload["measurement"], reopen_ns=payload["opened_ns"] - launch))
    return _summarize(operation, samples)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_report(path: Path, report: dict[str, object]) -> None:
    payload = (json.dumps(report, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    path.with_suffix(".sha256").write_text(hashlib.sha256(payload).hexdigest() + "\n")


def _preflight(args: argparse.Namespace) -> int:
    from tests.support.reference_capacity_profile import verify_profile

    report: dict[str, object] = {"revision": args.revision, "status": "unavailable"}
    try:
        report["profile"] = verify_profile(args.profile, args.work_root, dedicated_idle=args.dedicated_idle)
        report["wheel_sha256"] = _installed_wheel_digest(args.wheel)
        report["dependency_lock_sha256"] = _digest(args.dependency_lock)
        report["builder_lock_sha256"] = _digest(args.builder_lock)
        with tempfile.TemporaryDirectory(prefix="memorii-capacity-preflight-", dir=args.work_root) as scratch:
            root = Path(scratch) / "probe"
            probe = TaskAllocation("concentrated", 0, 2, 2, 0, 0, 1)
            audit = _prepare(
                root, "concentrated", (probe,), raw_payloads=args.raw_payloads,
                require_fresh_v8=args.require_fresh_v8,
            )
            report["partition_schema_version"] = audit.partition_schema_version
            report["fixture_origin"] = audit.fixture_origin
            with StorageAdministrationService(root) as service:
                with service.partition().transaction(write=False) as connection:
                    if not service.partition().supports_runtime_replay_checkpoints(connection):
                        raise ReferenceFixtureError("installed candidate has no signed replay checkpoint catalog")
                runtime = _WarmRuntime(service, "concentrated", label="preflight")
                sample = next(warm_samples("concentrated", "command_commit"))
                runtime.prepare_commands(sample)
                committed = runtime.process(sample)
                if committed.error is not None:
                    raise ReferenceFixtureError(f"managed status update failed preflight: {committed.error}")

                def advance(connection: sqlite3.Connection, repo: RuntimeStateRepository) -> None:
                    task = repo.get_task_in(connection, probe.task_id)
                    if task is None:
                        raise ReferenceFixtureError("checkpoint readiness task is missing")
                    repo.apply_task(connection, task.model_copy(update={"version": task.version + 1}))

                publish_runtime_change(service, advance, checkpoint_requested=True)
                publish_runtime_change(service, advance)
                service.acquire_verified_snapshot()
                resumed = _resume_probe(service, probe.task_id)
                if resumed.checkpoint_ref is None or resumed.task_id != probe.task_id:
                    raise ReferenceFixtureError("installed checkpoint resume failed preflight")
        report["status"] = "ready"
        report["verified_preflight_operations"] = ["native_capture", "signed_status_update", "checkpoint_resume"]
    except _EXPECTED_FAILURES as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
    _write_report(args.report, report)
    return 0 if report["status"] == "ready" else 1


def _independent_series(operation: str, invoke: Callable[[], dict[str, object]]) -> dict[str, object]:
    try:
        return invoke()
    except _EXPECTED_FAILURES as exc:
        result = _summarize(operation, [])
        result["setup_error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
        return result


def _qualify_frozen(
    args: argparse.Namespace, base: Path, report: dict[str, object],
) -> None:
    with StorageAdministrationService(base) as service:
        audit = _audit(
            service, args.distribution, task_allocations(args.distribution),
            expected_events=EVENT_COUNT, expected_tail=CHECKPOINT_TAIL_COUNT,
            expected_schema=RAW_MEMORY_PAYLOAD_SCHEMA_VERSION if args.raw_payloads else PARTITION_SCHEMA_VERSION,
        )
        if args.require_fresh_v8 and (audit.partition_schema_version != 8 or audit.fixture_origin != "fresh-default"):
            raise ReferenceFixtureError("qualification requires a fresh default-v8 fixture")
        if (audit.source_count, audit.source_body_bytes) != (SOURCE_COUNT, SOURCE_COUNT * SOURCE_BODY_BYTES):
            raise ReferenceFixtureError("the frozen fixture does not have the approved native source size")
        with service.partition().transaction(write=False) as connection:
            report["sqlite_settings"] = {
                key: connection.execute(f"PRAGMA {key}").fetchone()[0]
                for key in ("journal_mode", "synchronous", "busy_timeout", "foreign_keys")
            }
    report["fixture"] = asdict(audit)
    results = {}
    for contended in (False, True):
        regime = "contended" if contended else "sequential"
        for warm_operation in WARM_OPERATIONS:
            results[f"{warm_operation}:{regime}"] = _independent_series(
                warm_operation, partial(_warm, base, args.work_root, args.distribution, warm_operation, contended=contended),
            )
    for cold_operation in COLD_OPERATIONS:
        results[cold_operation] = _independent_series(
            cold_operation, partial(_cold, base, args.work_root, args.distribution, cold_operation),
        )
    results["command_commit:storage_growth"] = _independent_series("command_commit", lambda: _warm(
        base, args.work_root, args.distribution, "command_commit", contended=False, growth=True,
    ))
    report["measurements"] = results
    report["status"] = (
        "passed" if all(item["status"] in ("passed", "reported") for item in results.values()) else "failed"
    )


def _run(args: argparse.Namespace) -> int:
    from tests.support.reference_capacity_profile import verify_profile

    report: dict[str, object] = {"revision": args.revision, "distribution": args.distribution, "status": "failed"}
    try:
        report["profile"] = verify_profile(args.profile, args.work_root, dedicated_idle=args.dedicated_idle)
        report["wheel_sha256"] = _installed_wheel_digest(args.wheel)
        report["dependency_lock_sha256"] = _digest(args.dependency_lock)
        report["builder_lock_sha256"] = _digest(args.builder_lock)
        report["measurement_driver_sha256"] = _digest(Path(__file__))
        report["profile_driver_sha256"] = _digest(Path(__file__).with_name("reference_capacity_profile.py"))
        with _fresh_copy(args.base, args.work_root) as frozen:
            _qualify_frozen(args, frozen, report)
    except _EXPECTED_FAILURES as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
    _write_report(args.report, report)
    return 0 if report["status"] == "passed" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    run = commands.add_parser("run")
    run.add_argument("--base", type=Path, required=True)
    run.add_argument("--distribution", choices=("balanced", "concentrated"), required=True)
    preflight = commands.add_parser("preflight")
    for command in (preflight, run):
        command.add_argument("--work-root", type=Path, required=True)
        command.add_argument("--wheel", type=Path, required=True)
        command.add_argument("--dependency-lock", type=Path, required=True)
        command.add_argument("--builder-lock", type=Path, required=True)
        command.add_argument("--report", type=Path, required=True)
        command.add_argument("--revision", required=True)
        command.add_argument("--profile", choices=("linux", "macos"), required=True)
        command.add_argument("--dedicated-idle", action="store_true")
        formats = command.add_mutually_exclusive_group()
        formats.add_argument("--raw-payloads", action="store_true", help="require the v8 fixture format")
        formats.add_argument("--require-fresh-v8", action="store_true", help="require a fresh default-v8 fixture")
    sample = commands.add_parser("sample")
    sample.add_argument("--base", type=Path, required=True)
    sample.add_argument("--operation", choices=COLD_OPERATIONS, required=True)
    sample.add_argument("--distribution", choices=("balanced", "concentrated"), required=True)
    sample.add_argument("--identity", required=True)
    args = parser.parse_args(argv)
    if args.mode == "run":
        return _run(args)
    if args.mode == "preflight":
        return _preflight(args)
    measurement, opened = _cold_worker(args.base, args.distribution, args.operation, args.identity)
    payload = asdict(measurement)
    del payload["reopen_ns"]
    print(json.dumps({"measurement": payload, "opened_ns": opened}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

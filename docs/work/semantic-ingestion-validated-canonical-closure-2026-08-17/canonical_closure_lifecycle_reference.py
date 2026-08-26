from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from threading import Lock, Thread
from typing import Callable


HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "canonical-closure-operation-contract-v1.json"
OUTPUT = HERE / "canonical-closure-lifecycle-reference-v1.json"


@dataclass(frozen=True)
class Scope:
    tenant: str
    operation: str
    generation: int
    fence: int
    writer: str


@dataclass(frozen=True)
class Metrics:
    mode: str
    terminal_reason: str
    roots: int
    member_paths: int
    lookups: int
    hits: int
    misses: int
    capacity_refusals: int
    peak_charged_bytes: int
    reserved_bytes: int
    released: bool


class Sink:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.events: list[Metrics] = []

    def record(self, event: Metrics) -> str:
        self.events.append(event)
        return "recorded" if self.available else "unavailable"


class Reservations:
    def __init__(self, operation_bytes: int, process_bytes: int) -> None:
        self.operation_bytes = operation_bytes
        self.process_bytes = process_bytes
        self._lock = Lock()
        self.reserved = 0
        self.acquisitions = 0
        self.releases = 0

    def acquire(self) -> bool:
        with self._lock:
            if self.reserved + self.operation_bytes > self.process_bytes:
                return False
            self.reserved += self.operation_bytes
            self.acquisitions += 1
            return True

    def release(self) -> None:
        with self._lock:
            if self.reserved < self.operation_bytes:
                raise RuntimeError("reservation underflow")
            self.reserved -= self.operation_bytes
            self.releases += 1


class Capability:
    def __init__(self, issuer: object, scope: Scope) -> None:
        self.issuer = issuer
        self.scope = scope


class ScopeOwner:
    def __init__(self, contract: dict, reservations: Reservations, sink: Sink, scope: Scope, enabled: bool = True) -> None:
        self.contract = contract
        self.reservations = reservations
        self.sink = sink
        self.scope = scope
        self.state = "new"
        self.mode = "enabled"
        self.issuer = object()
        self.capability: Capability | None = None
        self.entries: set[str] = set()
        self.leases = 0
        self.held = False
        self.emitted = False
        self.roots = self.paths = self.charge = self.peak = 0
        self.lookups = self.hits = self.misses = self.refusals = 0
        self._lock = Lock()
        if not enabled:
            self.mode = "disabled_full_path"
            self._move("select_disabled", "disabled")
            self._emit("feature_disabled")
        elif reservations.acquire():
            self.held = True
            self._move("reserve_succeeded", "reserved")
        else:
            self.mode = "capacity_rejected_full_path"
            self.refusals = 1
            self._move("reserve_refused", "rejected")
            self._emit("capacity_refused")

    def _move(self, event: str, target: str) -> None:
        if [self.state, event, target] not in self.contract["transitions"]:
            raise ValueError("invalid lifecycle transition")
        self.state = target

    def begin(self) -> None:
        with self._lock:
            self._move("begin_staging", "staging")

    def admit(self, key: str, root_bytes: int, paths: int, charge: int) -> bool:
        with self._lock:
            if self.state != "staging":
                raise ValueError("admission outside staging")
            limits = self.contract["limits"]
            over = (
                self.roots + 1 > limits["roots_per_operation"]
                or root_bytes > limits["root_bytes"]
                or self.paths + paths > limits["member_paths_per_operation"]
                or self.charge + charge > limits["operation_reserved_bytes"]
            )
            if over:
                self.mode = "capacity_rejected_full_path"
                self.refusals += 1
                self.entries.clear()
                self._move("capacity_refused", "rejected")
                self._release()
                self._emit("capacity_refused")
                return False
            self.entries.add(key)
            self.roots += 1
            self.paths += paths
            self.charge += charge
            self.peak = max(self.peak, self.charge)
            return True

    def seal(self) -> Capability:
        with self._lock:
            self._move("seal", "sealed")
            self.capability = Capability(self.issuer, self.scope)
            return self.capability

    def lease(self, capability: Capability, scope: Scope, key: str) -> bool:
        with self._lock:
            if self.state != "sealed":
                raise ValueError("lookup outside sealed state")
            if capability is not self.capability or capability.issuer is not self.issuer:
                raise ValueError("forged capability")
            if capability.scope != self.scope or scope != self.scope:
                raise ValueError("foreign scope")
            self.lookups += 1
            if key not in self.entries:
                self.misses += 1
                return False
            self.hits += 1
            self.leases += 1
            return True

    def release_lease(self) -> None:
        with self._lock:
            if self.leases == 0:
                raise RuntimeError("lease underflow")
            self.leases -= 1
            if self.state == "closing" and self.leases == 0:
                self._move("last_lease_released", "closed")
                self._finish("completed")

    def close(self, reason: str = "completed") -> None:
        with self._lock:
            if self.state in {"closed", "disabled", "rejected"}:
                return
            if self.state != "sealed":
                raise ValueError("close outside sealed state")
            if self.leases:
                self._move("close_with_leases", "closing")
            else:
                self._move("close_without_leases", "closed")
                self._finish(reason)

    def abort(self, reason: str) -> None:
        with self._lock:
            if self.state not in {"reserved", "staging"}:
                raise ValueError("abort outside pre-seal state")
            self.entries.clear()
            self._move("abort", "closed")
            self._finish(reason)

    def _release(self) -> None:
        if self.held:
            self.reservations.release()
            self.held = False

    def _finish(self, reason: str) -> None:
        self.entries.clear()
        self.capability = None
        self.charge = 0
        self._release()
        self._emit(reason)

    def _emit(self, reason: str) -> None:
        if self.emitted:
            raise RuntimeError("duplicate terminal metrics")
        self.emitted = True
        self.sink.record(Metrics(
            self.mode, reason, self.roots, self.paths, self.lookups, self.hits,
            self.misses, self.refusals, self.peak,
            self.contract["limits"]["operation_reserved_bytes"] if self.mode == "enabled" else 0,
            not self.held,
        ))


def rejected(action: Callable[[], object]) -> bool:
    try:
        action()
    except (RuntimeError, ValueError):
        return True
    return False


def run() -> dict:
    contract = json.loads(CONTRACT.read_text())
    limits = contract["limits"]
    checks: dict[str, bool] = {}

    disabled_sink = Sink()
    disabled_res = Reservations(limits["operation_reserved_bytes"], limits["process_reserved_bytes"])
    ScopeOwner(contract, disabled_res, disabled_sink, Scope("t", "d", 1, 1, "w"), False)
    checks["disabled_allocates_nothing"] = disabled_res.reserved == 0 and len(disabled_sink.events) == 1

    shared = Reservations(limits["operation_reserved_bytes"], limits["process_reserved_bytes"])
    owners: list[ScopeOwner] = []
    output_lock = Lock()
    def construct(index: int) -> None:
        owner = ScopeOwner(contract, shared, Sink(), Scope("t", str(index), 1, 1, "w"))
        with output_lock:
            owners.append(owner)
    threads = [Thread(target=construct, args=(index,)) for index in range(5)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    checks["concurrent_process_limit"] = sum(o.state == "reserved" for o in owners) == 4 and sum(o.state == "rejected" for o in owners) == 1
    for owner in owners:
        if owner.state == "reserved": owner.abort("cancelled")
    checks["concurrent_exact_release"] = shared.reserved == 0 and shared.acquisitions == shared.releases == 4

    exact_sink, exact_res = Sink(), Reservations(limits["operation_reserved_bytes"], limits["process_reserved_bytes"])
    scope = Scope("t", "exact", 1, 1, "w")
    exact = ScopeOwner(contract, exact_res, exact_sink, scope)
    exact.begin()
    for index in range(8):
        exact.admit(str(index), limits["root_bytes"], 4096, limits["root_bytes"])
    cap = exact.seal()
    checks["exact_limit_seals"] = exact.lease(cap, scope, "0")
    exact.close()
    checks["close_blocks_new_leases"] = exact.state == "closing" and rejected(lambda: exact.lease(cap, scope, "1"))
    exact.release_lease()
    exact.close()
    checks["lease_drain_exact_release"] = exact.state == "closed" and exact_res.releases == 1 and len(exact_sink.events) == 1

    refused_sink, refused_res = Sink(False), Reservations(limits["operation_reserved_bytes"], limits["process_reserved_bytes"])
    refused = ScopeOwner(contract, refused_res, refused_sink, Scope("t", "r", 1, 1, "w"))
    refused.begin()
    for index in range(8): refused.admit(str(index), limits["root_bytes"], 4096, limits["root_bytes"])
    checks["over_limit_rejects_before_capability"] = not refused.admit("over", 1, 0, 1) and refused.capability is None and refused_res.reserved == 0
    checks["sink_unavailability_isolated"] = refused.state == "rejected" and len(refused_sink.events) == 1

    forge_res = Reservations(limits["operation_reserved_bytes"], limits["process_reserved_bytes"])
    forge_scope = Scope("t", "f", 1, 1, "w")
    forge = ScopeOwner(contract, forge_res, Sink(), forge_scope)
    forge.begin(); forge.admit("k", 1, 1, 1); real = forge.seal()
    checks["forged_capability_rejected"] = rejected(lambda: forge.lease(Capability(object(), forge_scope), forge_scope, "k"))
    checks["foreign_scope_rejected"] = rejected(lambda: forge.lease(real, Scope("t", "other", 1, 1, "w"), "k"))
    checks["stale_generation_rejected"] = rejected(lambda: forge.lease(real, Scope("t", "f", 2, 1, "w"), "k"))
    forge.close()

    fields = set(asdict(exact_sink.events[0]))
    checks["metric_fields_exact"] = fields == set(contract["metrics"]["allowed_fields"])
    checks["metrics_content_free"] = fields.isdisjoint(contract["metrics"]["forbidden_content"])
    checks["terminal_metrics_once"] = all(len(o.sink.events) == 1 for o in owners) and len(disabled_sink.events) == len(exact_sink.events) == len(refused_sink.events) == 1
    checks["transitions_unique"] = len({tuple(item) for item in contract["transitions"]}) == len(contract["transitions"])
    checks["capability_sealed_only"] = contract["capability"]["exposed_states"] == ["sealed"]

    return {
        "schema": "memorii.canonical-closure-lifecycle-reference-result.v1",
        "passed": all(checks.values()),
        "checks": checks,
        "check_count": len(checks),
        "contract_schema": contract["schema"],
        "limits": limits,
        "evidence_maturity": "locally_verified_reference_model",
        "production_implementation_claimed": False,
        "ci_enforcement_claimed": False
    }


if __name__ == "__main__":
    result = run()
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    if not result["passed"]: raise SystemExit(1)

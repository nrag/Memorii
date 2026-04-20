"""Deterministic routing policy for inbound event classes."""

from memorii.domain.enums import CommitStatus, Durability, MemoryDomain, MemoryScope
from memorii.domain.routing import InboundEventClass


class RoutingPolicy:
    def route_domains(self, event_class: InboundEventClass, payload: dict[str, object] | None = None) -> list[MemoryDomain]:
        payload = payload or {}
        policy: dict[InboundEventClass, list[MemoryDomain]] = {
            InboundEventClass.USER_MESSAGE: [MemoryDomain.TRANSCRIPT],
            InboundEventClass.AGENT_MESSAGE: [MemoryDomain.TRANSCRIPT],
            InboundEventClass.TOOL_RESULT: [MemoryDomain.TRANSCRIPT],
            InboundEventClass.EXECUTION_STATE_UPDATE: [MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION],
            InboundEventClass.SOLVER_OBSERVATION: [MemoryDomain.TRANSCRIPT, MemoryDomain.SOLVER],
            InboundEventClass.SOLVER_RESOLUTION: [MemoryDomain.TRANSCRIPT, MemoryDomain.SOLVER, MemoryDomain.EPISODIC],
            InboundEventClass.VALIDATED_ABSTRACTION_CANDIDATE: [MemoryDomain.SEMANTIC],
            InboundEventClass.USER_PREFERENCE_CANDIDATE: [MemoryDomain.TRANSCRIPT, MemoryDomain.USER],
            InboundEventClass.CHECKPOINT_EVENT: [MemoryDomain.EXECUTION],
            InboundEventClass.RESUME_EVENT: [MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION, MemoryDomain.SOLVER],
        }
        domains = list(policy[event_class])

        if event_class == InboundEventClass.TOOL_RESULT and self._is_failure_signal(payload):
            if MemoryDomain.EXECUTION not in domains:
                domains.append(MemoryDomain.EXECUTION)
            if MemoryDomain.SOLVER not in domains:
                domains.append(MemoryDomain.SOLVER)

        return domains

    def _is_failure_signal(self, payload: dict[str, object]) -> bool:
        outcome = payload.get("outcome")
        status = payload.get("status")
        result = payload.get("result")
        return outcome == "failed" or status == "failed" or result == "failed"

    def primary_store_for(self, domain: MemoryDomain) -> str:
        return domain.value

    def secondary_stores_for(self, event_class: InboundEventClass, domain: MemoryDomain) -> list[str]:
        if event_class == InboundEventClass.SOLVER_RESOLUTION and domain == MemoryDomain.SOLVER:
            return [MemoryDomain.EPISODIC.value]
        return []

    def status_for(self, event_class: InboundEventClass, domain: MemoryDomain) -> CommitStatus:
        if domain in {MemoryDomain.SEMANTIC, MemoryDomain.USER, MemoryDomain.EPISODIC}:
            return CommitStatus.CANDIDATE
        if event_class in {InboundEventClass.SOLVER_OBSERVATION, InboundEventClass.SOLVER_RESOLUTION} and domain == MemoryDomain.SOLVER:
            return CommitStatus.CANDIDATE
        return CommitStatus.COMMITTED

    def scope_for(self, event_class: InboundEventClass) -> MemoryScope:
        if event_class in {InboundEventClass.CHECKPOINT_EVENT, InboundEventClass.RESUME_EVENT}:
            return MemoryScope.TASK
        if event_class in {InboundEventClass.SOLVER_OBSERVATION, InboundEventClass.SOLVER_RESOLUTION}:
            return MemoryScope.EXECUTION_NODE
        return MemoryScope.TASK

    def durability_for(self, domain: MemoryDomain) -> Durability:
        if domain == MemoryDomain.TRANSCRIPT:
            return Durability.TASK_PERSISTENT
        if domain in {MemoryDomain.SEMANTIC, MemoryDomain.USER, MemoryDomain.EPISODIC}:
            return Durability.LONG_TERM
        return Durability.TASK_PERSISTENT

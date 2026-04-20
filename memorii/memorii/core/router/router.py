"""Memory router that classifies events and emits typed routing decisions."""

from datetime import UTC, datetime

from memorii.core.router.classifier import EventClassifier
from memorii.core.router.routing_policy import RoutingPolicy
from memorii.domain.common import Provenance, RoutingInfo
from memorii.domain.enums import MemoryDomain, SourceType
from memorii.domain.memory_object import MemoryObject
from memorii.domain.routing import InboundEvent, InboundEventClass, NamespaceKey, RoutedMemoryObject, RoutingDecision, RoutingMetadata


class MemoryRouter:
    def __init__(self, classifier: EventClassifier | None = None, policy: RoutingPolicy | None = None) -> None:
        self._classifier = classifier or EventClassifier()
        self._policy = policy or RoutingPolicy()

    def route_event(self, event: InboundEvent) -> RoutingDecision:
        event_class = self._classifier.classify(event)
        decision = RoutingDecision(event_id=event.event_id)

        for domain in self._policy.route_domains(event_class=event_class, payload=event.payload):
            if domain in {MemoryDomain.SEMANTIC, MemoryDomain.USER} and event_class in {
                InboundEventClass.USER_MESSAGE,
                InboundEventClass.AGENT_MESSAGE,
                InboundEventClass.TOOL_RESULT,
            }:
                decision.blocked_domains.append(domain)
                decision.policy_trace.append(f"blocked:{domain.value}:raw_event")
                continue

            now = event.timestamp if event.timestamp.tzinfo is not None else datetime.now(UTC)
            memory = MemoryObject(
                memory_id=f"{event.event_id}:{domain.value}",
                memory_type=domain,
                scope=self._policy.scope_for(event_class),
                durability=self._policy.durability_for(domain),
                status=self._policy.status_for(event_class, domain),
                content={"raw": event.payload} if domain == MemoryDomain.TRANSCRIPT else event.payload,
                provenance=Provenance(
                    source_type=self._source_type(event_class),
                    source_refs=[event.event_id],
                    created_at=now,
                    created_by="memory_router",
                ),
                routing=RoutingInfo(
                    primary_store=self._policy.primary_store_for(domain),
                    secondary_stores=self._policy.secondary_stores_for(event_class, domain),
                ),
                namespace=self._namespace_dict(domain=domain, event=event),
            )
            routed = RoutedMemoryObject(
                memory_object=memory,
                domain=domain,
                metadata=RoutingMetadata(
                    scope=memory.scope,
                    namespace=NamespaceKey(
                        memory_domain=domain,
                        task_id=event.task_id,
                        execution_node_id=event.execution_node_id,
                        solver_run_id=event.solver_run_id,
                        agent_id=event.agent_id,
                    ),
                    primary_store=memory.routing.primary_store,
                    secondary_stores=memory.routing.secondary_stores,
                ),
            )
            decision.routed_objects.append(routed)
            decision.policy_trace.append(f"routed:{domain.value}")

        return decision

    def _namespace_dict(self, domain: MemoryDomain, event: InboundEvent) -> dict[str, str]:
        values = {
            "memory_domain": domain.value,
            "task_id": event.task_id,
        }
        if event.execution_node_id is not None:
            values["execution_node_id"] = event.execution_node_id
        if event.solver_run_id is not None:
            values["solver_run_id"] = event.solver_run_id
        if event.agent_id is not None:
            values["agent_id"] = event.agent_id
        return values

    def _source_type(self, event_class: object) -> SourceType:
        name = str(getattr(event_class, "value", event_class))
        if "user" in name:
            return SourceType.USER
        if "agent" in name:
            return SourceType.AGENT
        if "tool" in name:
            return SourceType.TOOL
        if "checkpoint" in name or "resume" in name:
            return SourceType.SYSTEM
        return SourceType.DERIVED

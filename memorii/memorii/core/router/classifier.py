"""Inbound event classifier for memory routing."""

from memorii.domain.routing import InboundEvent, InboundEventClass


class EventClassifier:
    """Normalizes event classes when upstream inputs are incomplete."""

    def classify(self, event: InboundEvent) -> InboundEventClass:
        return event.event_class

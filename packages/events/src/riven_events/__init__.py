"""Domain event backbone (ticket S01.3).

State changes and their events are written in one database transaction (`add_event`); the
relay publishes committed events to a Redis Stream; `EventConsumer` delivers them at least
once and records each processed event so a replay causes no duplicate side effects.
"""

from riven_events.consumer import EventConsumer, Handler
from riven_events.models import EventsBase, OutboxEvent, ProcessedEvent
from riven_events.outbox import add_event
from riven_events.relay import STREAM, OutboxRelay

__all__ = [
    "STREAM",
    "EventConsumer",
    "EventsBase",
    "Handler",
    "OutboxEvent",
    "OutboxRelay",
    "ProcessedEvent",
    "add_event",
]

from sqlalchemy.ext.asyncio import AsyncSession

from riven_events.models import OutboxEvent
from riven_schemas import DomainEvent


def add_event(session: AsyncSession, event: DomainEvent, *, org_id: str) -> None:
    """Stage `event` in the caller's transaction; it is published only if that commits."""
    session.add(
        OutboxEvent(
            event_id=event.event_id,
            event_type=getattr(event, "type", type(event).__name__),
            org_id=org_id,
            payload=event.model_dump(mode="json"),
        )
    )

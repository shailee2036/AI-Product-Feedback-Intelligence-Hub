from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class StoredAuditEvent:
    id: int
    action: str
    created_at: datetime


async def load_audit_events(conn: AsyncConnection, *, limit: int) -> list[StoredAuditEvent]:
    """Return the newest events. Metadata stays in the database."""
    rows = (
        await conn.execute(
            text(
                "select id, action, created_at from public.audit_events "
                "order by created_at desc, id desc limit :limit"
            ),
            {"limit": limit},
        )
    ).all()
    return [_event(dict(row._mapping)) for row in rows]


def _event(mapping: dict[str, Any]) -> StoredAuditEvent:
    return StoredAuditEvent(
        id=int(mapping["id"]),
        action=str(mapping["action"]),
        created_at=mapping["created_at"],
    )

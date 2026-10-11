import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class Workspace:
    tenant_id: UUID
    name: str
    role: str


async def ensure_workspace(conn: AsyncConnection, default_name: str) -> Workspace:
    tenant_id = (
        await conn.execute(text("select app.ensure_workspace(:name)"), {"name": default_name})
    ).scalar_one()
    row = (
        await conn.execute(
            text(
                "select t.name, m.role from public.tenants t "
                "join public.memberships m on m.tenant_id = t.id where t.id = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        )
    ).one()
    return Workspace(tenant_id=tenant_id, name=row.name, role=row.role)


async def record_audit_event(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    await conn.execute(
        text(
            "insert into public.audit_events "
            "(tenant_id, actor_id, action, target_type, target_id, metadata) "
            "values (:tenant_id, :actor_id, :action, :target_type, :target_id, "
            "cast(:metadata as jsonb))"
        ),
        {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "metadata": json.dumps(metadata or {}, separators=(",", ":"), default=str),
        },
    )

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class StoredIssueDraft:
    cluster_id: UUID
    title: str
    body: str
    labels: tuple[str, ...]


async def load_issue_drafts(conn: AsyncConnection) -> list[StoredIssueDraft]:
    rows = (
        await conn.execute(text("select cluster_id, title, body, labels from public.issue_drafts"))
    ).all()
    return [_draft(dict(row._mapping)) for row in rows]


async def save_issue_draft(
    conn: AsyncConnection,
    *,
    cluster_id: UUID,
    tenant_id: UUID,
    product_id: UUID,
    title: str,
    body: str,
    labels: tuple[str, ...],
) -> None:
    await conn.execute(
        text(
            "insert into public.issue_drafts ("
            "cluster_id, tenant_id, product_id, title, body, labels, created_at"
            ") values ("
            ":cluster_id, :tenant_id, :product_id, :title, :body, "
            "cast(:labels as jsonb), :created_at"
            ") on conflict (cluster_id) do update set "
            "title = excluded.title, body = excluded.body, labels = excluded.labels, "
            "created_at = excluded.created_at"
        ),
        {
            "cluster_id": cluster_id,
            "tenant_id": tenant_id,
            "product_id": product_id,
            "title": title,
            "body": body,
            "labels": json.dumps(list(labels)),
            "created_at": datetime.now(UTC),
        },
    )


def _draft(mapping: Mapping[str, Any]) -> StoredIssueDraft:
    return StoredIssueDraft(
        cluster_id=mapping["cluster_id"],
        title=str(mapping["title"]),
        body=str(mapping["body"]),
        labels=_labels(mapping["labels"]),
    )


def _labels(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        loaded: object = json.loads(value)
    else:
        loaded = value
    if not isinstance(loaded, list):
        return ()
    return tuple(str(item) for item in loaded if isinstance(item, str) and item)

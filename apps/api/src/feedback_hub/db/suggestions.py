import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class StoredSuggestion:
    cluster_id: UUID
    feedback_item_id: UUID
    comment: str
    labels: tuple[str, ...]


async def load_issue_suggestions(conn: AsyncConnection) -> list[StoredSuggestion]:
    rows = (
        await conn.execute(
            text(
                "select cluster_id, feedback_item_id, comment, labels from public.issue_suggestions"
            )
        )
    ).all()
    return [_suggestion(dict(row._mapping)) for row in rows]


async def save_issue_suggestion(
    conn: AsyncConnection,
    *,
    cluster_id: UUID,
    tenant_id: UUID,
    product_id: UUID,
    feedback_item_id: UUID,
    comment: str,
    labels: tuple[str, ...],
) -> None:
    await conn.execute(
        text(
            "insert into public.issue_suggestions ("
            "cluster_id, tenant_id, product_id, feedback_item_id, comment, labels, created_at"
            ") values ("
            ":cluster_id, :tenant_id, :product_id, :feedback_item_id, :comment, "
            "cast(:labels as jsonb), :created_at"
            ") on conflict (cluster_id) do update set "
            "feedback_item_id = excluded.feedback_item_id, "
            "comment = excluded.comment, labels = excluded.labels, "
            "created_at = excluded.created_at"
        ),
        {
            "cluster_id": cluster_id,
            "tenant_id": tenant_id,
            "product_id": product_id,
            "feedback_item_id": feedback_item_id,
            "comment": comment,
            "labels": json.dumps(list(labels)),
            "created_at": datetime.now(UTC),
        },
    )


def _suggestion(mapping: Mapping[str, Any]) -> StoredSuggestion:
    return StoredSuggestion(
        cluster_id=mapping["cluster_id"],
        feedback_item_id=mapping["feedback_item_id"],
        comment=str(mapping["comment"]),
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

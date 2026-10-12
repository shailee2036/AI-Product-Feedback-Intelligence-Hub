from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from feedback_hub.feedback.duplicates import DuplicateLink


@dataclass(frozen=True, slots=True)
class DedupeItem:
    id: UUID
    source: str
    external_id: str
    title: str
    body: str
    language: str | None
    content_hash: str | None


@dataclass(frozen=True, slots=True)
class StoredEdge:
    left_item_id: UUID
    right_item_id: UUID
    kind: str
    score: float


@dataclass(frozen=True, slots=True)
class DedupeRun:
    exact_count: int
    semantic_count: int
    group_count: int
    threshold: float
    neighbor_count: int


async def load_feedback_items(conn: AsyncConnection) -> list[DedupeItem]:
    rows = (
        await conn.execute(
            text(
                "select id, source, external_id, title, body, language, content_hash "
                "from public.feedback_items"
            )
        )
    ).all()
    return [DedupeItem(**row._mapping) for row in rows]


async def load_embedding_pairs(
    conn: AsyncConnection, *, provider: str, model: str, model_version: str
) -> list[tuple[UUID, UUID, float]]:
    rows = (
        await conn.execute(
            text(
                "select a.feedback_item_id as left_id, b.feedback_item_id as right_id, "
                "1 - (a.embedding operator(extensions.<=>) b.embedding) as score "
                "from public.feedback_embeddings a "
                "join public.feedback_embeddings b on b.product_id = a.product_id "
                "and b.provider = a.provider and b.model = a.model "
                "and b.model_version = a.model_version "
                "and a.feedback_item_id < b.feedback_item_id "
                "where a.provider = :provider and a.model = :model "
                "and a.model_version = :model_version"
            ),
            {"provider": provider, "model": model, "model_version": model_version},
        )
    ).all()
    return [
        (row._mapping["left_id"], row._mapping["right_id"], float(row._mapping["score"]))
        for row in rows
    ]


async def replace_duplicate_edges(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    product_id: UUID,
    provider: str,
    model: str,
    model_version: str,
    links: list[DuplicateLink],
) -> None:
    await conn.execute(text("delete from public.duplicate_edges"))
    if not links:
        return
    await conn.execute(
        text(
            "insert into public.duplicate_edges (tenant_id, product_id, left_item_id, "
            "right_item_id, kind, score, provider, model, model_version) values ("
            ":tenant_id, :product_id, :left_item_id, :right_item_id, :kind, :score, "
            ":provider, :model, :model_version)"
        ),
        [
            {
                "tenant_id": tenant_id,
                "product_id": product_id,
                "left_item_id": left_id,
                "right_item_id": right_id,
                "kind": link.kind,
                "score": link.score,
                "provider": provider,
                "model": model,
                "model_version": model_version,
            }
            for link in links
            for left_id, right_id in (_ordered_ids(link.left_id, link.right_id),)
        ],
    )


async def insert_dedupe_run(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    product_id: UUID,
    exact_count: int,
    semantic_count: int,
    group_count: int,
    threshold: float,
    neighbor_count: int,
    provider: str,
    model: str,
    model_version: str,
) -> None:
    await conn.execute(
        text(
            "insert into public.dedupe_runs (tenant_id, product_id, exact_count, "
            "semantic_count, group_count, threshold, neighbor_count, provider, model, "
            "model_version) values (:tenant_id, :product_id, :exact_count, "
            ":semantic_count, :group_count, :threshold, :neighbor_count, :provider, "
            ":model, :model_version)"
        ),
        {
            "tenant_id": tenant_id,
            "product_id": product_id,
            "exact_count": exact_count,
            "semantic_count": semantic_count,
            "group_count": group_count,
            "threshold": threshold,
            "neighbor_count": neighbor_count,
            "provider": provider,
            "model": model,
            "model_version": model_version,
        },
    )


async def latest_dedupe_run(conn: AsyncConnection) -> DedupeRun | None:
    row = (
        await conn.execute(
            text(
                "select exact_count, semantic_count, group_count, threshold, neighbor_count "
                "from public.dedupe_runs order by created_at desc limit 1"
            )
        )
    ).first()
    return DedupeRun(**row._mapping) if row else None


async def load_duplicate_edges(conn: AsyncConnection) -> list[StoredEdge]:
    rows = (
        await conn.execute(
            text("select left_item_id, right_item_id, kind, score from public.duplicate_edges")
        )
    ).all()
    return [StoredEdge(**row._mapping) for row in rows]


def _ordered_ids(left: str, right: str) -> tuple[UUID, UUID]:
    left_id, right_id = UUID(left), UUID(right)
    if left_id < right_id:
        return left_id, right_id
    return right_id, left_id

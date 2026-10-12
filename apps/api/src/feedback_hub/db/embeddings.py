from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from feedback_hub.feedback.embeddings import vector_literal


class EmbeddingRunAlreadyActiveError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class EmbeddingRun:
    id: UUID
    status: str
    model: str
    dimensions: int
    embedded_count: int
    skipped_count: int
    unchanged_count: int
    redaction_count: int
    error_message: str | None


@dataclass(frozen=True, slots=True)
class EmbeddableItem:
    id: UUID
    source: str
    title: str
    body: str
    language: str | None
    content_hash: str | None
    embedded_hash: str | None


async def create_embedding_run(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    product_id: UUID,
    provider: str,
    model: str,
    model_version: str,
    dimensions: int,
) -> UUID:
    try:
        async with conn.begin_nested():
            run_id: UUID = (
                await conn.execute(
                    text(
                        "insert into public.embedding_runs (tenant_id, product_id, status, "
                        "provider, model, model_version, dimensions, created_by) values ("
                        ":tenant_id, :product_id, 'queued', :provider, :model, :model_version, "
                        ":dimensions, :actor_id) returning id"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "product_id": product_id,
                        "provider": provider,
                        "model": model,
                        "model_version": model_version,
                        "dimensions": dimensions,
                        "actor_id": actor_id,
                    },
                )
            ).scalar_one()
    except IntegrityError as exc:
        if _constraint(exc) == "embedding_runs_one_active":
            raise EmbeddingRunAlreadyActiveError from exc
        raise
    return run_id


async def latest_embedding_run(conn: AsyncConnection) -> EmbeddingRun | None:
    row = (
        await conn.execute(
            text(
                "select id, status, model, dimensions, embedded_count, skipped_count, "
                "unchanged_count, redaction_count, error_message from public.embedding_runs "
                "order by created_at desc limit 1"
            )
        )
    ).first()
    return EmbeddingRun(**row._mapping) if row else None


async def count_embeddings(conn: AsyncConnection) -> int:
    total = (
        await conn.execute(text("select count(*) from public.feedback_embeddings"))
    ).scalar_one()
    return int(total)


async def mark_embedding_running(conn: AsyncConnection, run_id: UUID) -> None:
    await conn.execute(
        text(
            "update public.embedding_runs set status = 'running', started_at = now() "
            "where id = :id and status = 'queued'"
        ),
        {"id": run_id},
    )


async def mark_embedding_finished(
    conn: AsyncConnection,
    run_id: UUID,
    *,
    status: str,
    embedded_count: int,
    skipped_count: int,
    unchanged_count: int,
    redaction_count: int,
    error_message: str | None,
) -> None:
    await conn.execute(
        text(
            "update public.embedding_runs set status = :status, embedded_count = :embedded_count, "
            "skipped_count = :skipped_count, unchanged_count = :unchanged_count, "
            "redaction_count = :redaction_count, error_message = :error_message, "
            "finished_at = now() where id = :id and status in ('queued', 'running')"
        ),
        {
            "id": run_id,
            "status": status,
            "embedded_count": embedded_count,
            "skipped_count": skipped_count,
            "unchanged_count": unchanged_count,
            "redaction_count": redaction_count,
            "error_message": error_message,
        },
    )


async def mark_embedding_failed(conn: AsyncConnection, run_id: UUID, error_message: str) -> None:
    await conn.execute(
        text(
            "update public.embedding_runs set status = 'failed', error_message = :error_message, "
            "finished_at = now() where id = :id and status in ('queued', 'running')"
        ),
        {"id": run_id, "error_message": error_message},
    )


async def load_embeddable_items(
    conn: AsyncConnection, *, provider: str, model: str, model_version: str
) -> list[EmbeddableItem]:
    rows = (
        await conn.execute(
            text(
                "select f.id, f.source, f.title, f.body, f.language, f.content_hash, "
                "e.content_hash as embedded_hash from public.feedback_items f "
                "left join public.feedback_embeddings e on e.feedback_item_id = f.id "
                "and e.provider = :provider and e.model = :model "
                "and e.model_version = :model_version"
            ),
            {"provider": provider, "model": model, "model_version": model_version},
        )
    ).all()
    return [EmbeddableItem(**row._mapping) for row in rows]


async def save_embedding(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    product_id: UUID,
    feedback_item_id: UUID,
    run_id: UUID,
    provider: str,
    model: str,
    model_version: str,
    dimensions: int,
    embedding: list[float],
    content_hash: str,
    language: str,
    redaction_count: int,
) -> None:
    await conn.execute(
        text(
            "insert into public.feedback_embeddings (tenant_id, product_id, feedback_item_id, "
            "embedding_run_id, provider, model, model_version, dimensions, embedding, "
            "content_hash) values (:tenant_id, :product_id, :feedback_item_id, :run_id, "
            ":provider, :model, :model_version, :dimensions, "
            "cast(:embedding as extensions.vector), :content_hash) "
            "on conflict (feedback_item_id, provider, model, model_version) do update set "
            "embedding_run_id = excluded.embedding_run_id, embedding = excluded.embedding, "
            "content_hash = excluded.content_hash, created_at = now()"
        ),
        {
            "tenant_id": tenant_id,
            "product_id": product_id,
            "feedback_item_id": feedback_item_id,
            "run_id": run_id,
            "provider": provider,
            "model": model,
            "model_version": model_version,
            "dimensions": dimensions,
            "embedding": vector_literal(embedding),
            "content_hash": content_hash,
        },
    )
    await remember_normalization(
        conn,
        feedback_item_id=feedback_item_id,
        content_hash=content_hash,
        language=language,
        redaction_count=redaction_count,
    )


async def remember_normalization(
    conn: AsyncConnection,
    *,
    feedback_item_id: UUID,
    content_hash: str,
    language: str,
    redaction_count: int,
) -> None:
    await conn.execute(
        text(
            "update public.feedback_items set content_hash = :content_hash, "
            "detected_language = :language, redaction_count = :redaction_count "
            "where id = :id"
        ),
        {
            "id": feedback_item_id,
            "content_hash": content_hash,
            "language": language,
            "redaction_count": redaction_count,
        },
    )


def _constraint(exc: IntegrityError) -> str | None:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = getattr(current, "constraint_name", None)
        if isinstance(name, str):
            return name
        current = current.__cause__
    return None

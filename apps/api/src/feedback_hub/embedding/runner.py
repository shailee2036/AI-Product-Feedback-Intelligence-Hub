from uuid import UUID

from feedback_hub.auth import AuthenticatedUser
from feedback_hub.db.embeddings import (
    load_embeddable_items,
    mark_embedding_failed,
    mark_embedding_finished,
    mark_embedding_running,
    remember_normalization,
    save_embedding,
)
from feedback_hub.db.engine import Database
from feedback_hub.db.workspaces import record_audit_event
from feedback_hub.feedback.embeddings import EmbeddingClient, EmbeddingError
from feedback_hub.feedback.normalize import PreparedText, prepare_text, source_text

Pending = tuple[UUID, PreparedText]


async def run_embeddings(
    database: Database,
    client: EmbeddingClient,
    user: AuthenticatedUser,
    run_id: UUID,
    *,
    tenant_id: UUID,
    product_id: UUID,
    provider: str,
    model: str,
    model_version: str,
    dimensions: int,
    batch_size: int,
) -> None:
    try:
        await _run(
            database,
            client,
            user,
            run_id,
            tenant_id=tenant_id,
            product_id=product_id,
            provider=provider,
            model=model,
            model_version=model_version,
            dimensions=dimensions,
            batch_size=batch_size,
        )
    except Exception as exc:
        message = (
            str(exc) if isinstance(exc, EmbeddingError) else "Embedding failed before it finished."
        )
        async with database.user_transaction(user) as conn:
            await mark_embedding_failed(conn, run_id, message)
            await record_audit_event(
                conn,
                tenant_id=tenant_id,
                actor_id=user.id,
                action="embedding.failed",
                target_type="embedding_run",
                target_id=str(run_id),
            )


async def _run(
    database: Database,
    client: EmbeddingClient,
    user: AuthenticatedUser,
    run_id: UUID,
    *,
    tenant_id: UUID,
    product_id: UUID,
    provider: str,
    model: str,
    model_version: str,
    dimensions: int,
    batch_size: int,
) -> None:
    async with database.user_transaction(user) as conn:
        await mark_embedding_running(conn, run_id)
        items = await load_embeddable_items(
            conn, provider=provider, model=model, model_version=model_version
        )

    pending: list[Pending] = []
    skipped = 0
    unchanged = 0
    redactions = 0
    for item in items:
        prepared = prepare_text(
            source_text(source=item.source, title=item.title, body=item.body),
            declared_language=item.language,
        )
        redactions += prepared.redaction_count
        if prepared.content_hash == item.embedded_hash:
            unchanged += 1
            continue
        if prepared.skip_reason:
            skipped += 1
            async with database.user_transaction(user) as conn:
                await remember_normalization(
                    conn,
                    feedback_item_id=item.id,
                    content_hash=prepared.content_hash,
                    language=prepared.language,
                    redaction_count=prepared.redaction_count,
                )
            continue
        pending.append((item.id, prepared))

    embedded = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        vectors = await client.embed([prepared.text for _, prepared in batch])
        async with database.user_transaction(user) as conn:
            for (item_id, prepared), vector in zip(batch, vectors, strict=True):
                await save_embedding(
                    conn,
                    tenant_id=tenant_id,
                    product_id=product_id,
                    feedback_item_id=item_id,
                    run_id=run_id,
                    provider=provider,
                    model=model,
                    model_version=model_version,
                    dimensions=dimensions,
                    embedding=vector,
                    content_hash=prepared.content_hash,
                    language=prepared.language,
                    redaction_count=prepared.redaction_count,
                )
        embedded += len(batch)

    async with database.user_transaction(user) as conn:
        await mark_embedding_finished(
            conn,
            run_id,
            status="succeeded",
            embedded_count=embedded,
            skipped_count=skipped,
            unchanged_count=unchanged,
            redaction_count=redactions,
            error_message=None,
        )
        await record_audit_event(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="embedding.completed",
            target_type="embedding_run",
            target_id=str(run_id),
            metadata={"embedded_count": embedded, "skipped_count": skipped},
        )

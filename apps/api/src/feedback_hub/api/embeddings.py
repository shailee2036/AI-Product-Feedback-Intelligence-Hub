import asyncio
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from feedback_hub.api.me import default_workspace_name
from feedback_hub.auth import AuthenticatedUser, CurrentUser
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.embeddings import (
    EmbeddingRun,
    EmbeddingRunAlreadyActiveError,
    count_embeddings,
    create_embedding_run,
    latest_embedding_run,
)
from feedback_hub.db.engine import Database, UserConnection, get_database
from feedback_hub.db.products import get_product
from feedback_hub.db.workspaces import ensure_workspace, record_audit_event
from feedback_hub.embedding.runner import run_embeddings
from feedback_hub.feedback.embeddings import EmbeddingClient

router = APIRouter(tags=["embeddings"])

PROVIDER = "gemini"
ALREADY_RUNNING = "An embedding run is already in progress."
NOT_CONFIGURED = "Add FEEDBACK_HUB_GEMINI_API_KEY before embedding feedback."


class EmbeddingStatusOut(BaseModel):
    id: UUID | None
    status: Literal["idle", "queued", "running", "succeeded", "failed", "cancelled"]
    model: str
    dimensions: int
    embedded_count: int
    skipped_count: int
    unchanged_count: int
    redaction_count: int
    stored_count: int
    error_message: str | None

    @classmethod
    def idle(cls, settings: Settings, stored_count: int) -> "EmbeddingStatusOut":
        return cls(
            id=None,
            status="idle",
            model=settings.gemini_embedding_model,
            dimensions=settings.gemini_embedding_dimensions,
            embedded_count=0,
            skipped_count=0,
            unchanged_count=0,
            redaction_count=0,
            stored_count=stored_count,
            error_message=None,
        )

    @classmethod
    def from_run(cls, run: EmbeddingRun, stored_count: int) -> "EmbeddingStatusOut":
        return cls(
            id=run.id,
            status=run.status,
            model=run.model,
            dimensions=run.dimensions,
            embedded_count=run.embedded_count,
            skipped_count=run.skipped_count,
            unchanged_count=run.unchanged_count,
            redaction_count=run.redaction_count,
            stored_count=stored_count,
            error_message=run.error_message,
        )


def _schedule(
    request: Request,
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
    client: EmbeddingClient = request.app.state.gemini
    database: Database = request.app.state.database
    task = asyncio.create_task(
        run_embeddings(
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
        ),
        name=f"embed-{run_id}",
    )
    tasks: set[asyncio.Task[None]] = request.app.state.import_tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)


@router.post(
    "/v1/feedback/embeddings",
    response_model=EmbeddingStatusOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_embeddings(
    request: Request,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmbeddingStatusOut:
    if settings.gemini_api_key is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_CONFIGURED)
    async with database.user_transaction(user) as conn:
        workspace = await ensure_workspace(conn, default_workspace_name(user.email))
        product = await get_product(conn)
        if product is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No product registered yet.")
        try:
            run_id = await create_embedding_run(
                conn,
                tenant_id=workspace.tenant_id,
                actor_id=user.id,
                product_id=product.id,
                provider=PROVIDER,
                model=settings.gemini_embedding_model,
                model_version=settings.gemini_embedding_version,
                dimensions=settings.gemini_embedding_dimensions,
            )
        except EmbeddingRunAlreadyActiveError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_RUNNING) from exc
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="embedding.started",
            target_type="embedding_run",
            target_id=str(run_id),
        )
        stored_count = await count_embeddings(conn)
    _schedule(
        request,
        user,
        run_id,
        tenant_id=workspace.tenant_id,
        product_id=product.id,
        provider=PROVIDER,
        model=settings.gemini_embedding_model,
        model_version=settings.gemini_embedding_version,
        dimensions=settings.gemini_embedding_dimensions,
        batch_size=settings.gemini_embedding_batch_size,
    )
    return EmbeddingStatusOut(
        id=run_id,
        status="queued",
        model=settings.gemini_embedding_model,
        dimensions=settings.gemini_embedding_dimensions,
        embedded_count=0,
        skipped_count=0,
        unchanged_count=0,
        redaction_count=0,
        stored_count=stored_count,
        error_message=None,
    )


@router.get("/v1/feedback/embeddings/current", response_model=EmbeddingStatusOut)
async def read_current_embeddings(
    conn: UserConnection, settings: Annotated[Settings, Depends(get_settings)]
) -> EmbeddingStatusOut:
    stored_count = await count_embeddings(conn)
    run = await latest_embedding_run(conn)
    if run is None:
        return EmbeddingStatusOut.idle(settings, stored_count)
    return EmbeddingStatusOut.from_run(run, stored_count)

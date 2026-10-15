import asyncio
import re
import time
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from feedback_hub.api.me import default_workspace_name
from feedback_hub.auth import AuthenticatedUser, CurrentUser
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.engine import Database, UserConnection, get_database
from feedback_hub.db.imports import (
    FeedbackItem,
    ImportAlreadyRunningError,
    ImportJob,
    cancel_import,
    create_import,
    get_import,
    latest_import,
    list_feedback,
)
from feedback_hub.db.products import get_product
from feedback_hub.db.workspaces import ensure_workspace, record_audit_event
from feedback_hub.github.client import GitHubClient
from feedback_hub.importing.runner import run_import

router = APIRouter(tags=["imports"])

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,80}$")
ALREADY_RUNNING = "An import is already running for this product."


class ImportOut(BaseModel):
    id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    issue_limit: int
    imported_count: int
    skipped_count: int
    not_modified: bool
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_job(cls, job: ImportJob) -> "ImportOut":
        return cls(
            id=job.id,
            status=job.status,
            issue_limit=job.issue_limit,
            imported_count=job.imported_count,
            skipped_count=job.skipped_count,
            not_modified=job.not_modified,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class FeedbackOut(BaseModel):
    id: UUID
    source: Literal["github_issue", "csv"]
    number: int | None
    title: str
    state: str | None
    html_url: str | None
    labels: list[str]
    comment_count: int
    reactions_total: int
    excerpt: str
    product_area: str | None
    is_synthetic: bool
    updated_at: datetime

    @classmethod
    def from_item(cls, item: FeedbackItem) -> "FeedbackOut":
        return cls(
            id=item.id,
            source=item.source,
            number=item.github_number,
            title=item.title,
            state=item.state,
            html_url=item.html_url,
            labels=list(item.labels),
            comment_count=item.comment_count,
            reactions_total=item.reactions_total,
            excerpt=item.excerpt,
            product_area=item.product_area,
            is_synthetic=item.is_synthetic,
            updated_at=item.source_updated_at,
        )


class FeedbackPage(BaseModel):
    total: int
    items: list[FeedbackOut]


def _schedule(request: Request, user: AuthenticatedUser, import_id: UUID) -> None:
    database: Database = request.app.state.database
    github: GitHubClient = request.app.state.github
    task = asyncio.create_task(
        run_import(database, github, user, import_id, queued_at=time.perf_counter()),
        name=f"import-{import_id}",
    )
    tasks: set[asyncio.Task[None]] = request.app.state.import_tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def _idempotency_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    if _IDEMPOTENCY_KEY.fullmatch(raw) is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Idempotency-Key must be 8-80 letters, digits, or the characters . _ : -",
        )
    return raw


@router.post("/v1/imports")
async def start_import(
    request: Request,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    key = _idempotency_key(idempotency_key)
    async with database.user_transaction(user) as conn:
        workspace = await ensure_workspace(conn, default_workspace_name(user.email))
        product = await get_product(conn)
        if product is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No product registered yet.")
        try:
            job, created = await create_import(
                conn,
                tenant_id=workspace.tenant_id,
                actor_id=user.id,
                product_id=product.id,
                repository_id=product.repository_id,
                issue_limit=settings.github_import_limit,
                idempotency_key=key,
            )
        except ImportAlreadyRunningError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_RUNNING) from exc
        if created:
            await record_audit_event(
                conn,
                tenant_id=workspace.tenant_id,
                actor_id=user.id,
                action="import.started",
                target_type="import",
                target_id=str(job.id),
            )
    if created:
        _schedule(request, user, job.id)
    body = ImportOut.from_job(job).model_dump(mode="json")
    return JSONResponse(
        body, status_code=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
    )


@router.get("/v1/imports/current", response_model=ImportOut)
async def read_current_import(conn: UserConnection) -> ImportOut:
    job = await latest_import(conn)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No import has been started.")
    return ImportOut.from_job(job)


@router.get("/v1/imports/{import_id}", response_model=ImportOut)
async def read_import(import_id: UUID, conn: UserConnection) -> ImportOut:
    job = await get_import(conn, import_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found.")
    return ImportOut.from_job(job)


@router.post("/v1/imports/{import_id}/cancel", response_model=ImportOut)
async def cancel(
    import_id: UUID, user: CurrentUser, database: Annotated[Database, Depends(get_database)]
) -> ImportOut:
    async with database.user_transaction(user) as conn:
        workspace = await ensure_workspace(conn, default_workspace_name(user.email))
        cancelled = await cancel_import(conn, import_id)
        if not cancelled:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "This import is not running, so it cannot be cancelled."
            )
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="import.cancelled",
            target_type="import",
            target_id=str(import_id),
        )
        job = await get_import(conn, import_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found.")
    return ImportOut.from_job(job)


@router.get("/v1/feedback", response_model=FeedbackPage)
async def read_feedback(
    conn: UserConnection,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    source: Annotated[Literal["github_issue", "csv"] | None, Query()] = None,
) -> FeedbackPage:
    items, total = await list_feedback(conn, limit=limit, source=source)
    return FeedbackPage(total=total, items=[FeedbackOut.from_item(item) for item in items])

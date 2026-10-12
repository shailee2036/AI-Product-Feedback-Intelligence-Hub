from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from feedback_hub.github.issues import ImportedIssue


class ImportAlreadyRunningError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ImportJob:
    id: UUID
    status: str
    issue_limit: int
    imported_count: int
    skipped_count: int
    not_modified: bool
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class ImportTarget:
    id: UUID
    status: str
    issue_limit: int
    tenant_id: UUID
    product_id: UUID
    owner: str
    name: str


@dataclass(frozen=True, slots=True)
class FeedbackItem:
    id: UUID
    source: str
    github_number: int | None
    title: str
    state: str | None
    html_url: str | None
    labels: list[str]
    comment_count: int
    reactions_total: int
    excerpt: str
    product_area: str | None
    is_synthetic: bool
    source_updated_at: datetime


_SELECT_JOB = (
    "select id, status, issue_limit, imported_count, skipped_count, not_modified, "
    "error_message, created_at, started_at, finished_at from public.imports"
)


def _job(row: Row[Any]) -> ImportJob:
    return ImportJob(**row._mapping)


async def create_import(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    product_id: UUID,
    repository_id: UUID,
    issue_limit: int,
    idempotency_key: str | None,
) -> tuple[ImportJob, bool]:
    if idempotency_key is not None:
        existing = await _by_idempotency_key(conn, idempotency_key)
        if existing is not None:
            return existing, False
    try:
        async with conn.begin_nested():
            row = (
                await conn.execute(
                    text(
                        "insert into public.imports (tenant_id, product_id, repository_id, source, "
                        "status, issue_limit, created_by, idempotency_key) values (:tenant_id, "
                        ":product_id, :repository_id, 'github_issues', 'queued', :issue_limit, "
                        ":actor_id, :idempotency_key) returning id, status, issue_limit, "
                        "imported_count, skipped_count, not_modified, error_message, "
                        "created_at, started_at, finished_at"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "product_id": product_id,
                        "repository_id": repository_id,
                        "issue_limit": issue_limit,
                        "actor_id": actor_id,
                        "idempotency_key": idempotency_key,
                    },
                )
            ).one()
    except IntegrityError as exc:
        if _constraint(exc) == "imports_one_active_per_product":
            raise ImportAlreadyRunningError from exc
        if _constraint(exc) == "imports_idempotency_key" and idempotency_key is not None:
            existing = await _by_idempotency_key(conn, idempotency_key)
            if existing is not None:
                return existing, False
        raise
    return _job(row), True


async def get_import(conn: AsyncConnection, import_id: UUID) -> ImportJob | None:
    row = (
        await conn.execute(
            text(_SELECT_JOB + " where id = :id"),
            {"id": import_id},
        )
    ).first()
    return _job(row) if row else None


async def latest_import(conn: AsyncConnection) -> ImportJob | None:
    row = (await conn.execute(text(_SELECT_JOB + " order by created_at desc limit 1"))).first()
    return _job(row) if row else None


async def load_target(conn: AsyncConnection, import_id: UUID) -> ImportTarget | None:
    row = (
        await conn.execute(
            text(
                "select i.id, i.status, i.issue_limit, i.tenant_id, i.product_id, r.owner, r.name "
                "from public.imports i "
                "join public.github_repositories r on r.id = i.repository_id "
                "where i.id = :id"
            ),
            {"id": import_id},
        )
    ).first()
    return ImportTarget(**row._mapping) if row else None


async def mark_running(conn: AsyncConnection, import_id: UUID) -> None:
    await conn.execute(
        text(
            "update public.imports set status = 'running', started_at = now() "
            "where id = :id and status = 'queued'"
        ),
        {"id": import_id},
    )


async def mark_finished(
    conn: AsyncConnection,
    import_id: UUID,
    *,
    status: str,
    imported_count: int,
    skipped_count: int,
    not_modified: bool,
    error_message: str | None,
) -> None:
    await conn.execute(
        text(
            "update public.imports set status = :status, imported_count = :imported_count, "
            "skipped_count = :skipped_count, not_modified = :not_modified, "
            "error_message = :error_message, finished_at = now() "
            "where id = :id and status in ('queued', 'running')"
        ),
        {
            "id": import_id,
            "status": status,
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "not_modified": not_modified,
            "error_message": error_message,
        },
    )


async def mark_failed(conn: AsyncConnection, import_id: UUID, error_message: str) -> None:
    await conn.execute(
        text(
            "update public.imports set status = 'failed', error_message = :error_message, "
            "finished_at = now() where id = :id and status in ('queued', 'running')"
        ),
        {"id": import_id, "error_message": error_message},
    )


async def cancel_import(conn: AsyncConnection, import_id: UUID) -> bool:
    result = await conn.execute(
        text(
            "update public.imports set status = 'cancelled', finished_at = now() "
            "where id = :id and status in ('queued', 'running')"
        ),
        {"id": import_id},
    )
    return result.rowcount > 0


async def is_cancelled(conn: AsyncConnection, import_id: UUID) -> bool:
    status = (
        await conn.execute(
            text("select status from public.imports where id = :id"),
            {"id": import_id},
        )
    ).scalar_one_or_none()
    return status == "cancelled"


async def save_checkpoint(
    conn: AsyncConnection,
    *,
    import_id: UUID,
    tenant_id: UUID,
    page: int,
    etag: str | None,
    last_issue_updated_at: datetime | None,
    imported_count: int,
    skipped_count: int,
) -> None:
    await conn.execute(
        text(
            "insert into public.import_checkpoints "
            "(import_id, tenant_id, page, etag, last_issue_updated_at) "
            "values (:import_id, :tenant_id, :page, :etag, :last_updated) "
            "on conflict (import_id) do update set page = excluded.page, "
            "etag = coalesce(excluded.etag, public.import_checkpoints.etag), "
            "last_issue_updated_at = coalesce(excluded.last_issue_updated_at, "
            "public.import_checkpoints.last_issue_updated_at), updated_at = now()"
        ),
        {
            "import_id": import_id,
            "tenant_id": tenant_id,
            "page": page,
            "etag": etag,
            "last_updated": last_issue_updated_at,
        },
    )
    await conn.execute(
        text(
            "update public.imports set imported_count = :imported_count, "
            "skipped_count = :skipped_count where id = :id and status = 'running'"
        ),
        {"id": import_id, "imported_count": imported_count, "skipped_count": skipped_count},
    )


async def previous_page_etag(conn: AsyncConnection, product_id: UUID) -> str | None:
    return (
        await conn.execute(
            text(
                "select c.etag from public.import_checkpoints c "
                "join public.imports i on i.id = c.import_id "
                "where i.product_id = :product_id and i.status = 'succeeded' "
                "and c.etag is not null "
                "order by i.created_at desc limit 1"
            ),
            {"product_id": product_id},
        )
    ).scalar_one_or_none()


async def upsert_issue(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    product_id: UUID,
    import_id: UUID,
    issue: ImportedIssue,
) -> None:
    await conn.execute(
        text(
            "insert into public.feedback_items (tenant_id, product_id, import_id, source, "
            "external_id, github_number, title, body, body_normalized, state, html_url, labels, "
            "comment_count, reactions_total, author_hash, source_created_at, source_updated_at) "
            "values (:tenant_id, :product_id, :import_id, 'github_issue', :external_id, :number, "
            ":title, :body, :body_normalized, :state, :html_url, :labels, :comment_count, "
            ":reactions_total, :author_hash, :source_created_at, :source_updated_at) "
            "on conflict (product_id, source, external_id) do update set "
            "import_id = excluded.import_id, title = excluded.title, body = excluded.body, "
            "body_normalized = excluded.body_normalized, state = excluded.state, "
            "html_url = excluded.html_url, labels = excluded.labels, "
            "comment_count = excluded.comment_count, reactions_total = excluded.reactions_total, "
            "author_hash = excluded.author_hash, source_created_at = excluded.source_created_at, "
            "source_updated_at = excluded.source_updated_at, updated_at = now()"
        ),
        {
            "tenant_id": tenant_id,
            "product_id": product_id,
            "import_id": import_id,
            "external_id": issue.external_id,
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
            "body_normalized": issue.body_normalized,
            "state": issue.state,
            "html_url": issue.html_url,
            "labels": issue.labels,
            "comment_count": issue.comment_count,
            "reactions_total": issue.reactions_total,
            "author_hash": issue.author_hash,
            "source_created_at": issue.source_created_at,
            "source_updated_at": issue.source_updated_at,
        },
    )


async def list_feedback(
    conn: AsyncConnection, *, limit: int, source: str | None = None
) -> tuple[list[FeedbackItem], int]:
    total = (
        await conn.execute(
            text(
                "select count(*) from public.feedback_items "
                "where (cast(:source as text) is null or source = :source)"
            ),
            {"source": source},
        )
    ).scalar_one()
    rows = (
        await conn.execute(
            text(
                "select id, source, github_number, title, state, html_url, labels, comment_count, "
                "reactions_total, left(body_normalized, 180) as excerpt, product_area, "
                "is_synthetic, source_updated_at from public.feedback_items "
                "where (cast(:source as text) is null or source = :source) "
                "order by source_updated_at desc limit :limit"
            ),
            {"limit": limit, "source": source},
        )
    ).all()
    return [FeedbackItem(**row._mapping) for row in rows], int(total)


async def _by_idempotency_key(conn: AsyncConnection, key: str) -> ImportJob | None:
    row = (
        await conn.execute(
            text(_SELECT_JOB + " where idempotency_key = :key"),
            {"key": key},
        )
    ).first()
    return _job(row) if row else None


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

from uuid import UUID

from feedback_hub.auth import AuthenticatedUser
from feedback_hub.db.engine import Database
from feedback_hub.db.imports import (
    is_cancelled,
    load_target,
    mark_failed,
    mark_finished,
    mark_running,
    previous_page_etag,
    save_checkpoint,
    upsert_issue,
)
from feedback_hub.db.workspaces import record_audit_event
from feedback_hub.github.client import GitHubClient, GitHubError, GitHubRateLimitedError
from feedback_hub.github.issues import prepare_issue

_PAGE_SIZE = 100
_MAX_PAGES = 10


async def run_import(
    database: Database,
    github: GitHubClient,
    user: AuthenticatedUser,
    import_id: UUID,
) -> None:
    try:
        await _run(database, github, user, import_id)
    except Exception as exc:
        message = _failure_message(exc)
        async with database.user_transaction(user) as conn:
            await mark_failed(conn, import_id, message)
            target = await load_target(conn, import_id)
            if target is not None:
                await record_audit_event(
                    conn,
                    tenant_id=target.tenant_id,
                    actor_id=user.id,
                    action="import.failed",
                    target_type="import",
                    target_id=str(import_id),
                )


async def _run(
    database: Database, github: GitHubClient, user: AuthenticatedUser, import_id: UUID
) -> None:
    async with database.user_transaction(user) as conn:
        target = await load_target(conn, import_id)
        if target is None or target.status != "queued":
            return
        await mark_running(conn, import_id)
        etag = await previous_page_etag(conn, target.product_id)

    imported = 0
    skipped = 0
    not_modified = False
    last_updated = None
    page_etag: str | None = None

    for page in range(1, _MAX_PAGES + 1):
        async with database.user_transaction(user) as conn:
            if await is_cancelled(conn, import_id):
                await record_audit_event(
                    conn,
                    tenant_id=target.tenant_id,
                    actor_id=user.id,
                    action="import.cancelled",
                    target_type="import",
                    target_id=str(import_id),
                )
                return

        result = await github.list_issues_page(
            target.owner,
            target.name,
            page=page,
            per_page=_PAGE_SIZE,
            etag=etag if page == 1 else None,
        )
        if result.not_modified:
            not_modified = True
            async with database.user_transaction(user) as conn:
                await save_checkpoint(
                    conn,
                    import_id=import_id,
                    tenant_id=target.tenant_id,
                    page=1,
                    etag=result.etag,
                    last_issue_updated_at=None,
                    imported_count=imported,
                    skipped_count=skipped,
                )
            break

        batch = []
        page_updated = None
        for raw in result.issues:
            prepared = prepare_issue(raw)
            if prepared.issue is None:
                skipped += 1
                continue
            if imported >= target.issue_limit:
                break
            batch.append(prepared.issue)
            imported += 1
            page_updated = prepared.issue.source_updated_at
        if page_updated is not None:
            last_updated = page_updated
        page_etag = result.etag

        async with database.user_transaction(user) as conn:
            for issue in batch:
                await upsert_issue(
                    conn,
                    tenant_id=target.tenant_id,
                    product_id=target.product_id,
                    import_id=import_id,
                    issue=issue,
                )
            await save_checkpoint(
                conn,
                import_id=import_id,
                tenant_id=target.tenant_id,
                page=page,
                etag=page_etag if page == 1 else None,
                last_issue_updated_at=last_updated,
                imported_count=imported,
                skipped_count=skipped,
            )
        if imported >= target.issue_limit or not result.has_next or not result.issues:
            break

    async with database.user_transaction(user) as conn:
        if await is_cancelled(conn, import_id):
            return
        await mark_finished(
            conn,
            import_id,
            status="succeeded",
            imported_count=imported,
            skipped_count=skipped,
            not_modified=not_modified,
            error_message=None,
        )
        await record_audit_event(
            conn,
            tenant_id=target.tenant_id,
            actor_id=user.id,
            action="import.completed",
            target_type="import",
            target_id=str(import_id),
            metadata={"imported_count": imported, "skipped_count": skipped},
        )


def _failure_message(exc: Exception) -> str:
    if isinstance(exc, GitHubRateLimitedError):
        return "GitHub rate limit reached. Try the import again after it resets."
    if isinstance(exc, GitHubError):
        return str(exc)
    return "The import failed before it could finish."

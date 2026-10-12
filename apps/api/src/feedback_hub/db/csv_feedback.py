from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from feedback_hub.feedback.csv_import import csv_title, normalized_feedback
from feedback_hub.feedback.csv_schema import FeedbackRow


async def create_csv_import(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    product_id: UUID,
    repository_id: UUID,
    row_count: int,
) -> UUID:
    import_id: UUID = (
        await conn.execute(
            text(
                "insert into public.imports (tenant_id, product_id, repository_id, source, "
                "status, issue_limit, imported_count, created_by, started_at, finished_at) "
                "values (:tenant_id, :product_id, :repository_id, 'csv', 'succeeded', "
                ":row_count, :row_count, :actor_id, now(), now()) returning id"
            ),
            {
                "tenant_id": tenant_id,
                "product_id": product_id,
                "repository_id": repository_id,
                "row_count": row_count,
                "actor_id": actor_id,
            },
        )
    ).scalar_one()
    return import_id


async def upsert_csv_rows(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    product_id: UUID,
    import_id: UUID,
    rows: list[FeedbackRow],
) -> None:
    for row in rows:
        await conn.execute(
            text(
                "insert into public.feedback_items (tenant_id, product_id, import_id, source, "
                "external_id, title, body, body_normalized, channel, customer_segment, "
                "product_area, rating, severity, language, is_synthetic, source_created_at, "
                "source_updated_at) values (:tenant_id, :product_id, :import_id, 'csv', "
                ":external_id, :title, :body, :body_normalized, :channel, :customer_segment, "
                ":product_area, :rating, :severity, :language, :is_synthetic, :created_at, "
                ":created_at) on conflict (product_id, source, external_id) do update set "
                "import_id = excluded.import_id, title = excluded.title, body = excluded.body, "
                "body_normalized = excluded.body_normalized, channel = excluded.channel, "
                "customer_segment = excluded.customer_segment, "
                "product_area = excluded.product_area, rating = excluded.rating, "
                "severity = excluded.severity, language = excluded.language, "
                "is_synthetic = excluded.is_synthetic, "
                "source_created_at = excluded.source_created_at, "
                "source_updated_at = excluded.source_updated_at, updated_at = now()"
            ),
            {
                "tenant_id": tenant_id,
                "product_id": product_id,
                "import_id": import_id,
                "external_id": row.feedback_id,
                "title": csv_title(row),
                "body": row.feedback,
                "body_normalized": normalized_feedback(row.feedback),
                "channel": row.source,
                "customer_segment": row.customer_segment,
                "product_area": row.product_area,
                "rating": row.rating,
                "severity": row.severity.value if row.severity is not None else None,
                "language": row.language,
                "is_synthetic": row.is_synthetic,
                "created_at": row.created_at,
            },
        )

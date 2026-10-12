from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class AnalysisRun:
    cluster_count: int
    member_count: int
    threshold: float
    neighbor_count: int
    minimum_size: int


async def replace_candidate_clusters(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    product_id: UUID,
    groups: list[list[str]],
    threshold: float,
    neighbor_count: int,
    minimum_size: int,
    provider: str,
    model: str,
    model_version: str,
) -> list[tuple[UUID, list[UUID]]]:
    await conn.execute(text("delete from public.candidate_cluster_members"))
    await conn.execute(text("delete from public.candidate_clusters"))
    await conn.execute(text("delete from public.analysis_runs"))
    member_count = sum(len(group) for group in groups)
    run_id = (
        await conn.execute(
            text(
                "insert into public.analysis_runs (tenant_id, product_id, cluster_count, "
                "member_count, threshold, neighbor_count, minimum_size, provider, model, "
                "model_version) values (:tenant_id, :product_id, :cluster_count, "
                ":member_count, :threshold, :neighbor_count, :minimum_size, :provider, "
                ":model, :model_version) returning id"
            ),
            {
                "tenant_id": tenant_id,
                "product_id": product_id,
                "cluster_count": len(groups),
                "member_count": member_count,
                "threshold": threshold,
                "neighbor_count": neighbor_count,
                "minimum_size": minimum_size,
                "provider": provider,
                "model": model,
                "model_version": model_version,
            },
        )
    ).scalar_one()
    stored: list[tuple[UUID, list[UUID]]] = []
    for group in groups:
        cluster_id = (
            await conn.execute(
                text(
                    "insert into public.candidate_clusters (tenant_id, product_id, "
                    "analysis_run_id) values (:tenant_id, :product_id, :run_id) returning id"
                ),
                {"tenant_id": tenant_id, "product_id": product_id, "run_id": run_id},
            )
        ).scalar_one()
        member_ids = [UUID(item_id) for item_id in group]
        if member_ids:
            await conn.execute(
                text(
                    "insert into public.candidate_cluster_members (cluster_id, "
                    "feedback_item_id, tenant_id, product_id) values (:cluster_id, "
                    ":feedback_item_id, :tenant_id, :product_id)"
                ),
                [
                    {
                        "cluster_id": cluster_id,
                        "feedback_item_id": member_id,
                        "tenant_id": tenant_id,
                        "product_id": product_id,
                    }
                    for member_id in member_ids
                ],
            )
        stored.append((cluster_id, member_ids))
    return stored


async def latest_analysis_run(conn: AsyncConnection) -> AnalysisRun | None:
    row = (
        await conn.execute(
            text(
                "select cluster_count, member_count, threshold, neighbor_count, minimum_size "
                "from public.analysis_runs order by created_at desc limit 1"
            )
        )
    ).first()
    return AnalysisRun(**row._mapping) if row else None


async def load_cluster_members(conn: AsyncConnection) -> list[tuple[UUID, UUID]]:
    rows = (
        await conn.execute(
            text(
                "select c.id as cluster_id, m.feedback_item_id from public.candidate_clusters c "
                "join public.candidate_cluster_members m on m.cluster_id = c.id "
                "order by c.created_at, m.feedback_item_id"
            )
        )
    ).all()
    return [(row._mapping["cluster_id"], row._mapping["feedback_item_id"]) for row in rows]

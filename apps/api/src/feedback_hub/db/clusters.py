from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

ClusterStatus = Literal["open", "approved", "dismissed"]


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
    await conn.execute(
        text(
            "delete from public.candidate_cluster_members where cluster_id in "
            "(select id from public.candidate_clusters where status <> 'approved')"
        )
    )
    await conn.execute(text("delete from public.candidate_clusters where status <> 'approved'"))
    await conn.execute(
        text(
            "delete from public.analysis_runs where not exists ("
            "select 1 from public.candidate_clusters c "
            "where c.analysis_run_id = public.analysis_runs.id)"
        )
    )
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


@dataclass(frozen=True, slots=True)
class StoredCluster:
    id: UUID
    name: str | None
    summary: str | None
    name_edited: bool
    status: ClusterStatus
    member_ids: tuple[UUID, ...]


async def load_stored_clusters(conn: AsyncConnection) -> list[StoredCluster]:
    rows = (
        await conn.execute(
            text(
                "select c.id as cluster_id, c.name, c.summary, c.name_edited, c.status, "
                "m.feedback_item_id from public.candidate_clusters c "
                "join public.candidate_cluster_members m on m.cluster_id = c.id "
                "order by c.created_at, m.feedback_item_id"
            )
        )
    ).all()
    order: list[UUID] = []
    members: dict[UUID, list[UUID]] = {}
    labels: dict[UUID, tuple[str | None, str | None, bool, ClusterStatus]] = {}
    for row in rows:
        mapping = row._mapping
        cluster_id = mapping["cluster_id"]
        if cluster_id not in members:
            order.append(cluster_id)
            members[cluster_id] = []
            labels[cluster_id] = (
                _optional_text(mapping.get("name")),
                _optional_text(mapping.get("summary")),
                bool(mapping.get("name_edited")),
                _status(mapping.get("status")),
            )
        members[cluster_id].append(mapping["feedback_item_id"])
    return [
        StoredCluster(
            id=cluster_id,
            name=labels[cluster_id][0],
            summary=labels[cluster_id][1],
            name_edited=labels[cluster_id][2],
            status=labels[cluster_id][3],
            member_ids=tuple(members[cluster_id]),
        )
        for cluster_id in order
    ]


async def save_theme_names(
    conn: AsyncConnection,
    names: list[tuple[UUID, str, str]],
    *,
    provider: str,
    model: str,
) -> None:
    """Fill blank names. A name that is already set, or marked edited, stays put."""
    if not names:
        return
    await conn.execute(
        text(
            "update public.candidate_clusters set name = :name, summary = :summary, "
            "name_provider = :provider, name_model = :model "
            "where id = :id and name is null and name_edited = false"
        ),
        [
            {
                "id": cluster_id,
                "name": name,
                "summary": summary,
                "provider": provider,
                "model": model,
            }
            for cluster_id, name, summary in names
        ],
    )


def partition_members(
    members: tuple[UUID, ...], requested: list[UUID]
) -> tuple[tuple[UUID, ...], tuple[UUID, ...]] | None:
    """Split a theme into the rows that stay and the rows that move out."""
    seen: set[UUID] = set()
    unique: list[UUID] = []
    for member_id in requested:
        if member_id in seen:
            continue
        seen.add(member_id)
        unique.append(member_id)
    if not unique or any(member_id not in members for member_id in unique):
        return None
    if len(unique) >= len(members):
        return None
    staying = tuple(member_id for member_id in members if member_id not in seen)
    moving = tuple(member_id for member_id in members if member_id in seen)
    if not staying or not moving:
        return None
    return staying, moving


async def relabel_cluster(
    conn: AsyncConnection, cluster_id: UUID, *, name: str, summary: str | None
) -> bool:
    row = (
        await conn.execute(
            text(
                "update public.candidate_clusters set name = :name, summary = :summary, "
                "name_edited = true, name_provider = null, name_model = null "
                "where id = :id returning id"
            ),
            {"id": cluster_id, "name": name, "summary": summary},
        )
    ).first()
    return row is not None


async def set_cluster_status(
    conn: AsyncConnection, cluster_id: UUID, status: ClusterStatus
) -> bool:
    row = (
        await conn.execute(
            text(
                "update public.candidate_clusters set status = :status where id = :id returning id"
            ),
            {"id": cluster_id, "status": status},
        )
    ).first()
    return row is not None


async def merge_cluster_members(
    conn: AsyncConnection, source: StoredCluster, target: StoredCluster
) -> None:
    await conn.execute(
        text(
            "insert into public.candidate_cluster_members "
            "(cluster_id, feedback_item_id, tenant_id, product_id) "
            "select :target_id, feedback_item_id, tenant_id, product_id "
            "from public.candidate_cluster_members where cluster_id = :source_id "
            "on conflict (cluster_id, feedback_item_id) do nothing"
        ),
        {"target_id": target.id, "source_id": source.id},
    )
    if source.status == "approved" or target.status == "approved":
        await set_cluster_status(conn, target.id, "approved")
    await conn.execute(
        text("delete from public.candidate_cluster_members where cluster_id = :id"),
        {"id": source.id},
    )
    await conn.execute(
        text("delete from public.candidate_clusters where id = :id"),
        {"id": source.id},
    )


async def split_cluster_members(
    conn: AsyncConnection, source: StoredCluster, moving: tuple[UUID, ...]
) -> UUID:
    created = (
        await conn.execute(
            text(
                "insert into public.candidate_clusters "
                "(tenant_id, product_id, analysis_run_id) "
                "select tenant_id, product_id, analysis_run_id "
                "from public.candidate_clusters where id = :source_id returning id"
            ),
            {"source_id": source.id},
        )
    ).scalar_one()
    if not isinstance(created, UUID):
        raise RuntimeError("Theme split did not return an id.")
    for member_id in moving:
        await conn.execute(
            text(
                "insert into public.candidate_cluster_members "
                "(cluster_id, feedback_item_id, tenant_id, product_id) "
                "select :cluster_id, feedback_item_id, tenant_id, product_id "
                "from public.candidate_cluster_members "
                "where cluster_id = :source_id and feedback_item_id = :member_id"
            ),
            {"cluster_id": created, "source_id": source.id, "member_id": member_id},
        )
        await conn.execute(
            text(
                "delete from public.candidate_cluster_members "
                "where cluster_id = :source_id and feedback_item_id = :member_id"
            ),
            {"source_id": source.id, "member_id": member_id},
        )
    return created


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _status(value: object) -> ClusterStatus:
    if value == "approved" or value == "dismissed" or value == "open":
        return value
    return "open"

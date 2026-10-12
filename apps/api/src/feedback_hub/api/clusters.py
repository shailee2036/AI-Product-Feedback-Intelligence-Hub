from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from feedback_hub.api.me import default_workspace_name
from feedback_hub.auth import CurrentUser
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.clusters import (
    latest_analysis_run,
    load_cluster_members,
    replace_candidate_clusters,
)
from feedback_hub.db.duplicates import DedupeItem, load_embedding_pairs, load_feedback_items
from feedback_hub.db.engine import Database, get_database
from feedback_hub.db.products import get_product
from feedback_hub.db.workspaces import ensure_workspace, record_audit_event
from feedback_hub.feedback.clusters import LABELED_THEMES, score_themes, theme_groups

router = APIRouter(tags=["clusters"])

PROVIDER = "gemini"
CLUSTER_LIMIT = 20
NO_PRODUCT = "No product registered yet."
NO_FEEDBACK = "Import feedback before grouping it into themes."
NO_EMBEDDINGS = "Embed feedback before grouping it into themes."


class ClusterMember(BaseModel):
    id: UUID
    source: Literal["github_issue", "csv"]
    external_id: str
    title: str


class ClusterGroup(BaseModel):
    id: UUID
    members: list[ClusterMember]


class ClusterEvaluation(BaseModel):
    labeled: int
    gathered: int
    mean_cohesion: float


class ClusterReport(BaseModel):
    ran: bool
    cluster_count: int
    member_count: int
    threshold: float
    neighbor_count: int
    minimum_size: int
    clusters: list[ClusterGroup]
    evaluation: ClusterEvaluation | None

    @classmethod
    def idle(cls, settings: Settings) -> "ClusterReport":
        return cls(
            ran=False,
            cluster_count=0,
            member_count=0,
            threshold=settings.cluster_similarity_threshold,
            neighbor_count=settings.cluster_neighbor_count,
            minimum_size=settings.cluster_minimum_size,
            clusters=[],
            evaluation=None,
        )


@router.post("/v1/feedback/clusters", response_model=ClusterReport)
async def find_clusters(
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Group embedded feedback into candidate themes. Original rows stay put."""
    async with database.user_transaction(user) as conn:
        workspace = await ensure_workspace(conn, default_workspace_name(user.email))
        product = await get_product(conn)
        if product is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_PRODUCT)
        items = await load_feedback_items(conn)
        if not items:
            raise HTTPException(status.HTTP_409_CONFLICT, NO_FEEDBACK)
        pairs = await load_embedding_pairs(
            conn,
            provider=PROVIDER,
            model=settings.gemini_embedding_model,
            model_version=settings.gemini_embedding_version,
        )
        if not pairs:
            raise HTTPException(status.HTTP_409_CONFLICT, NO_EMBEDDINGS)
        groups = theme_groups(
            [(str(left), str(right), score) for left, right, score in pairs],
            threshold=settings.cluster_similarity_threshold,
            neighbors=settings.cluster_neighbor_count,
            minimum_size=settings.cluster_minimum_size,
        )
        stored = await replace_candidate_clusters(
            conn,
            tenant_id=workspace.tenant_id,
            product_id=product.id,
            groups=groups,
            threshold=settings.cluster_similarity_threshold,
            neighbor_count=settings.cluster_neighbor_count,
            minimum_size=settings.cluster_minimum_size,
            provider=PROVIDER,
            model=settings.gemini_embedding_model,
            model_version=settings.gemini_embedding_version,
        )
        report = _report(
            items,
            stored,
            threshold=settings.cluster_similarity_threshold,
            neighbor_count=settings.cluster_neighbor_count,
            minimum_size=settings.cluster_minimum_size,
        )
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="cluster.completed",
            target_type="product",
            target_id=str(product.id),
            metadata={
                "cluster_count": report.cluster_count,
                "member_count": report.member_count,
            },
        )
    return report


@router.get("/v1/feedback/clusters", response_model=ClusterReport)
async def read_clusters(
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    async with database.user_transaction(user) as conn:
        await ensure_workspace(conn, default_workspace_name(user.email))
        run = await latest_analysis_run(conn)
        if await get_product(conn) is None or run is None:
            return ClusterReport.idle(settings)
        items = await load_feedback_items(conn)
        memberships = await load_cluster_members(conn)
    grouped: dict[UUID, list[UUID]] = {}
    for cluster_id, item_id in memberships:
        grouped.setdefault(cluster_id, []).append(item_id)
    stored = list(grouped.items())
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
    )


def _report(
    items: list[DedupeItem],
    stored: list[tuple[UUID, list[UUID]]],
    *,
    threshold: float,
    neighbor_count: int,
    minimum_size: int,
) -> ClusterReport:
    by_id = {item.id: item for item in items}
    clusters: list[ClusterGroup] = []
    for cluster_id, member_ids in stored[:CLUSTER_LIMIT]:
        members = [_member(by_id[member_id]) for member_id in member_ids if member_id in by_id]
        members.sort(key=lambda member: member.title.casefold())
        if len(members) < minimum_size:
            continue
        clusters.append(ClusterGroup(id=cluster_id, members=members))
    identities = [(str(item.id), item.external_id) for item in items]
    groups = [[str(member_id) for member_id in member_ids] for _cluster_id, member_ids in stored]
    scored = score_themes(groups, identities, list(LABELED_THEMES))
    return ClusterReport(
        ran=True,
        cluster_count=len(stored),
        member_count=sum(len(member_ids) for _cluster_id, member_ids in stored),
        threshold=threshold,
        neighbor_count=neighbor_count,
        minimum_size=minimum_size,
        clusters=clusters,
        evaluation=None if scored is None else _evaluation(scored),
    )


def _member(item: DedupeItem) -> ClusterMember:
    source: Literal["github_issue", "csv"] = "csv" if item.source == "csv" else "github_issue"
    return ClusterMember(id=item.id, source=source, external_id=item.external_id, title=item.title)


def _evaluation(scored: tuple[int, int, float]) -> ClusterEvaluation:
    labeled, gathered, mean_cohesion = scored
    return ClusterEvaluation(labeled=labeled, gathered=gathered, mean_cohesion=mean_cohesion)

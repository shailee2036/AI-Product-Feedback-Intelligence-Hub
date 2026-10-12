from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from feedback_hub.api.me import default_workspace_name
from feedback_hub.auth import CurrentUser
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.clusters import (
    StoredCluster,
    latest_analysis_run,
    load_stored_clusters,
    replace_candidate_clusters,
    save_theme_names,
)
from feedback_hub.db.duplicates import DedupeItem, load_embedding_pairs, load_feedback_items
from feedback_hub.db.engine import Database, get_database
from feedback_hub.db.products import get_product
from feedback_hub.db.workspaces import ensure_workspace, record_audit_event
from feedback_hub.feedback.clusters import LABELED_THEMES, score_themes, theme_groups
from feedback_hub.feedback.groq import GroqClient, GroqError
from feedback_hub.feedback.theme_names import naming_prompt, parse_theme_names, representative_lines

router = APIRouter(tags=["clusters"])

PROVIDER = "gemini"
CLUSTER_LIMIT = 20
NO_PRODUCT = "No product registered yet."
NO_FEEDBACK = "Import feedback before grouping it into themes."
NO_EMBEDDINGS = "Embed feedback before grouping it into themes."
NO_CLUSTERS = "Find themes before naming them."
NO_GROQ = "Add FEEDBACK_HUB_GROQ_API_KEY before naming themes."
NAME_PROVIDER = "groq"


class ClusterMember(BaseModel):
    id: UUID
    source: Literal["github_issue", "csv"]
    external_id: str
    title: str


class ClusterGroup(BaseModel):
    id: UUID
    name: str | None
    summary: str | None
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
    named_count: int
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
            named_count=0,
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
            [
                StoredCluster(
                    id=cluster_id,
                    name=None,
                    summary=None,
                    name_edited=False,
                    member_ids=tuple(member_ids),
                )
                for cluster_id, member_ids in stored
            ],
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
        stored = await load_stored_clusters(conn)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
    )


@router.post("/v1/feedback/clusters/names", response_model=ClusterReport)
async def name_clusters(
    user: CurrentUser,
    request: Request,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Name untitled themes from redacted titles. Edited names stay in place."""
    if settings.groq_api_key is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_GROQ)
    async with database.user_transaction(user) as conn:
        workspace = await ensure_workspace(conn, default_workspace_name(user.email))
        product = await get_product(conn)
        if product is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_PRODUCT)
        run = await latest_analysis_run(conn)
        if run is None:
            raise HTTPException(status.HTTP_409_CONFLICT, NO_CLUSTERS)
        items = await load_feedback_items(conn)
        stored = await load_stored_clusters(conn)
        unnamed = [
            cluster for cluster in stored if cluster.name is None and not cluster.name_edited
        ]
        themes, id_map = _naming_inputs(items, unnamed)
        if themes:
            client: GroqClient = request.app.state.groq
            try:
                parsed = parse_theme_names(await client.complete(naming_prompt(themes)))
            except (GroqError, ValueError) as exc:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
            to_save = [
                (id_map[key], name, summary)
                for key, (name, summary) in parsed.items()
                if key in id_map
            ]
            await save_theme_names(
                conn, to_save, provider=NAME_PROVIDER, model=settings.groq_theme_model
            )
            stored = _with_saved_names(stored, to_save)
            await record_audit_event(
                conn,
                tenant_id=workspace.tenant_id,
                actor_id=user.id,
                action="cluster.named",
                target_type="product",
                target_id=str(product.id),
                metadata={"named_count": len(to_save)},
            )
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
    )


def _naming_inputs(
    items: list[DedupeItem], clusters: list[StoredCluster]
) -> tuple[list[tuple[str, list[str]]], dict[str, UUID]]:
    by_id = {item.id: item for item in items}
    themes: list[tuple[str, list[str]]] = []
    id_map: dict[str, UUID] = {}
    for cluster in clusters:
        titles = [by_id[member_id].title for member_id in cluster.member_ids if member_id in by_id]
        samples = representative_lines(titles)
        if not samples:
            continue
        key = str(len(themes) + 1)
        id_map[key] = cluster.id
        themes.append((key, samples))
    return themes, id_map


def _with_saved_names(
    stored: list[StoredCluster], saved: list[tuple[UUID, str, str]]
) -> list[StoredCluster]:
    by_id = {cluster_id: (name, summary) for cluster_id, name, summary in saved}
    updated: list[StoredCluster] = []
    for cluster in stored:
        replacement = by_id.get(cluster.id)
        if replacement is None:
            updated.append(cluster)
            continue
        name, summary = replacement
        updated.append(
            StoredCluster(
                id=cluster.id,
                name=name,
                summary=summary,
                name_edited=cluster.name_edited,
                member_ids=cluster.member_ids,
            )
        )
    return updated


def _report(
    items: list[DedupeItem],
    stored: list[StoredCluster],
    *,
    threshold: float,
    neighbor_count: int,
    minimum_size: int,
) -> ClusterReport:
    by_id = {item.id: item for item in items}
    clusters: list[ClusterGroup] = []
    for cluster in stored[:CLUSTER_LIMIT]:
        members = [
            _member(by_id[member_id]) for member_id in cluster.member_ids if member_id in by_id
        ]
        members.sort(key=lambda member: member.title.casefold())
        if len(members) < minimum_size:
            continue
        clusters.append(
            ClusterGroup(id=cluster.id, name=cluster.name, summary=cluster.summary, members=members)
        )
    identities = [(str(item.id), item.external_id) for item in items]
    groups = [[str(member_id) for member_id in cluster.member_ids] for cluster in stored]
    scored = score_themes(groups, identities, list(LABELED_THEMES))
    return ClusterReport(
        ran=True,
        cluster_count=len(stored),
        member_count=sum(len(cluster.member_ids) for cluster in stored),
        threshold=threshold,
        neighbor_count=neighbor_count,
        minimum_size=minimum_size,
        named_count=sum(cluster.name is not None for cluster in stored),
        clusters=clusters,
        evaluation=None if scored is None else _evaluation(scored),
    )


def _member(item: DedupeItem) -> ClusterMember:
    source: Literal["github_issue", "csv"] = "csv" if item.source == "csv" else "github_issue"
    return ClusterMember(id=item.id, source=source, external_id=item.external_id, title=item.title)


def _evaluation(scored: tuple[int, int, float]) -> ClusterEvaluation:
    labeled, gathered, mean_cohesion = scored
    return ClusterEvaluation(labeled=labeled, gathered=gathered, mean_cohesion=mean_cohesion)

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from feedback_hub.api.me import default_workspace_name
from feedback_hub.auth import CurrentUser
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.briefs import StoredBrief, load_product_briefs, save_product_brief
from feedback_hub.db.clusters import (
    AnalysisRun,
    ClusterStatus,
    StoredCluster,
    latest_analysis_run,
    load_stored_clusters,
    merge_cluster_members,
    partition_members,
    relabel_cluster,
    replace_candidate_clusters,
    save_theme_names,
    set_cluster_status,
    split_cluster_members,
)
from feedback_hub.db.duplicates import (
    DedupeItem,
    load_duplicate_edges,
    load_embedded_item_ids,
    load_embedding_pairs,
    load_feedback_items,
)
from feedback_hub.db.engine import Database, get_database
from feedback_hub.db.products import RegisteredProduct, get_product
from feedback_hub.db.workspaces import Workspace, ensure_workspace, record_audit_event
from feedback_hub.feedback.clusters import LABELED_THEMES, score_themes, theme_groups
from feedback_hub.feedback.groq import GroqClient, GroqError
from feedback_hub.feedback.normalize import prepare_text
from feedback_hub.feedback.theme_briefs import brief_prompt, brief_samples, parse_theme_brief
from feedback_hub.feedback.theme_names import naming_prompt, parse_theme_names, representative_lines
from feedback_hub.feedback.theme_scores import ScoreFact, score_cluster

router = APIRouter(tags=["clusters"])

PROVIDER = "gemini"
CLUSTER_LIMIT = 20
NO_PRODUCT = "No product registered yet."
NO_FEEDBACK = "Import feedback before grouping it into themes."
NO_EMBEDDINGS = "Embed feedback before grouping it into themes."
NO_CLUSTERS = "Find themes before naming them."
NO_GROQ = "Add FEEDBACK_HUB_GROQ_API_KEY before naming themes."
NO_BRIEF = "Add FEEDBACK_HUB_GROQ_API_KEY before writing a brief."
NO_THEME = "That theme is no longer available."
NO_MERGE = "Choose a different theme to merge into."
NO_SPLIT = "Keep at least one row in the original theme, and move at least one row out."
NO_NAME = "Enter a theme name."
NO_APPROVED = "Approve the theme before writing a brief."
NAME_PROVIDER = "groq"
BRIEF_SYSTEM = "You write evidence-linked product briefs. Reply with JSON only."


class ClusterMember(BaseModel):
    id: UUID
    source: Literal["github_issue", "csv"]
    external_id: str
    title: str


class ClusterScore(BaseModel):
    member_count: int
    recent_count: int
    recent_days: int
    source_count: int
    unique_count: int
    embedded_count: int
    named: bool
    score: float


class ClusterBrief(BaseModel):
    problem: str
    impact: str
    evidence_summary: str
    non_goals: str
    acceptance_criteria: str
    open_questions: str
    evidence_ids: list[UUID]


class ClusterGroup(BaseModel):
    id: UUID
    name: str | None
    summary: str | None
    status: ClusterStatus
    members: list[ClusterMember]
    score: ClusterScore
    brief: ClusterBrief | None


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
    approved_count: int
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
            approved_count=0,
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
        existing = await load_stored_clusters(conn)
        approved_ids = {
            member_id
            for cluster in existing
            if cluster.status == "approved"
            for member_id in cluster.member_ids
        }
        open_pairs = [
            (left, right, score)
            for left, right, score in pairs
            if left not in approved_ids and right not in approved_ids
        ]
        groups = theme_groups(
            [(str(left), str(right), score) for left, right, score in open_pairs],
            threshold=settings.cluster_similarity_threshold,
            neighbors=settings.cluster_neighbor_count,
            minimum_size=settings.cluster_minimum_size,
        )
        await replace_candidate_clusters(
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
        stored = await load_stored_clusters(conn)
        edges, embedded, briefs = await _report_inputs(conn, settings)
        report = _report(
            items,
            stored,
            threshold=settings.cluster_similarity_threshold,
            neighbor_count=settings.cluster_neighbor_count,
            minimum_size=settings.cluster_minimum_size,
            edges=edges,
            embedded=embedded,
            briefs=briefs,
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
        edges, embedded, briefs = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=edges,
        embedded=embedded,
        briefs=briefs,
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
            cluster
            for cluster in stored
            if cluster.status == "open" and cluster.name is None and not cluster.name_edited
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
        edges, embedded, briefs = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=edges,
        embedded=embedded,
        briefs=briefs,
    )


class ThemeLabel(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    summary: str = Field(default="", max_length=400)


class ThemeDecisionBody(BaseModel):
    decision: Literal["approve", "dismiss"]


class ThemeMergeBody(BaseModel):
    target_id: UUID


class ThemeSplitBody(BaseModel):
    member_ids: list[UUID] = Field(min_length=1)


@router.patch("/v1/feedback/clusters/{cluster_id}", response_model=ClusterReport)
async def relabel_theme(
    cluster_id: UUID,
    body: ThemeLabel,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Save a name a person wrote. Later naming runs leave it alone."""
    name = _clean_label(body.name, 80)
    summary = _clean_label(body.summary, 400) or None
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NO_NAME)
    async with database.user_transaction(user) as conn:
        workspace, product, run, items, stored = await _review_context(conn, user)
        if _find_cluster(stored, cluster_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_THEME)
        await relabel_cluster(conn, cluster_id, name=name, summary=summary)
        stored = await load_stored_clusters(conn)
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="cluster.relabeled",
            target_type="candidate_cluster",
            target_id=str(cluster_id),
            metadata={"product_id": str(product.id)},
        )
        edges, embedded, briefs = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=edges,
        embedded=embedded,
        briefs=briefs,
    )


@router.post("/v1/feedback/clusters/{cluster_id}/decision", response_model=ClusterReport)
async def decide_theme(
    cluster_id: UUID,
    body: ThemeDecisionBody,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Approve a theme so the next clustering run keeps it, or dismiss it."""
    next_status: ClusterStatus = "approved" if body.decision == "approve" else "dismissed"
    async with database.user_transaction(user) as conn:
        workspace, product, run, items, stored = await _review_context(conn, user)
        if _find_cluster(stored, cluster_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_THEME)
        await set_cluster_status(conn, cluster_id, next_status)
        stored = await load_stored_clusters(conn)
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="cluster.approved" if next_status == "approved" else "cluster.dismissed",
            target_type="candidate_cluster",
            target_id=str(cluster_id),
            metadata={"product_id": str(product.id)},
        )
        edges, embedded, briefs = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=edges,
        embedded=embedded,
        briefs=briefs,
    )


@router.post("/v1/feedback/clusters/{cluster_id}/merge", response_model=ClusterReport)
async def merge_theme(
    cluster_id: UUID,
    body: ThemeMergeBody,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Move every row from this theme into another theme."""
    if body.target_id == cluster_id:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_MERGE)
    async with database.user_transaction(user) as conn:
        workspace, product, run, items, stored = await _review_context(conn, user)
        source = _find_cluster(stored, cluster_id)
        target = _find_cluster(stored, body.target_id)
        if source is None or target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_THEME)
        await merge_cluster_members(conn, source, target)
        stored = await load_stored_clusters(conn)
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="cluster.merged",
            target_type="candidate_cluster",
            target_id=str(body.target_id),
            metadata={"source_id": str(cluster_id), "product_id": str(product.id)},
        )
        edges, embedded, briefs = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=edges,
        embedded=embedded,
        briefs=briefs,
    )


@router.post("/v1/feedback/clusters/{cluster_id}/split", response_model=ClusterReport)
async def split_theme(
    cluster_id: UUID,
    body: ThemeSplitBody,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Move the selected rows into a new theme and leave the rest in place."""
    async with database.user_transaction(user) as conn:
        workspace, product, run, items, stored = await _review_context(conn, user)
        source = _find_cluster(stored, cluster_id)
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_THEME)
        plan = partition_members(source.member_ids, body.member_ids)
        if plan is None:
            raise HTTPException(status.HTTP_409_CONFLICT, NO_SPLIT)
        _staying, moving = plan
        created = await split_cluster_members(conn, source, moving)
        stored = await load_stored_clusters(conn)
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="cluster.split",
            target_type="candidate_cluster",
            target_id=str(created),
            metadata={"source_id": str(cluster_id), "product_id": str(product.id)},
        )
        edges, embedded, briefs = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=edges,
        embedded=embedded,
        briefs=briefs,
    )


@router.post("/v1/feedback/clusters/{cluster_id}/brief", response_model=ClusterReport)
async def write_theme_brief(
    cluster_id: UUID,
    user: CurrentUser,
    request: Request,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Write an evidence-linked brief for an approved theme. A later write replaces it."""
    if settings.groq_api_key is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_BRIEF)
    async with database.user_transaction(user) as conn:
        workspace, product, run, items, stored = await _review_context(conn, user)
        cluster = _find_cluster(stored, cluster_id)
        if cluster is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_THEME)
        if cluster.status != "approved":
            raise HTTPException(status.HTTP_409_CONFLICT, NO_APPROVED)
        by_id = {item.id: item for item in items}
        samples = brief_samples(
            [
                (member_id, by_id[member_id].title)
                for member_id in cluster.member_ids
                if member_id in by_id
            ]
        )
        client: GroqClient = request.app.state.groq
        try:
            parsed = parse_theme_brief(
                await client.complete(
                    brief_prompt(cluster.name or "Untitled theme", samples),
                    system=BRIEF_SYSTEM,
                    model=settings.groq_theme_model,
                ),
                set(cluster.member_ids),
            )
        except (GroqError, ValueError) as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        await save_product_brief(
            conn,
            cluster_id=cluster.id,
            tenant_id=workspace.tenant_id,
            product_id=product.id,
            brief=parsed,
            provider=NAME_PROVIDER,
            model=settings.groq_theme_model,
        )
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="cluster.briefed",
            target_type="candidate_cluster",
            target_id=str(cluster.id),
            metadata={"product_id": str(product.id)},
        )
        edges, embedded, briefs = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=edges,
        embedded=embedded,
        briefs=briefs,
    )


async def _review_context(
    conn: AsyncConnection, user: CurrentUser
) -> tuple[Workspace, RegisteredProduct, AnalysisRun, list[DedupeItem], list[StoredCluster]]:
    workspace = await ensure_workspace(conn, default_workspace_name(user.email))
    product = await get_product(conn)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_PRODUCT)
    run = await latest_analysis_run(conn)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_THEME)
    items = await load_feedback_items(conn)
    stored = await load_stored_clusters(conn)
    return workspace, product, run, items, stored


def _find_cluster(stored: list[StoredCluster], cluster_id: UUID) -> StoredCluster | None:
    return next((cluster for cluster in stored if cluster.id == cluster_id), None)


def _clean_label(value: str, limit: int) -> str:
    return prepare_text(value).text[:limit].strip()


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
                status=cluster.status,
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
    edges: list[tuple[UUID, UUID]],
    embedded: set[UUID],
    briefs: dict[UUID, StoredBrief],
    now: datetime | None = None,
) -> ClusterReport:
    by_id = {item.id: item for item in items}
    facts = {item.id: ScoreFact(item.source, item.source_created_at) for item in items}
    moment = now or datetime.now(UTC)
    clusters: list[ClusterGroup] = []
    for cluster in stored[:CLUSTER_LIMIT]:
        members = [
            _member(by_id[member_id]) for member_id in cluster.member_ids if member_id in by_id
        ]
        members.sort(key=lambda member: member.title.casefold())
        if not members:
            continue
        clusters.append(
            ClusterGroup(
                id=cluster.id,
                name=cluster.name,
                summary=cluster.summary,
                status=cluster.status,
                members=members,
                score=_cluster_score(
                    tuple(member.id for member in members),
                    facts=facts,
                    embedded=embedded,
                    edges=edges,
                    named=cluster.name is not None,
                    now=moment,
                ),
                brief=_public_brief(briefs.get(cluster.id), {member.id for member in members}),
            )
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
        approved_count=sum(cluster.status == "approved" for cluster in stored),
        clusters=clusters,
        evaluation=None if scored is None else _evaluation(scored),
    )


def _cluster_score(
    member_ids: tuple[UUID, ...],
    *,
    facts: dict[UUID, ScoreFact],
    embedded: set[UUID],
    edges: list[tuple[UUID, UUID]],
    named: bool,
    now: datetime,
) -> ClusterScore:
    factors = score_cluster(
        member_ids,
        facts=facts,
        embedded=embedded,
        edges=edges,
        named=named,
        now=now,
    )
    return ClusterScore(
        member_count=factors.member_count,
        recent_count=factors.recent_count,
        recent_days=factors.recent_days,
        source_count=factors.source_count,
        unique_count=factors.unique_count,
        embedded_count=factors.embedded_count,
        named=factors.named,
        score=factors.score,
    )


async def _report_inputs(
    conn: AsyncConnection, settings: Settings
) -> tuple[list[tuple[UUID, UUID]], set[UUID], dict[UUID, StoredBrief]]:
    edges = [(edge.left_item_id, edge.right_item_id) for edge in await load_duplicate_edges(conn)]
    embedded = set(
        await load_embedded_item_ids(
            conn,
            provider=PROVIDER,
            model=settings.gemini_embedding_model,
            model_version=settings.gemini_embedding_version,
        )
    )
    briefs = {brief.cluster_id: brief for brief in await load_product_briefs(conn)}
    return edges, embedded, briefs


def _public_brief(stored: StoredBrief | None, member_ids: set[UUID]) -> ClusterBrief | None:
    if stored is None:
        return None
    cited = [item_id for item_id in stored.evidence_ids if item_id in member_ids]
    return ClusterBrief(
        problem=stored.problem,
        impact=stored.impact,
        evidence_summary=stored.evidence_summary,
        non_goals=stored.non_goals,
        acceptance_criteria=stored.acceptance_criteria,
        open_questions=stored.open_questions,
        evidence_ids=cited,
    )


def _member(item: DedupeItem) -> ClusterMember:
    source: Literal["github_issue", "csv"] = "csv" if item.source == "csv" else "github_issue"
    return ClusterMember(id=item.id, source=source, external_id=item.external_id, title=item.title)


def _evaluation(scored: tuple[int, int, float]) -> ClusterEvaluation:
    labeled, gathered, mean_cohesion = scored
    return ClusterEvaluation(labeled=labeled, gathered=gathered, mean_cohesion=mean_cohesion)

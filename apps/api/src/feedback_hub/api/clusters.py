from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from feedback_hub.api.me import default_workspace_name
from feedback_hub.auth import CurrentUser
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.briefs import (
    StoredBrief,
    StoredVersion,
    load_brief_versions,
    load_product_briefs,
    save_product_brief,
)
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
    load_github_issue_signals,
)
from feedback_hub.db.engine import Database, get_database
from feedback_hub.db.issue_drafts import StoredIssueDraft, load_issue_drafts, save_issue_draft
from feedback_hub.db.products import RegisteredProduct, get_product
from feedback_hub.db.suggestions import (
    StoredSuggestion,
    load_issue_suggestions,
    save_issue_suggestion,
)
from feedback_hub.db.workspaces import Workspace, ensure_workspace, record_audit_event
from feedback_hub.feedback.canonical import (
    IssueSignal,
    final_open_issue_warnings,
    recommend_canonical,
)
from feedback_hub.feedback.clusters import LABELED_THEMES, score_themes, theme_groups
from feedback_hub.feedback.groq import GroqClient, GroqError, generation_key, generation_target
from feedback_hub.feedback.issue_suggestions import IssueDraft, suggest_issue_update
from feedback_hub.feedback.new_issues import (
    NewIssueText,
    clean_issue_body,
    clean_issue_title,
    draft_new_issue,
)
from feedback_hub.feedback.normalize import prepare_text
from feedback_hub.feedback.theme_briefs import (
    brief_from_edit,
    brief_prompt,
    brief_samples,
    parse_theme_brief,
)
from feedback_hub.feedback.theme_names import naming_prompt, parse_theme_names, representative_lines
from feedback_hub.feedback.theme_scores import ScoreFact, score_cluster

router = APIRouter(tags=["clusters"])

PROVIDER = "gemini"
CLUSTER_LIMIT = 20
NO_PRODUCT = "No product registered yet."
NO_FEEDBACK = "Import feedback before grouping it into themes."
NO_EMBEDDINGS = "Embed feedback before grouping it into themes."
NO_CLUSTERS = "Find themes before naming them."
NO_GROQ = "Add FEEDBACK_HUB_GROQ_API_KEY or a LiteLLM proxy before naming themes."
NO_BRIEF = "Add FEEDBACK_HUB_GROQ_API_KEY or a LiteLLM proxy before writing a brief."
NO_THEME = "That theme is no longer available."
NO_MERGE = "Choose a different theme to merge into."
NO_SPLIT = "Keep at least one row in the original theme, and move at least one row out."
NO_NAME = "Enter a theme name."
NO_APPROVED = "Approve the theme before writing a brief."
NO_CANONICAL = "No imported GitHub issue is available for this theme."
NO_SUGGESTION = "Approve the theme before saving a suggestion."
NO_DRAFT = "Approve the theme before drafting a new issue."
NO_CONFIRM = "Confirm the draft before saving it. Nothing is created on GitHub."
NO_GITHUB_WRITE = (
    "Creating a GitHub issue is not enabled. A confirmed draft is saved only in the workspace."
)
NO_DRAFT_TEXT = "Write a title and a body before saving the draft."
NO_BRIEF_YET = "Write a brief before editing it."
NO_SECTION = "Fill in every section of the brief."
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


class CanonicalIssue(BaseModel):
    id: UUID
    number: int
    title: str
    html_url: str
    state: Literal["open", "closed"]
    comment_count: int
    reactions_total: int
    coverage: float
    recent: bool
    recent_days: int
    score: float


class DuplicateWarning(BaseModel):
    id: UUID
    number: int
    title: str
    html_url: str
    similarity: float
    in_theme: bool


class IssueSuggestion(BaseModel):
    comment: str
    labels: list[str]
    saved: bool


class NewIssueDraft(BaseModel):
    title: str
    body: str
    labels: list[str]
    warnings: list[DuplicateWarning]
    saved: bool


class NewIssuePreview(BaseModel):
    title: str
    body: str
    labels: list[str]
    warnings: list[DuplicateWarning]


class ConfirmIssueDraft(BaseModel):
    confirmed: bool
    create_on_github: bool = False
    title: str | None = Field(default=None, max_length=2000)
    body: str | None = Field(default=None, max_length=4000)


class BriefVersion(BaseModel):
    version: int
    source: Literal["generated", "edited"]
    problem: str
    created_at: datetime


class ClusterBrief(BaseModel):
    problem: str
    impact: str
    evidence_summary: str
    non_goals: str
    acceptance_criteria: str
    open_questions: str
    evidence_ids: list[UUID]
    version: int
    source: Literal["generated", "edited"]
    history: list[BriefVersion]


class ClusterGroup(BaseModel):
    id: UUID
    name: str | None
    summary: str | None
    status: ClusterStatus
    members: list[ClusterMember]
    score: ClusterScore
    brief: ClusterBrief | None
    canonical: CanonicalIssue | None
    duplicate_warnings: list[DuplicateWarning]
    suggestion: IssueSuggestion | None
    new_issue: NewIssueDraft | None


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
        loaded = await _report_inputs(conn, settings)
        report = _report(
            items,
            stored,
            threshold=settings.cluster_similarity_threshold,
            neighbor_count=settings.cluster_neighbor_count,
            minimum_size=settings.cluster_minimum_size,
            edges=loaded.edges,
            embedded=loaded.embedded,
            briefs=loaded.briefs,
            history=loaded.history,
            issues=loaded.issues,
            pairs=loaded.pairs,
            duplicate_threshold=settings.duplicate_similarity_threshold,
            suggestions=loaded.suggestions,
            drafts=loaded.drafts,
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
        loaded = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=loaded.edges,
        embedded=loaded.embedded,
        briefs=loaded.briefs,
        history=loaded.history,
        issues=loaded.issues,
        pairs=loaded.pairs,
        duplicate_threshold=settings.duplicate_similarity_threshold,
        suggestions=loaded.suggestions,
        drafts=loaded.drafts,
    )


@router.post("/v1/feedback/clusters/names", response_model=ClusterReport)
async def name_clusters(
    user: CurrentUser,
    request: Request,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Name untitled themes from redacted titles. Edited names stay in place."""
    if generation_key(settings) is None:
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
            target = generation_target(settings)
            await save_theme_names(conn, to_save, provider=target.provider, model=target.model)
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
        loaded = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=loaded.edges,
        embedded=loaded.embedded,
        briefs=loaded.briefs,
        history=loaded.history,
        issues=loaded.issues,
        pairs=loaded.pairs,
        duplicate_threshold=settings.duplicate_similarity_threshold,
        suggestions=loaded.suggestions,
        drafts=loaded.drafts,
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
        loaded = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=loaded.edges,
        embedded=loaded.embedded,
        briefs=loaded.briefs,
        history=loaded.history,
        issues=loaded.issues,
        pairs=loaded.pairs,
        duplicate_threshold=settings.duplicate_similarity_threshold,
        suggestions=loaded.suggestions,
        drafts=loaded.drafts,
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
        loaded = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=loaded.edges,
        embedded=loaded.embedded,
        briefs=loaded.briefs,
        history=loaded.history,
        issues=loaded.issues,
        pairs=loaded.pairs,
        duplicate_threshold=settings.duplicate_similarity_threshold,
        suggestions=loaded.suggestions,
        drafts=loaded.drafts,
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
        loaded = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=loaded.edges,
        embedded=loaded.embedded,
        briefs=loaded.briefs,
        history=loaded.history,
        issues=loaded.issues,
        pairs=loaded.pairs,
        duplicate_threshold=settings.duplicate_similarity_threshold,
        suggestions=loaded.suggestions,
        drafts=loaded.drafts,
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
        loaded = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=loaded.edges,
        embedded=loaded.embedded,
        briefs=loaded.briefs,
        history=loaded.history,
        issues=loaded.issues,
        pairs=loaded.pairs,
        duplicate_threshold=settings.duplicate_similarity_threshold,
        suggestions=loaded.suggestions,
        drafts=loaded.drafts,
    )


@router.post("/v1/feedback/clusters/{cluster_id}/brief", response_model=ClusterReport)
async def write_theme_brief(
    cluster_id: UUID,
    user: CurrentUser,
    request: Request,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Write an evidence-linked brief for an approved theme. Earlier versions stay stored."""
    if generation_key(settings) is None:
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
                ),
                set(cluster.member_ids),
            )
        except (GroqError, ValueError) as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        target = generation_target(settings)
        await save_product_brief(
            conn,
            cluster_id=cluster.id,
            tenant_id=workspace.tenant_id,
            product_id=product.id,
            brief=parsed,
            source="generated",
            provider=target.provider,
            model=target.model,
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
        loaded = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=loaded.edges,
        embedded=loaded.embedded,
        briefs=loaded.briefs,
        history=loaded.history,
        issues=loaded.issues,
        pairs=loaded.pairs,
        duplicate_threshold=settings.duplicate_similarity_threshold,
        suggestions=loaded.suggestions,
        drafts=loaded.drafts,
    )


class ThemeBriefEdit(BaseModel):
    problem: str = Field(min_length=1, max_length=400)
    impact: str = Field(min_length=1, max_length=400)
    evidence_summary: str = Field(min_length=1, max_length=600)
    non_goals: str = Field(min_length=1, max_length=400)
    acceptance_criteria: str = Field(min_length=1, max_length=600)
    open_questions: str = Field(min_length=1, max_length=400)


@router.patch("/v1/feedback/clusters/{cluster_id}/brief", response_model=ClusterReport)
async def edit_theme_brief(
    cluster_id: UUID,
    body: ThemeBriefEdit,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Save a person's edits as a new version and keep the earlier text."""
    async with database.user_transaction(user) as conn:
        workspace, product, run, items, stored = await _review_context(conn, user)
        cluster = _find_cluster(stored, cluster_id)
        if cluster is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_THEME)
        current = next(
            (item for item in await load_product_briefs(conn) if item.cluster_id == cluster_id),
            None,
        )
        if current is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_BRIEF_YET)
        try:
            edited = brief_from_edit(
                {
                    "problem": body.problem,
                    "impact": body.impact,
                    "evidence_summary": body.evidence_summary,
                    "non_goals": body.non_goals,
                    "acceptance_criteria": body.acceptance_criteria,
                    "open_questions": body.open_questions,
                },
                current.evidence_ids,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        await save_product_brief(
            conn,
            cluster_id=cluster.id,
            tenant_id=workspace.tenant_id,
            product_id=product.id,
            brief=edited,
            source="edited",
            provider=None,
            model=None,
        )
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="cluster.brief_edited",
            target_type="candidate_cluster",
            target_id=str(cluster.id),
            metadata={"product_id": str(product.id)},
        )
        loaded = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=loaded.edges,
        embedded=loaded.embedded,
        briefs=loaded.briefs,
        history=loaded.history,
        issues=loaded.issues,
        pairs=loaded.pairs,
        duplicate_threshold=settings.duplicate_similarity_threshold,
        suggestions=loaded.suggestions,
        drafts=loaded.drafts,
    )


@router.post("/v1/feedback/clusters/{cluster_id}/suggestion", response_model=ClusterReport)
async def save_theme_suggestion(
    cluster_id: UUID,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Store the suggested comment locally. Nothing is posted to GitHub."""
    async with database.user_transaction(user) as conn:
        workspace, product, run, items, stored = await _review_context(conn, user)
        cluster = _find_cluster(stored, cluster_id)
        if cluster is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_THEME)
        if cluster.status != "approved":
            raise HTTPException(status.HTTP_409_CONFLICT, NO_SUGGESTION)
        loaded = await _report_inputs(conn, settings)
        by_id = {item.id: item for item in items}
        member_ids = tuple(member_id for member_id in cluster.member_ids if member_id in by_id)
        canonical, _warnings = _canonical_issue(
            member_ids,
            issues=loaded.issues,
            pairs=loaded.pairs,
            now=datetime.now(UTC),
            duplicate_threshold=settings.duplicate_similarity_threshold,
        )
        if canonical is None:
            raise HTTPException(status.HTTP_409_CONFLICT, NO_CANONICAL)
        draft = _issue_draft(cluster, by_id, canonical, loaded.briefs.get(cluster.id))
        await save_issue_suggestion(
            conn,
            cluster_id=cluster.id,
            tenant_id=workspace.tenant_id,
            product_id=product.id,
            feedback_item_id=canonical.id,
            comment=draft.comment,
            labels=draft.labels,
        )
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="cluster.suggestion_saved",
            target_type="candidate_cluster",
            target_id=str(cluster.id),
            metadata={"product_id": str(product.id), "feedback_item_id": str(canonical.id)},
        )
        loaded = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=loaded.edges,
        embedded=loaded.embedded,
        briefs=loaded.briefs,
        history=loaded.history,
        issues=loaded.issues,
        pairs=loaded.pairs,
        duplicate_threshold=settings.duplicate_similarity_threshold,
        suggestions=loaded.suggestions,
        drafts=loaded.drafts,
    )


@router.post("/v1/feedback/clusters/{cluster_id}/issue-draft", response_model=NewIssuePreview)
async def preview_new_issue(
    cluster_id: UUID,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> NewIssuePreview:
    """Show a new-issue draft and similar open issues. Nothing is saved or created."""
    async with database.user_transaction(user) as conn:
        *_, cluster, loaded, by_id, member_ids = await _approved_theme_context(
            conn, user, cluster_id, settings
        )
        generated = _generated_issue(cluster, by_id, loaded.briefs.get(cluster.id))
        warnings = _open_issue_warnings(
            member_ids,
            issues=loaded.issues,
            pairs=loaded.pairs,
            duplicate_threshold=settings.duplicate_similarity_threshold,
        )
    return NewIssuePreview(
        title=generated.title,
        body=generated.body,
        labels=list(generated.labels),
        warnings=warnings,
    )


@router.post(
    "/v1/feedback/clusters/{cluster_id}/issue-draft/confirmation",
    response_model=ClusterReport,
)
async def confirm_new_issue(
    cluster_id: UUID,
    body: ConfirmIssueDraft,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterReport:
    """Save a confirmed draft in the workspace. Creating a GitHub issue is rejected."""
    if body.create_on_github:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_GITHUB_WRITE)
    if not body.confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_CONFIRM)
    async with database.user_transaction(user) as conn:
        (
            workspace,
            product,
            run,
            items,
            stored,
            cluster,
            loaded,
            by_id,
            member_ids,
        ) = await _approved_theme_context(conn, user, cluster_id, settings)
        generated = _generated_issue(cluster, by_id, loaded.briefs.get(cluster.id))
        title, draft_body = _draft_text(generated, body.title, body.body)
        warnings = _open_issue_warnings(
            member_ids,
            issues=loaded.issues,
            pairs=loaded.pairs,
            duplicate_threshold=settings.duplicate_similarity_threshold,
        )
        await save_issue_draft(
            conn,
            cluster_id=cluster.id,
            tenant_id=workspace.tenant_id,
            product_id=product.id,
            title=title,
            body=draft_body,
            labels=generated.labels,
        )
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="cluster.issue_draft_saved",
            target_type="candidate_cluster",
            target_id=str(cluster.id),
            metadata={"product_id": str(product.id), "warning_count": len(warnings)},
        )
        loaded = await _report_inputs(conn, settings)
    return _report(
        items,
        stored,
        threshold=run.threshold,
        neighbor_count=run.neighbor_count,
        minimum_size=run.minimum_size,
        edges=loaded.edges,
        embedded=loaded.embedded,
        briefs=loaded.briefs,
        history=loaded.history,
        issues=loaded.issues,
        pairs=loaded.pairs,
        duplicate_threshold=settings.duplicate_similarity_threshold,
        suggestions=loaded.suggestions,
        drafts=loaded.drafts,
    )


async def _approved_theme_context(
    conn: AsyncConnection,
    user: CurrentUser,
    cluster_id: UUID,
    settings: Settings,
) -> tuple[
    Workspace,
    RegisteredProduct,
    AnalysisRun,
    list[DedupeItem],
    list[StoredCluster],
    StoredCluster,
    "_ReportInputs",
    dict[UUID, DedupeItem],
    tuple[UUID, ...],
]:
    workspace, product, run, items, stored = await _review_context(conn, user)
    cluster = _find_cluster(stored, cluster_id)
    if cluster is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_THEME)
    if cluster.status != "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, NO_DRAFT)
    loaded = await _report_inputs(conn, settings)
    by_id = {item.id: item for item in items}
    member_ids = tuple(member_id for member_id in cluster.member_ids if member_id in by_id)
    return workspace, product, run, items, stored, cluster, loaded, by_id, member_ids


def _generated_issue(
    cluster: StoredCluster, by_id: dict[UUID, DedupeItem], brief: StoredBrief | None
) -> NewIssueText:
    rows = [by_id[member_id] for member_id in cluster.member_ids if member_id in by_id]
    return draft_new_issue(
        theme_name=cluster.name,
        theme_summary=cluster.summary,
        brief_problem=None if brief is None else brief.problem,
        brief_impact=None if brief is None else brief.impact,
        brief_evidence=None if brief is None else brief.evidence_summary,
        reports=[row.title for row in rows if row.source == "csv"],
        areas=[row.product_area for row in rows],
    )


def _draft_text(generated: NewIssueText, title: str | None, body: str | None) -> tuple[str, str]:
    chosen_title = generated.title if title is None else clean_issue_title(title)
    chosen_body = generated.body if body is None else clean_issue_body(body)
    if not chosen_title or not chosen_body:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_DRAFT_TEXT)
    return chosen_title, chosen_body


def _open_issue_warnings(
    member_ids: tuple[UUID, ...],
    *,
    issues: dict[UUID, IssueSignal],
    pairs: list[tuple[UUID, UUID, float]],
    duplicate_threshold: float,
) -> list[DuplicateWarning]:
    warnings = final_open_issue_warnings(
        member_ids, issues, pairs, duplicate_threshold=duplicate_threshold
    )
    return [
        DuplicateWarning(
            id=warning.issue.id,
            number=warning.issue.number,
            title=warning.issue.title,
            html_url=warning.issue.html_url,
            similarity=warning.similarity,
            in_theme=warning.in_theme,
        )
        for warning in warnings
    ]


def _public_new_issue(
    stored: StoredIssueDraft | None, warnings: list[DuplicateWarning]
) -> NewIssueDraft | None:
    if stored is None:
        return None
    return NewIssueDraft(
        title=stored.title,
        body=stored.body,
        labels=list(stored.labels),
        warnings=warnings,
        saved=True,
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
    history: dict[UUID, list[StoredVersion]],
    issues: dict[UUID, IssueSignal],
    pairs: list[tuple[UUID, UUID, float]],
    duplicate_threshold: float,
    suggestions: dict[UUID, StoredSuggestion],
    drafts: dict[UUID, StoredIssueDraft],
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
        member_ids = tuple(member.id for member in members)
        canonical, warnings = _canonical_issue(
            member_ids,
            issues=issues,
            pairs=pairs,
            now=moment,
            duplicate_threshold=duplicate_threshold,
        )
        stored_brief = briefs.get(cluster.id)
        draft = None if canonical is None else _issue_draft(cluster, by_id, canonical, stored_brief)
        clusters.append(
            ClusterGroup(
                id=cluster.id,
                name=cluster.name,
                summary=cluster.summary,
                status=cluster.status,
                members=members,
                score=_cluster_score(
                    member_ids,
                    facts=facts,
                    embedded=embedded,
                    edges=edges,
                    named=cluster.name is not None,
                    now=moment,
                ),
                brief=_public_brief(
                    briefs.get(cluster.id),
                    set(member_ids),
                    history.get(cluster.id, []),
                ),
                canonical=canonical,
                duplicate_warnings=warnings,
                suggestion=None
                if draft is None or canonical is None
                else _public_suggestion(draft, suggestions.get(cluster.id), canonical.id),
                new_issue=_public_new_issue(
                    drafts.get(cluster.id),
                    _open_issue_warnings(
                        member_ids,
                        issues=issues,
                        pairs=pairs,
                        duplicate_threshold=duplicate_threshold,
                    ),
                ),
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


@dataclass(frozen=True, slots=True)
class _ReportInputs:
    edges: list[tuple[UUID, UUID]]
    embedded: set[UUID]
    briefs: dict[UUID, StoredBrief]
    history: dict[UUID, list[StoredVersion]]
    issues: dict[UUID, IssueSignal]
    pairs: list[tuple[UUID, UUID, float]]
    suggestions: dict[UUID, StoredSuggestion]
    drafts: dict[UUID, StoredIssueDraft]


async def _report_inputs(conn: AsyncConnection, settings: Settings) -> _ReportInputs:
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
    history: dict[UUID, list[StoredVersion]] = {}
    for version in await load_brief_versions(conn):
        history.setdefault(version.cluster_id, []).append(version)
    issues = {issue.id: issue for issue in await load_github_issue_signals(conn)}
    suggestions = {
        suggestion.cluster_id: suggestion for suggestion in await load_issue_suggestions(conn)
    }
    drafts = {draft.cluster_id: draft for draft in await load_issue_drafts(conn)}
    pairs = await load_embedding_pairs(
        conn,
        provider=PROVIDER,
        model=settings.gemini_embedding_model,
        model_version=settings.gemini_embedding_version,
    )
    return _ReportInputs(edges, embedded, briefs, history, issues, pairs, suggestions, drafts)


def _issue_draft(
    cluster: StoredCluster,
    by_id: dict[UUID, DedupeItem],
    canonical: CanonicalIssue,
    brief: StoredBrief | None,
) -> IssueDraft:
    rows = [by_id[member_id] for member_id in cluster.member_ids if member_id in by_id]
    return suggest_issue_update(
        number=canonical.number,
        theme_name=cluster.name,
        theme_summary=cluster.summary,
        brief_problem=None if brief is None else brief.problem,
        brief_evidence=None if brief is None else brief.evidence_summary,
        reports=[row.title for row in rows if row.id != canonical.id and row.source == "csv"],
        areas=[row.product_area for row in rows],
    )


def _public_suggestion(
    draft: IssueDraft, stored: StoredSuggestion | None, issue_id: UUID
) -> IssueSuggestion:
    saved = (
        stored is not None
        and stored.feedback_item_id == issue_id
        and stored.comment == draft.comment
        and stored.labels == draft.labels
    )
    return IssueSuggestion(comment=draft.comment, labels=list(draft.labels), saved=saved)


def _canonical_issue(
    member_ids: tuple[UUID, ...],
    *,
    issues: dict[UUID, IssueSignal],
    pairs: list[tuple[UUID, UUID, float]],
    now: datetime,
    duplicate_threshold: float,
) -> tuple[CanonicalIssue | None, list[DuplicateWarning]]:
    pick, warnings = recommend_canonical(
        member_ids,
        issues,
        pairs,
        now=now,
        duplicate_threshold=duplicate_threshold,
    )
    canonical = None
    if pick is not None:
        state: Literal["open", "closed"] = "open" if pick.issue.state == "open" else "closed"
        canonical = CanonicalIssue(
            id=pick.issue.id,
            number=pick.issue.number,
            title=pick.issue.title,
            html_url=pick.issue.html_url,
            state=state,
            comment_count=pick.issue.comment_count,
            reactions_total=pick.issue.reactions_total,
            coverage=pick.coverage,
            recent=pick.recent,
            recent_days=pick.recent_days,
            score=pick.score,
        )
    return canonical, [
        DuplicateWarning(
            id=warning.issue.id,
            number=warning.issue.number,
            title=warning.issue.title,
            html_url=warning.issue.html_url,
            similarity=warning.similarity,
            in_theme=warning.in_theme,
        )
        for warning in warnings
    ]


def _public_brief(
    stored: StoredBrief | None, member_ids: set[UUID], versions: list[StoredVersion]
) -> ClusterBrief | None:
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
        version=stored.version,
        source=stored.source,
        history=[
            BriefVersion(
                version=item.version,
                source=item.source,
                problem=item.problem,
                created_at=item.created_at,
            )
            for item in versions
            if item.version != stored.version
        ],
    )


def _member(item: DedupeItem) -> ClusterMember:
    source: Literal["github_issue", "csv"] = "csv" if item.source == "csv" else "github_issue"
    return ClusterMember(id=item.id, source=source, external_id=item.external_id, title=item.title)


def _evaluation(scored: tuple[int, int, float]) -> ClusterEvaluation:
    labeled, gathered, mean_cohesion = scored
    return ClusterEvaluation(labeled=labeled, gathered=gathered, mean_cohesion=mean_cohesion)

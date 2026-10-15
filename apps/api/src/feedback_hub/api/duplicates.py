from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from feedback_hub.api.me import default_workspace_name
from feedback_hub.auth import CurrentUser
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.duplicates import (
    DedupeItem,
    insert_dedupe_run,
    latest_dedupe_run,
    load_duplicate_edges,
    load_embedding_pairs,
    load_feedback_items,
    replace_duplicate_edges,
)
from feedback_hub.db.engine import Database, get_database
from feedback_hub.db.products import get_product
from feedback_hub.db.workspaces import ensure_workspace, record_audit_event
from feedback_hub.feedback.duplicates import (
    LABELED_PAIRS,
    DuplicateLink,
    HashableFeedback,
    LabelScore,
    assemble_groups,
    evaluate_links,
    links_for_feedback,
)
from feedback_hub.observability import observe_duplicate_rate, trace_operation

router = APIRouter(tags=["duplicates"])

PROVIDER = "gemini"
GROUP_LIMIT = 30
NO_PRODUCT = "No product registered yet."


class DuplicateMember(BaseModel):
    id: UUID
    source: Literal["github_issue", "csv"]
    external_id: str
    title: str


class DuplicateGroup(BaseModel):
    kind: Literal["exact", "semantic", "mixed"]
    members: list[DuplicateMember]


class DuplicateEvaluation(BaseModel):
    labeled: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None


class DuplicateReport(BaseModel):
    ran: bool
    exact_edges: int
    semantic_edges: int
    group_count: int
    threshold: float
    neighbor_count: int
    groups: list[DuplicateGroup]
    evaluation: DuplicateEvaluation | None

    @classmethod
    def idle(cls, settings: Settings) -> "DuplicateReport":
        return cls(
            ran=False,
            exact_edges=0,
            semantic_edges=0,
            group_count=0,
            threshold=settings.duplicate_similarity_threshold,
            neighbor_count=settings.duplicate_neighbor_count,
            groups=[],
            evaluation=None,
        )


@router.post("/v1/feedback/duplicates", response_model=DuplicateReport)
async def find_duplicates(
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DuplicateReport:
    """Rebuild duplicate links for the registered product. Original rows stay put.

    The comparison is SQL on the stored vectors, so it finishes inside the request.
    """
    with trace_operation("analysis_run") as span:
        span["operation"] = "duplicates"
        report = await _rebuild_duplicates(user, database, settings)
        span["records"] = report.exact_edges + report.semantic_edges
        span["clusters"] = report.group_count
    return report


async def _rebuild_duplicates(
    user: CurrentUser,
    database: Database,
    settings: Settings,
) -> DuplicateReport:
    async with database.user_transaction(user) as conn:
        workspace = await ensure_workspace(conn, default_workspace_name(user.email))
        product = await get_product(conn)
        if product is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_PRODUCT)
        items = await load_feedback_items(conn)
        pairs = await load_embedding_pairs(
            conn,
            provider=PROVIDER,
            model=settings.gemini_embedding_model,
            model_version=settings.gemini_embedding_version,
        )
        links = links_for_feedback(
            [_hashable(item) for item in items],
            [(str(left), str(right), score) for left, right, score in pairs],
            threshold=settings.duplicate_similarity_threshold,
            neighbors=settings.duplicate_neighbor_count,
        )
        await replace_duplicate_edges(
            conn,
            tenant_id=workspace.tenant_id,
            product_id=product.id,
            provider=PROVIDER,
            model=settings.gemini_embedding_model,
            model_version=settings.gemini_embedding_version,
            links=links,
        )
        report = _report(
            items,
            links,
            threshold=settings.duplicate_similarity_threshold,
            neighbor_count=settings.duplicate_neighbor_count,
        )
        await insert_dedupe_run(
            conn,
            tenant_id=workspace.tenant_id,
            product_id=product.id,
            exact_count=report.exact_edges,
            semantic_count=report.semantic_edges,
            group_count=report.group_count,
            threshold=settings.duplicate_similarity_threshold,
            neighbor_count=settings.duplicate_neighbor_count,
            provider=PROVIDER,
            model=settings.gemini_embedding_model,
            model_version=settings.gemini_embedding_version,
        )
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="dedupe.completed",
            target_type="product",
            target_id=str(product.id),
            metadata={
                "exact_edges": report.exact_edges,
                "semantic_edges": report.semantic_edges,
                "group_count": report.group_count,
            },
        )
    observe_duplicate_rate("exact", edges=report.exact_edges, items=len(items))
    observe_duplicate_rate("semantic", edges=report.semantic_edges, items=len(items))
    return report


@router.get("/v1/feedback/duplicates", response_model=DuplicateReport)
async def read_duplicates(
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DuplicateReport:
    async with database.user_transaction(user) as conn:
        await ensure_workspace(conn, default_workspace_name(user.email))
        run = await latest_dedupe_run(conn)
        if await get_product(conn) is None or run is None:
            return DuplicateReport.idle(settings)
        items = await load_feedback_items(conn)
        edges = await load_duplicate_edges(conn)
    links = [
        DuplicateLink(str(edge.left_item_id), str(edge.right_item_id), edge.kind, edge.score)
        for edge in edges
    ]
    return _report(items, links, threshold=run.threshold, neighbor_count=run.neighbor_count)


def _hashable(item: DedupeItem) -> HashableFeedback:
    return HashableFeedback(
        str(item.id),
        item.source,
        item.title,
        item.body,
        item.language,
        item.content_hash,
    )


def _report(
    items: list[DedupeItem],
    links: list[DuplicateLink],
    *,
    threshold: float,
    neighbor_count: int,
) -> DuplicateReport:
    by_id = {str(item.id): item for item in items}
    components = assemble_groups(links)
    groups: list[DuplicateGroup] = []
    for component in components[:GROUP_LIMIT]:
        members = [_member(by_id[item_id]) for item_id in component.member_ids if item_id in by_id]
        members.sort(key=lambda member: member.title.casefold())
        if len(members) < 2:
            continue
        groups.append(DuplicateGroup(kind=_kind(component.kind), members=members))
    evaluation = evaluate_links(
        links,
        [(str(item.id), item.external_id) for item in items],
        list(LABELED_PAIRS),
    )
    return DuplicateReport(
        ran=True,
        exact_edges=sum(link.kind == "exact" for link in links),
        semantic_edges=sum(link.kind == "semantic" for link in links),
        group_count=len(components),
        threshold=threshold,
        neighbor_count=neighbor_count,
        groups=groups,
        evaluation=None if evaluation is None else _evaluation(evaluation),
    )


def _member(item: DedupeItem) -> DuplicateMember:
    return DuplicateMember(
        id=item.id,
        source=_source(item.source),
        external_id=item.external_id,
        title=item.title,
    )


def _source(source: str) -> Literal["github_issue", "csv"]:
    if source == "csv":
        return "csv"
    return "github_issue"


def _kind(kind: str) -> Literal["exact", "semantic", "mixed"]:
    if kind == "exact":
        return "exact"
    if kind == "semantic":
        return "semantic"
    return "mixed"


def _evaluation(score: LabelScore) -> DuplicateEvaluation:
    return DuplicateEvaluation(
        labeled=score.labeled,
        true_positives=score.true_positives,
        false_positives=score.false_positives,
        false_negatives=score.false_negatives,
        precision=score.precision,
        recall=score.recall,
    )

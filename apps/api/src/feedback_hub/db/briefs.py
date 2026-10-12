import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from feedback_hub.feedback.theme_briefs import ThemeBrief

BriefSource = Literal["generated", "edited"]


@dataclass(frozen=True, slots=True)
class StoredBrief:
    cluster_id: UUID
    problem: str
    impact: str
    evidence_summary: str
    non_goals: str
    acceptance_criteria: str
    open_questions: str
    evidence_ids: tuple[UUID, ...]
    version: int
    source: BriefSource


@dataclass(frozen=True, slots=True)
class StoredVersion:
    cluster_id: UUID
    version: int
    source: BriefSource
    problem: str
    created_at: datetime


async def load_product_briefs(conn: AsyncConnection) -> list[StoredBrief]:
    rows = (
        await conn.execute(
            text(
                "select cluster_id, problem, impact, evidence_summary, non_goals, "
                "acceptance_criteria, open_questions, evidence_ids, version_number, source "
                "from public.product_briefs"
            )
        )
    ).all()
    return [_brief(dict(row._mapping)) for row in rows]


async def load_brief_versions(conn: AsyncConnection) -> list[StoredVersion]:
    rows = (
        await conn.execute(
            text(
                "select cluster_id, version_number, source, problem, created_at "
                "from public.product_brief_versions order by version_number"
            )
        )
    ).all()
    return [_version(dict(row._mapping)) for row in rows]


async def save_product_brief(
    conn: AsyncConnection,
    *,
    cluster_id: UUID,
    tenant_id: UUID,
    product_id: UUID,
    brief: ThemeBrief,
    source: BriefSource,
    provider: str | None,
    model: str | None,
) -> None:
    current = (
        await conn.execute(
            text(
                "select coalesce(max(version_number), 0) as version_number "
                "from public.product_brief_versions where cluster_id = :cluster_id"
            ),
            {"cluster_id": cluster_id},
        )
    ).first()
    previous = 0 if current is None else int(current._mapping["version_number"])
    created_at = datetime.now(UTC)
    payload = {
        "cluster_id": cluster_id,
        "tenant_id": tenant_id,
        "product_id": product_id,
        "version_number": previous + 1,
        "source": source,
        "problem": brief.problem,
        "impact": brief.impact,
        "evidence_summary": brief.evidence_summary,
        "non_goals": brief.non_goals,
        "acceptance_criteria": brief.acceptance_criteria,
        "open_questions": brief.open_questions,
        "evidence_ids": json.dumps([str(item_id) for item_id in brief.evidence_ids]),
        "provider": provider,
        "model": model,
        "created_at": created_at,
    }
    await conn.execute(
        text(
            "insert into public.product_brief_versions ("
            "cluster_id, tenant_id, product_id, version_number, source, problem, impact, "
            "evidence_summary, non_goals, acceptance_criteria, open_questions, evidence_ids, "
            "provider, model, created_at"
            ") values ("
            ":cluster_id, :tenant_id, :product_id, :version_number, :source, :problem, :impact, "
            ":evidence_summary, :non_goals, :acceptance_criteria, :open_questions, "
            "cast(:evidence_ids as jsonb), :provider, :model, :created_at)"
        ),
        payload,
    )
    await conn.execute(
        text(
            "insert into public.product_briefs ("
            "cluster_id, tenant_id, product_id, problem, impact, evidence_summary, "
            "non_goals, acceptance_criteria, open_questions, evidence_ids, provider, model, "
            "version_number, source, created_at"
            ") values ("
            ":cluster_id, :tenant_id, :product_id, :problem, :impact, :evidence_summary, "
            ":non_goals, :acceptance_criteria, :open_questions, "
            "cast(:evidence_ids as jsonb), :provider, :model, :version_number, :source, "
            ":created_at"
            ") on conflict (cluster_id) do update set "
            "problem = excluded.problem, impact = excluded.impact, "
            "evidence_summary = excluded.evidence_summary, non_goals = excluded.non_goals, "
            "acceptance_criteria = excluded.acceptance_criteria, "
            "open_questions = excluded.open_questions, evidence_ids = excluded.evidence_ids, "
            "provider = excluded.provider, model = excluded.model, "
            "version_number = excluded.version_number, source = excluded.source, "
            "created_at = excluded.created_at"
        ),
        payload,
    )


def _brief(mapping: Mapping[str, Any]) -> StoredBrief:
    row = mapping
    return StoredBrief(
        cluster_id=row["cluster_id"],
        problem=row["problem"],
        impact=row["impact"],
        evidence_summary=row["evidence_summary"],
        non_goals=row["non_goals"],
        acceptance_criteria=row["acceptance_criteria"],
        open_questions=row["open_questions"],
        evidence_ids=_ids(row["evidence_ids"]),
        version=int(row["version_number"]),
        source=_source(row["source"]),
    )


def _version(mapping: Mapping[str, Any]) -> StoredVersion:
    created_at = mapping["created_at"]
    if not isinstance(created_at, datetime):
        created_at = datetime.now(UTC)
    return StoredVersion(
        cluster_id=mapping["cluster_id"],
        version=int(mapping["version_number"]),
        source=_source(mapping["source"]),
        problem=mapping["problem"],
        created_at=created_at,
    )


def _source(value: object) -> BriefSource:
    return "edited" if value == "edited" else "generated"


def _ids(value: object) -> tuple[UUID, ...]:
    if isinstance(value, str):
        loaded: object = json.loads(value)
    else:
        loaded = value
    if not isinstance(loaded, list):
        return ()
    parsed: list[UUID] = []
    for item in loaded:
        if isinstance(item, UUID):
            parsed.append(item)
        elif isinstance(item, str):
            parsed.append(UUID(item))
    return tuple(parsed)

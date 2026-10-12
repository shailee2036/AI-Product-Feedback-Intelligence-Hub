import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from feedback_hub.feedback.theme_briefs import ThemeBrief


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


async def load_product_briefs(conn: AsyncConnection) -> list[StoredBrief]:
    rows = (
        await conn.execute(
            text(
                "select cluster_id, problem, impact, evidence_summary, non_goals, "
                "acceptance_criteria, open_questions, evidence_ids "
                "from public.product_briefs"
            )
        )
    ).all()
    return [_brief(dict(row._mapping)) for row in rows]


async def save_product_brief(
    conn: AsyncConnection,
    *,
    cluster_id: UUID,
    tenant_id: UUID,
    product_id: UUID,
    brief: ThemeBrief,
    provider: str,
    model: str,
) -> None:
    await conn.execute(
        text(
            "insert into public.product_briefs ("
            "cluster_id, tenant_id, product_id, problem, impact, evidence_summary, "
            "non_goals, acceptance_criteria, open_questions, evidence_ids, provider, model"
            ") values ("
            ":cluster_id, :tenant_id, :product_id, :problem, :impact, :evidence_summary, "
            ":non_goals, :acceptance_criteria, :open_questions, "
            "cast(:evidence_ids as jsonb), :provider, :model"
            ") on conflict (cluster_id) do update set "
            "problem = excluded.problem, impact = excluded.impact, "
            "evidence_summary = excluded.evidence_summary, non_goals = excluded.non_goals, "
            "acceptance_criteria = excluded.acceptance_criteria, "
            "open_questions = excluded.open_questions, evidence_ids = excluded.evidence_ids, "
            "provider = excluded.provider, model = excluded.model, created_at = now()"
        ),
        {
            "cluster_id": cluster_id,
            "tenant_id": tenant_id,
            "product_id": product_id,
            "problem": brief.problem,
            "impact": brief.impact,
            "evidence_summary": brief.evidence_summary,
            "non_goals": brief.non_goals,
            "acceptance_criteria": brief.acceptance_criteria,
            "open_questions": brief.open_questions,
            "evidence_ids": json.dumps([str(item_id) for item_id in brief.evidence_ids]),
            "provider": provider,
            "model": model,
        },
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
    )


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

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

RECENT_DAYS = 90
SIZE_FULL = 10


@dataclass(frozen=True, slots=True)
class ScoreFact:
    source: str
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class ThemeFactors:
    member_count: int
    recent_count: int
    recent_days: int
    source_count: int
    unique_count: int
    embedded_count: int
    named: bool
    score: float


def score_cluster(
    member_ids: tuple[UUID, ...],
    *,
    facts: dict[UUID, ScoreFact],
    embedded: set[UUID],
    edges: list[tuple[UUID, UUID]],
    named: bool,
    now: datetime,
    recent_days: int = RECENT_DAYS,
) -> ThemeFactors:
    """Average five visible factors. The number is not chosen by a model.

    Size reaches 1 at 10 rows. Recent is the share created inside the window.
    Two sources score 1 and one source scores 0.5. Unique is the share left
    after duplicate links inside the theme are counted once. Completeness
    averages a stored name with the share of rows that have an embedding.
    """
    members = [member_id for member_id in member_ids if member_id in facts]
    count = len(members)
    if count == 0:
        return ThemeFactors(0, 0, recent_days, 0, 0, 0, named, 0.0)
    cutoff = now - timedelta(days=recent_days)
    recent = sum(1 for member_id in members if _is_recent(facts[member_id].created_at, cutoff))
    sources = {facts[member_id].source for member_id in members}
    unique = _unique_count(members, edges)
    embedded_count = sum(1 for member_id in members if member_id in embedded)
    size_part = min(count / SIZE_FULL, 1.0)
    recent_part = recent / count
    source_part = 1.0 if len(sources) >= 2 else 0.5
    unique_part = unique / count
    complete_part = ((1.0 if named else 0.0) + (embedded_count / count)) / 2
    score = round((size_part + recent_part + source_part + unique_part + complete_part) / 5, 3)
    return ThemeFactors(
        member_count=count,
        recent_count=recent,
        recent_days=recent_days,
        source_count=len(sources),
        unique_count=unique,
        embedded_count=embedded_count,
        named=named,
        score=score,
    )


def _is_recent(created_at: datetime | None, cutoff: datetime) -> bool:
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=cutoff.tzinfo)
    return created_at >= cutoff


def _unique_count(members: list[UUID], edges: list[tuple[UUID, UUID]]) -> int:
    parent = {member_id: member_id for member_id in members}
    present = set(members)

    def find(item: UUID) -> UUID:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for left, right in edges:
        if left in present and right in present and left != right:
            parent[find(left)] = find(right)
    return len({find(member_id) for member_id in members})

"""Recommend one imported GitHub issue for a theme. GitHub is not written."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

DISCUSSION_FULL = 10
REACTION_FULL = 10
RECENT_DAYS = 90
WARNING_LIMIT = 5


@dataclass(frozen=True, slots=True)
class IssueSignal:
    id: UUID
    number: int
    title: str
    state: str
    html_url: str
    comment_count: int
    reactions_total: int
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CanonicalPick:
    issue: IssueSignal
    coverage: float
    recent: bool
    recent_days: int
    score: float


@dataclass(frozen=True, slots=True)
class IssueWarning:
    issue: IssueSignal
    similarity: float
    in_theme: bool


def recommend_canonical(
    member_ids: tuple[UUID, ...],
    issues: dict[UUID, IssueSignal],
    pairs: list[tuple[UUID, UUID, float]],
    *,
    now: datetime,
    duplicate_threshold: float,
    recent_days: int = RECENT_DAYS,
) -> tuple[CanonicalPick | None, tuple[IssueWarning, ...]]:
    """Pick the strongest issue already in the theme and warn about open duplicates.

    Open issues sort ahead of closed ones. The displayed score then averages
    coverage, comments, reactions, and recency. Other open issues in the theme
    are warnings, as are open issues outside it at or above the duplicate threshold.
    """
    if not member_ids:
        return None, ()
    members = set(member_ids)
    index = _pair_index(pairs)
    ranked = [
        _pick(issue, member_ids, index, now=now, recent_days=recent_days)
        for issue in issues.values()
        if issue.id in members and _usable(issue)
    ]
    ranked.sort(key=lambda pick: (pick.issue.state != "open", -pick.score, pick.issue.number))
    chosen = ranked[0] if ranked else None
    warnings = _warnings(
        chosen,
        members,
        issues,
        index,
        duplicate_threshold=duplicate_threshold,
    )
    return chosen, tuple(warnings[:WARNING_LIMIT])


def _usable(issue: IssueSignal) -> bool:
    return (
        issue.number > 0
        and issue.state in {"open", "closed"}
        and issue.html_url.startswith("https://github.com/")
    )


def _pick(
    issue: IssueSignal,
    member_ids: tuple[UUID, ...],
    index: dict[tuple[UUID, UUID], float],
    *,
    now: datetime,
    recent_days: int,
) -> CanonicalPick:
    others = [member_id for member_id in member_ids if member_id != issue.id]
    coverage = 0.0 if not others else round(_mean(issue.id, others, index), 3)
    cutoff = now - timedelta(days=recent_days)
    recent = _is_recent(issue.updated_at, cutoff)
    return CanonicalPick(
        issue=issue,
        coverage=coverage,
        recent=recent,
        recent_days=recent_days,
        score=_score(issue, coverage, recent),
    )


def _score(issue: IssueSignal, coverage: float, recent: bool) -> float:
    parts = (
        1.0 if issue.state == "open" else 0.0,
        coverage,
        min(max(issue.comment_count, 0) / DISCUSSION_FULL, 1.0),
        min(max(issue.reactions_total, 0) / REACTION_FULL, 1.0),
        1.0 if recent else 0.0,
    )
    return round(sum(parts) / len(parts), 3)


def _warnings(
    chosen: CanonicalPick | None,
    members: set[UUID],
    issues: dict[UUID, IssueSignal],
    index: dict[tuple[UUID, UUID], float],
    *,
    duplicate_threshold: float,
) -> list[IssueWarning]:
    chosen_id = None if chosen is None else chosen.issue.id
    warnings: list[IssueWarning] = []
    for issue in issues.values():
        if issue.id == chosen_id or issue.state != "open" or not _usable(issue):
            continue
        if issue.id in members:
            similarity = 0.0 if chosen is None else _lookup(index, issue.id, chosen.issue.id)
            warnings.append(IssueWarning(issue, round(similarity, 3), True))
            continue
        similarity = _best(issue.id, members, index)
        if similarity >= duplicate_threshold:
            warnings.append(IssueWarning(issue, round(similarity, 3), False))
    warnings.sort(
        key=lambda warning: (not warning.in_theme, -warning.similarity, warning.issue.number)
    )
    return warnings


def _pair_index(pairs: list[tuple[UUID, UUID, float]]) -> dict[tuple[UUID, UUID], float]:
    index: dict[tuple[UUID, UUID], float] = {}
    for left, right, score in pairs:
        if left == right:
            continue
        key = (left, right) if left < right else (right, left)
        current = index.get(key)
        if current is None or score > current:
            index[key] = score
    return index


def _lookup(index: dict[tuple[UUID, UUID], float], left: UUID, right: UUID) -> float:
    if left == right:
        return 0.0
    key = (left, right) if left < right else (right, left)
    return index.get(key, 0.0)


def _mean(issue_id: UUID, others: list[UUID], index: dict[tuple[UUID, UUID], float]) -> float:
    return sum(_lookup(index, issue_id, other) for other in others) / len(others)


def _best(issue_id: UUID, members: set[UUID], index: dict[tuple[UUID, UUID], float]) -> float:
    return max((_lookup(index, issue_id, member_id) for member_id in members), default=0.0)


def _is_recent(updated_at: datetime | None, cutoff: datetime) -> bool:
    if updated_at is None:
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=cutoff.tzinfo)
    return updated_at >= cutoff

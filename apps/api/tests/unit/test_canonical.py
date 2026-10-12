from datetime import UTC, datetime
from uuid import uuid4

from feedback_hub.feedback.canonical import IssueSignal, recommend_canonical

NOW = datetime(2026, 10, 11, tzinfo=UTC)


def _issue(
    number: int,
    *,
    state: str = "open",
    comments: int = 0,
    reactions: int = 0,
    updated_at: datetime | None = None,
    html_url: str | None = None,
) -> IssueSignal:
    return IssueSignal(
        id=uuid4(),
        number=number,
        title=f"Issue {number}",
        state=state,
        html_url=html_url or f"https://github.com/appwrite/appwrite/issues/{number}",
        comment_count=comments,
        reactions_total=reactions,
        updated_at=updated_at,
    )


def test_open_issue_ranks_ahead_of_a_busier_closed_issue() -> None:
    closed = _issue(4, state="closed", comments=40, reactions=20, updated_at=NOW)
    opened = _issue(8, comments=1, updated_at=NOW)
    members = (closed.id, opened.id, uuid4())
    pairs = [(closed.id, members[2], 0.99), (opened.id, members[2], 0.4)]

    pick, warnings = recommend_canonical(
        members, {closed.id: closed, opened.id: opened}, pairs, now=NOW, duplicate_threshold=0.86
    )

    assert pick is not None
    assert pick.issue.number == 8
    assert pick.recent is True
    assert warnings == ()


def test_lower_issue_number_wins_a_score_tie() -> None:
    older = _issue(3, comments=2, reactions=2, updated_at=NOW)
    newer = _issue(11, comments=2, reactions=2, updated_at=NOW)
    row = uuid4()
    pairs = [(older.id, row, 0.9), (newer.id, row, 0.9)]

    pick, _warnings = recommend_canonical(
        (older.id, newer.id, row),
        {older.id: older, newer.id: newer},
        pairs,
        now=NOW,
        duplicate_threshold=0.86,
    )

    assert pick is not None
    assert pick.issue.number == 3
    assert pick.coverage == 0.45
    assert pick.score == 0.57


def test_in_theme_open_issue_is_a_duplicate_warning() -> None:
    canonical = _issue(7, comments=4, reactions=2, updated_at=NOW)
    other = _issue(9, comments=1)
    row = uuid4()
    pairs = [(canonical.id, row, 0.9), (canonical.id, other.id, 0.91)]

    pick, warnings = recommend_canonical(
        (canonical.id, other.id, row),
        {canonical.id: canonical, other.id: other},
        pairs,
        now=NOW,
        duplicate_threshold=0.86,
    )

    assert pick is not None
    assert pick.issue.number == 7
    assert pick.coverage == 0.905
    assert pick.score == 0.701
    assert len(warnings) == 1
    assert warnings[0].issue.number == 9
    assert warnings[0].in_theme is True
    assert warnings[0].similarity == 0.91


def test_similar_open_issue_outside_the_theme_is_a_warning() -> None:
    canonical = _issue(7, updated_at=NOW)
    close = _issue(12)
    far = _issue(13)
    row = uuid4()
    pairs = [(canonical.id, row, 0.9), (close.id, row, 0.86), (far.id, row, 0.85)]

    _pick, warnings = recommend_canonical(
        (canonical.id, row),
        {canonical.id: canonical, close.id: close, far.id: far},
        pairs,
        now=NOW,
        duplicate_threshold=0.86,
    )

    assert [warning.issue.number for warning in warnings] == [12]
    assert warnings[0].in_theme is False
    assert warnings[0].similarity == 0.86


def test_theme_without_a_github_issue_stays_empty() -> None:
    row = uuid4()
    skipped = _issue(2, html_url="http://example.test/2")

    pick, warnings = recommend_canonical(
        (row, skipped.id), {skipped.id: skipped}, [], now=NOW, duplicate_threshold=0.86
    )

    assert pick is None
    assert warnings == ()


def test_naive_timestamp_counts_as_recent() -> None:
    issue = _issue(5, updated_at=datetime(2026, 10, 1))

    pick, _warnings = recommend_canonical(
        (issue.id,), {issue.id: issue}, [], now=NOW, duplicate_threshold=0.86
    )

    assert pick is not None
    assert pick.recent is True
    assert pick.coverage == 0.0

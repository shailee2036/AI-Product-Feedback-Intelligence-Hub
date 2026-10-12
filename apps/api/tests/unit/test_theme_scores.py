from datetime import UTC, datetime, timedelta
from uuid import uuid4

from feedback_hub.feedback.theme_scores import ScoreFact, score_cluster


def test_score_shows_recent_rows_sources_and_duplicates() -> None:
    now = datetime(2026, 10, 11, tzinfo=UTC)
    first, second, third = uuid4(), uuid4(), uuid4()
    facts = {
        first: ScoreFact("csv", now - timedelta(days=1)),
        second: ScoreFact("github_issue", now - timedelta(days=200)),
        third: ScoreFact("csv", now - timedelta(days=10)),
    }

    factors = score_cluster(
        (first, second, third),
        facts=facts,
        embedded={first, second},
        edges=[(first, third), (first, uuid4())],
        named=True,
        now=now,
    )

    assert factors.member_count == 3
    assert factors.recent_count == 2
    assert factors.recent_days == 90
    assert factors.source_count == 2
    assert factors.unique_count == 2
    assert factors.embedded_count == 2
    assert factors.named is True
    size_part = 0.3
    recent_part = 2 / 3
    complete_part = (1 + (2 / 3)) / 2
    expected = round((size_part + recent_part + 1 + recent_part + complete_part) / 5, 3)
    assert factors.score == expected


def test_score_of_an_empty_theme_is_zero() -> None:
    factors = score_cluster(
        (),
        facts={},
        embedded=set(),
        edges=[],
        named=False,
        now=datetime(2026, 10, 11, tzinfo=UTC),
    )

    assert factors.member_count == 0
    assert factors.score == 0.0


def test_score_treats_a_naive_timestamp_as_recent() -> None:
    now = datetime(2026, 10, 11, tzinfo=UTC)
    item_id = uuid4()

    factors = score_cluster(
        (item_id,),
        facts={item_id: ScoreFact("csv", datetime(2026, 10, 10))},
        embedded=set(),
        edges=[],
        named=False,
        now=now,
    )

    assert factors.recent_count == 1


def test_score_treats_a_missing_date_as_not_recent() -> None:
    now = datetime(2026, 10, 11, tzinfo=UTC)
    item_id = uuid4()

    factors = score_cluster(
        (item_id,),
        facts={item_id: ScoreFact("csv", None)},
        embedded=set(),
        edges=[],
        named=False,
        now=now,
    )

    assert factors.recent_count == 0
    assert factors.source_count == 1
    assert factors.unique_count == 1
    assert factors.score == round((0.1 + 0 + 0.5 + 1 + 0) / 5, 3)

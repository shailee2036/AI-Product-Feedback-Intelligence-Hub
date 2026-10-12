import csv
from pathlib import Path

from feedback_hub.feedback.duplicates import (
    LABELED_PAIRS,
    DuplicateLink,
    HashableFeedback,
    assemble_groups,
    build_links,
    content_digest,
    evaluate_links,
    exact_links,
    links_for_feedback,
    score_labels,
    semantic_links,
)

SEED_CSV = Path(__file__).resolve().parents[4] / "seed-data" / "appwrite-customer-feedback.csv"


def test_exact_links_pair_every_member_of_a_hash() -> None:
    links = exact_links([("b", "hash-1"), ("a", "hash-1"), ("c", "hash-1"), ("d", "hash-2")])

    assert [(link.left_id, link.right_id) for link in links] == [("a", "b"), ("a", "c"), ("b", "c")]
    assert {link.kind for link in links} == {"exact"}


def test_semantic_links_require_a_mutual_neighbor_above_the_threshold() -> None:
    nearest = {
        "a": [("b", 0.91), ("c", 0.70)],
        "b": [("a", 0.91), ("c", 0.89)],
        "c": [("b", 0.89), ("a", 0.70)],
    }

    links = semantic_links(nearest, threshold=0.86, neighbors=2, blocked={("a", "b")})

    assert [(link.left_id, link.right_id, round(link.score, 2)) for link in links] == [
        ("b", "c", 0.89)
    ]


def test_build_links_keeps_exact_text_out_of_the_semantic_edges() -> None:
    links = build_links(
        [("a", "same"), ("b", "same"), ("c", "other"), ("d", "else")],
        [("a", "b", 0.99), ("c", "d", 0.9), ("a", "c", 0.2)],
        threshold=0.86,
        neighbors=2,
    )

    assert [(link.left_id, link.right_id, link.kind) for link in links] == [
        ("a", "b", "exact"),
        ("c", "d", "semantic"),
    ]


def test_connected_groups_keep_separate_pairs() -> None:
    links = exact_links([("a", "same"), ("b", "same")]) + semantic_links(
        {"c": [("d", 0.9)], "d": [("c", 0.9)]},
        threshold=0.86,
        neighbors=1,
        blocked=set(),
    )

    assert len(assemble_groups(links)) == 2


def test_assemble_groups_marks_a_shared_item_as_mixed() -> None:
    groups = assemble_groups(
        [
            DuplicateLink("a", "b", "exact", 1),
            DuplicateLink("b", "c", "semantic", 0.9),
        ]
    )

    assert len(groups) == 1
    assert groups[0].kind == "mixed"
    assert groups[0].member_ids == ["a", "b", "c"]


def test_content_digest_skips_short_text_and_keeps_a_stored_hash() -> None:
    assert content_digest(None, "too short", "en") is None
    assert content_digest("a" * 64, "too short", "en") == "a" * 64


def test_links_for_feedback_hash_identical_csv_rows() -> None:
    body = "The callback checklist is hard to follow for production."
    items = [
        HashableFeedback("b", "csv", "One", body, "en", None),
        HashableFeedback("a", "csv", "Two", body, "en", None),
        HashableFeedback("c", "csv", "Short", "nope", "en", None),
    ]

    links = links_for_feedback(items, [], threshold=0.86, neighbors=2)

    assert [(link.left_id, link.right_id, link.kind) for link in links] == [("a", "b", "exact")]


def test_score_labels_ignores_pairs_that_are_not_in_the_product() -> None:
    links = exact_links([("a", "same"), ("b", "same")])
    labels = [("a", "b", True), ("a", "c", False), ("missing", "b", True)]

    score = score_labels(links, labels, present={"a", "b", "c"})

    assert score.labeled == 2
    assert score.true_positives == 1
    assert score.false_positives == 0
    assert score.false_negatives == 0
    assert score.precision == 1
    assert score.recall == 1


def test_evaluate_links_uses_external_ids() -> None:
    score = evaluate_links(
        [DuplicateLink("id-1", "id-2", "exact", 1)],
        [("id-1", "AW-SYN-001"), ("id-2", "AW-SYN-002"), ("id-6", "AW-SYN-006")],
        list(LABELED_PAIRS),
    )

    assert score is not None
    assert score.true_positives == 1
    assert score.false_positives == 0
    assert score.false_negatives == 0


def test_starter_labels_name_rows_in_the_seed_csv() -> None:
    with SEED_CSV.open(encoding="utf-8", newline="") as handle:
        ids = {row["feedback_id"] for row in csv.DictReader(handle)}

    positives = [pair for pair in LABELED_PAIRS if pair[2]]
    negatives = [pair for pair in LABELED_PAIRS if not pair[2]]
    assert len(positives) >= 3
    assert len(negatives) >= 3
    for left, right, _duplicate in LABELED_PAIRS:
        assert left in ids
        assert right in ids
        assert left != right

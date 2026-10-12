import csv
from pathlib import Path

from feedback_hub.feedback.clusters import LABELED_THEMES, score_themes, theme_groups

SEED_CSV = Path(__file__).resolve().parents[4] / "seed-data" / "appwrite-customer-feedback.csv"


def test_theme_groups_keep_a_mutual_triangle_and_drop_a_pair() -> None:
    groups = theme_groups(
        [
            ("a", "b", 0.9),
            ("b", "c", 0.9),
            ("a", "c", 0.9),
            ("d", "e", 0.95),
            ("a", "d", 0.2),
        ],
        threshold=0.82,
        neighbors=3,
        minimum_size=3,
    )

    assert groups == [["a", "b", "c"]]


def test_theme_groups_ignore_a_one_way_neighbor() -> None:
    groups = theme_groups(
        [("a", "b", 0.95), ("b", "c", 0.99), ("a", "c", 0.4)],
        threshold=0.82,
        neighbors=1,
        minimum_size=2,
    )

    assert groups == [["b", "c"]]


def test_score_themes_counts_a_gathered_seed_theme() -> None:
    scored = score_themes(
        [["a", "b", "c"]],
        [("a", "AW-SYN-007"), ("b", "AW-SYN-008"), ("c", "AW-SYN-041")],
        list(LABELED_THEMES),
    )

    assert scored == (1, 1, 1.0)


def test_score_themes_skips_labels_that_are_not_in_the_product() -> None:
    assert score_themes([["a", "b"]], [("a", "other"), ("b", "else")], list(LABELED_THEMES)) is None


def test_starter_themes_name_rows_in_the_seed_csv() -> None:
    with SEED_CSV.open(encoding="utf-8", newline="") as handle:
        ids = {row["feedback_id"] for row in csv.DictReader(handle)}

    assert len(LABELED_THEMES) >= 4
    for _name, members in LABELED_THEMES:
        assert len(members) >= 2
        assert len(set(members)) == len(members)
        for external_id in members:
            assert external_id in ids

from feedback_hub.feedback.issue_suggestions import suggest_issue_update


def test_comment_uses_the_brief_and_redacts_csv_titles() -> None:
    draft = suggest_issue_update(
        number=7,
        theme_name="Import progress",
        theme_summary="People want progress.",
        brief_problem="Imports hide progress.",
        brief_evidence="Rows from ada@example.com never show a count.",
        reports=["Rejected rows for ada@example.com", "Import progress"],
        areas=["Import progress", "Import progress", None],
    )

    assert draft.comment.startswith("Related feedback for #7.")
    assert "Imports hide progress." in draft.comment
    assert "ada@example.com" not in draft.comment
    assert "[email]" in draft.comment
    assert draft.comment.count("Rejected rows") == 1
    assert draft.labels == ("import-progress",)


def test_comment_falls_back_to_the_theme_summary() -> None:
    draft = suggest_issue_update(
        number=4,
        theme_name="Uploads",
        theme_summary="Large uploads stop.",
        brief_problem=None,
        brief_evidence=None,
        reports=[],
        areas=["OAuth / SSO"],
    )

    assert "Large uploads stop." in draft.comment
    assert "Related reports:" not in draft.comment
    assert draft.labels == ("oauth-sso",)

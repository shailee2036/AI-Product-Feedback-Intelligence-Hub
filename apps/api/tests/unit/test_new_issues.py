from feedback_hub.feedback.new_issues import clean_issue_body, clean_issue_title, draft_new_issue


def test_draft_uses_the_brief_and_redacts_csv_titles() -> None:
    draft = draft_new_issue(
        theme_name="Import progress",
        theme_summary="People want progress.",
        brief_problem="Imports hide progress.",
        brief_impact="Customers cannot tell whether a job is stuck.",
        brief_evidence="Rows from ada@example.com never show a count.",
        reports=["Rejected rows for ada@example.com", "Import progress"],
        areas=["Import progress", None],
    )

    assert draft.title == "Import progress"
    assert "Imports hide progress." in draft.body
    assert "ada@example.com" not in draft.body
    assert "[email]" in draft.body
    assert "Related reports:" in draft.body
    assert draft.body.count("Rejected rows") == 1
    assert draft.labels == ("import-progress",)


def test_draft_falls_back_to_a_generic_title() -> None:
    draft = draft_new_issue(
        theme_name=None,
        theme_summary=None,
        brief_problem=None,
        brief_impact=None,
        brief_evidence=None,
        reports=[],
        areas=[],
    )

    assert draft.title == "Feedback theme"
    assert draft.body == "Feedback theme"
    assert draft.labels == ()


def test_edited_text_redacts_each_line() -> None:
    title = clean_issue_title("Write ada@example.com about progress")
    body = clean_issue_body("First line for ada@example.com\n\nSecond line")

    assert "ada@example.com" not in title
    assert "[email]" in title
    assert body == "First line for [email]\nSecond line"

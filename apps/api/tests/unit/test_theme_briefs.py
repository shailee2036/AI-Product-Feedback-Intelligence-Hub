from uuid import uuid4

import pytest

from feedback_hub.feedback.theme_briefs import (
    NO_CITATION,
    UNREADABLE,
    brief_prompt,
    brief_samples,
    parse_theme_brief,
)


def test_brief_prompt_uses_redacted_titles() -> None:
    item_id = uuid4()
    samples = brief_samples([(item_id, "Email ada@example.com about import progress")])

    prompt = brief_prompt("Import progress", samples)

    assert str(item_id) in prompt
    assert "ada@example.com" not in prompt
    assert "[email]" in prompt


def test_parse_drops_ids_that_are_not_in_the_theme() -> None:
    cited = uuid4()
    raw = (
        '{"problem":"Imports hide progress.","user_impact":"People wait.",'
        '"evidence_summary":"Rows ask for progress.","non_goals":"Leave the file format.",'
        '"acceptance_criteria":"Show progress.","open_questions":"Offer a download?",'
        f'"evidence_ids":["{cited}","{uuid4()}","not-an-id"]}}'
    )

    brief = parse_theme_brief(raw, {cited})

    assert brief.evidence_ids == (cited,)
    assert brief.impact == "People wait."


def test_parse_rejects_a_brief_with_no_theme_citation() -> None:
    raw = (
        '{"problem":"Imports hide progress.","user_impact":"People wait.",'
        '"evidence_summary":"Rows ask for progress.","non_goals":"Leave the file format.",'
        '"acceptance_criteria":"Show progress.","open_questions":"Offer a download?",'
        f'"evidence_ids":["{uuid4()}"]}}'
    )

    with pytest.raises(ValueError, match=NO_CITATION):
        parse_theme_brief(raw, {uuid4()})


def test_parse_rejects_a_missing_field() -> None:
    with pytest.raises(ValueError, match=UNREADABLE):
        parse_theme_brief('{"problem":"Imports hide progress."}', {uuid4()})

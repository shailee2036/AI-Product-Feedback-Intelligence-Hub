from datetime import UTC, datetime

from feedback_hub.github.client import GitHubError, GitHubRateLimitedError
from feedback_hub.github.issues import prepare_issue
from feedback_hub.importing.runner import _failure_message

CREATED = "2026-10-01T12:00:00Z"
UPDATED = "2026-10-11T15:30:00Z"


def issue(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "node_id": "I_kwDOABC",
        "number": 42,
        "title": "  Login   fails  ",
        "body": "Steps:\n\n1. Open the console",
        "state": "open",
        "html_url": "https://github.com/appwrite/appwrite/issues/42",
        "user": {"login": "ada", "node_id": "U_ada", "type": "User"},
        "labels": [{"name": "bug"}, {"name": "auth"}],
        "comments": 3,
        "reactions": {"total_count": 5},
        "created_at": CREATED,
        "updated_at": UPDATED,
    }
    payload.update(overrides)
    return payload


def test_prepare_issue_keeps_product_fields_and_hashes_the_author() -> None:
    prepared = prepare_issue(issue())

    assert prepared.skip_reason is None
    record = prepared.issue
    assert record is not None
    assert record.title == "Login fails"
    assert record.body_normalized == "Steps: 1. Open the console"
    assert record.labels == ["bug", "auth"]
    assert record.comment_count == 3
    assert record.reactions_total == 5
    assert record.author_hash is not None
    assert "ada" not in record.author_hash
    assert record.source_updated_at == datetime(2026, 10, 11, 15, 30, tzinfo=UTC)


def test_author_hash_is_stable() -> None:
    first = prepare_issue(issue())
    second = prepare_issue(issue())
    assert first.issue is not None
    assert second.issue is not None
    assert first.issue.author_hash == second.issue.author_hash


def test_pull_requests_bots_and_security_reports_are_skipped() -> None:
    pull_request = prepare_issue(issue(pull_request={"url": "https://api.github.com/pulls/1"}))
    bot = prepare_issue(issue(user={"login": "dependabot", "type": "Bot", "node_id": "U_bot"}))
    security = prepare_issue(issue(labels=[{"name": "Security"}]))

    assert pull_request.skip_reason == "pull_request"
    assert bot.skip_reason == "bot"
    assert security.skip_reason == "security"


def test_missing_optional_fields_use_safe_defaults() -> None:
    prepared = prepare_issue(
        issue(
            body=None, reactions=None, comments=-1, labels=["nope", {"name": "  "}, {"name": "bug"}]
        )
    )

    assert prepared.issue is not None
    assert prepared.issue.body == ""
    assert prepared.issue.labels == ["bug"]
    assert prepared.issue.comment_count == 0
    assert prepared.issue.reactions_total == 0


def test_blank_titles_and_unusable_authors_are_skipped_or_anonymous() -> None:
    blank = prepare_issue(issue(title="   "))
    anonymous = prepare_issue(issue(user=None))
    nameless = prepare_issue(issue(user={"type": "User"}))
    undated = prepare_issue(issue(created_at="yesterday"))

    assert blank.skip_reason == "invalid"
    assert anonymous.issue is not None
    assert anonymous.issue.author_hash is None
    assert nameless.issue is not None
    assert nameless.issue.author_hash is None
    assert undated.skip_reason == "invalid"


def test_failure_messages_distinguish_rate_limits_from_other_errors() -> None:
    assert "rate limit" in _failure_message(GitHubRateLimitedError(datetime.now(UTC))).lower()
    assert _failure_message(GitHubError("GitHub returned HTTP 502.")) == "GitHub returned HTTP 502."
    assert _failure_message(RuntimeError("boom")) == "The import failed before it could finish."


def test_incomplete_payloads_are_skipped() -> None:
    prepared = prepare_issue(issue(state="locked", html_url="http://example.com/1"))

    assert prepared.issue is None
    assert prepared.skip_reason == "invalid"
